#!/usr/bin/env bash
# notify-me selftest — runs the plugin's own scripts against a throwaway HOME and a capture server on 127.0.0.1.
# Nothing leaves this machine, no sound plays (SOUND="off" in every case), and your real ~/.notify-me is never read.
#
#   bash notify-me/tools/selftest.sh        (from the repo root, or from anywhere — paths are found from this file)
#   exit 0 = every check passed; each failure prints one FAIL line.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
S="$ROOT/scripts"
T="$(mktemp -d)"
SRV=""
cleanup() { [ -n "$SRV" ] && kill "$SRV" 2>/dev/null; rm -rf "$T"; }
trap cleanup EXIT
n=0; fail=0
check() {  # check "<what>" <command…> — passes when the command exits 0
  local what="$1"; shift
  n=$((n+1))
  if ! "$@"; then echo "FAIL #$n: $what"; fail=1; fi
}

# A capture server: every POST becomes one JSON line in $T/req.log — the path, the ntfy headers and the body.
PORT="$(python3 -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')"
python3 - "$PORT" "$T/req.log" <<'PY' &
import http.server, json, sys
port, log = int(sys.argv[1]), sys.argv[2]
class H(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get('Content-Length', 0))).decode()
        with open(log, 'a') as f:
            f.write(json.dumps({'path': self.path, 'title': self.headers.get('Title'),
                                'priority': self.headers.get('Priority'), 'body': body}) + '\n')
        self.send_response(200); self.end_headers()
    def log_message(self, *a): pass
http.server.HTTPServer(('127.0.0.1', port), H).serve_forever()
PY
SRV=$!; disown "$SRV"   # its end at cleanup is expected: no job notice
: > "$T/req.log"

# wait_for <count> [<seconds>] — until req.log holds <count> lines (exit 0) or the time runs out (exit 1).
# notify.sh sends its curl in the background, so a request arrives a moment after the script returns.
wait_for() {
  python3 - "$T/req.log" "$1" "${2:-5}" <<'PY'
import sys, time
log, want, limit = sys.argv[1], int(sys.argv[2]), float(sys.argv[3])
end = time.time() + limit
while time.time() < end:
    try:
        if sum(1 for _ in open(log)) >= want: sys.exit(0)
    except FileNotFoundError: pass
    time.sleep(0.05)
sys.exit(1)
PY
}
# still <count> — nothing new arrives within a short wait.
still() { ! wait_for "$(( $1 + 1 ))" 1; }
# last <field> <value> — the newest request carries that value.
last() { python3 -c 'import json, sys; r = json.loads(open(sys.argv[1]).read().splitlines()[-1]); sys.exit(0 if r.get(sys.argv[2]) == sys.argv[3] else 1)' "$T/req.log" "$1" "$2"; }
count() { wc -l < "$T/req.log" | tr -d ' '; }

H="$T/home"; mkdir -p "$H"
conf() {  # conf <TOKEN line> [more lines…] — a fresh config pointing at the capture server, sound off
  mkdir -p "$H/.notify-me"
  { printf '%s\n' "$@"; printf 'SOUND="off"\nSERVER="http://127.0.0.1:%s"\n' "$PORT"; } > "$H/.notify-me/config"
}
run() { HOME="$H" bash "$S/notify.sh" "$@" < /dev/null; }

# 1 · every script parses
for f in "$S"/*.sh; do check "bash -n $(basename "$f")" bash -n "$f"; done

# 2 · not set up yet: notify.sh stays silent, check-setup.sh offers setup as valid JSON
check "no config: notify.sh exits 0" run blocked "hello"
check "no config: no request" still 0
check "no config: check-setup prints the setup offer as JSON" bash -c \
  'HOME="$1" bash "$2/check-setup.sh" | python3 -c "import json, sys; d = json.load(sys.stdin); sys.exit(0 if \"not yet configured\" in d[\"hookSpecificOutput\"][\"additionalContext\"] else 1)"' _ "$H" "$S"

# 3 · set up: check-setup is quiet; "blocked" pushes a high-priority ping to the topic
conf 'TOKEN="selftest-topic"'
check "config present: check-setup prints nothing" test -z "$(HOME="$H" bash "$S/check-setup.sh")"
check "blocked: notify.sh exits 0" run blocked "pick a colour"
check "blocked: one request arrives" wait_for 1
check "blocked: sent to /<token>" last path /selftest-topic
check "blocked: title" last title "Agent needs you"
check "blocked: high priority" last priority high
check "blocked: the message is the body" last body "pick a colour"

# 4 · "done" is opt-in
check "done, NOTIFY_ON_STOP off: notify.sh exits 0" run done
check "done, NOTIFY_ON_STOP off: nothing arrives" still 1
conf 'TOKEN="selftest-topic"' 'NOTIFY_ON_STOP="on"'
run done
check "done, NOTIFY_ON_STOP on: a request arrives" wait_for 2
check "done: title" last title "Agent finished"
check "done: default priority" last priority default
check "done: the default body" last body "The agent finished and is waiting."

# 5 · the body: a note left by the agent (used once), then the hook's JSON message
conf 'TOKEN="selftest-topic"'
printf 'The deploy needs your yes.' > "$H/.notify-me/note"
run blocked
check "note: arrives" wait_for 3
check "note: is the body" last body "The deploy needs your yes."
check "note: used once (file removed)" test ! -e "$H/.notify-me/note"
printf '{"message":"Claude needs your permission to use Bash"}' | HOME="$H" bash "$S/notify.sh" blocked
check "hook JSON: arrives" wait_for 4
check "hook JSON: its message is the body" last body "Claude needs your permission to use Bash"

# 6 · the older TOPIC= name still works; no token means no push; a server that is down never breaks the agent
conf 'TOPIC="legacy-topic"'
run blocked "x"
check "TOPIC=: arrives at /legacy-topic" wait_for 5
check "TOPIC=: path" last path /legacy-topic
conf 'SOUND_FILE="@system"'
check "no token: exits 0" run blocked "x"
check "no token: no request" still 5
mkdir -p "$H/.notify-me"; printf 'TOKEN="t"\nSOUND="off"\nSERVER="http://127.0.0.1:1"\n' > "$H/.notify-me/config"
check "server down: exits 0" run blocked "x"

# 7 · the setup skill makes the config readable by its owner only — it holds the token, which is the password for the topic.
#     The skill is text an agent follows, so the check reads the step itself.
SKILL="$ROOT/skills/notify-me-setup/SKILL.md"
check "setup skill: step 4 makes the config owner-only (chmod 600)" grep -qF 'chmod 600 "$HOME/.notify-me/config"' "$SKILL"

[ "$fail" -eq 0 ] && echo "selftest: $n/$n checks passed" && exit 0
echo "selftest FAILED"; exit 1
