#!/usr/bin/env bash
# notify-me: alert when an agent is blocked ("blocked") or finished ("done").
# Usage: notify.sh <blocked|done> [custom message]
# Reads ~/.notify-me/config. Best-effort only — never disrupts the agent.

EVENT="${1:-blocked}"
ARG_MSG="${2:-}"
CONFIG="$HOME/.notify-me/config"
NOTE_FILE="$HOME/.notify-me/note"

# Not set up yet -> stay silent.
[ -f "$CONFIG" ] || exit 0
# shellcheck disable=SC1090
. "$CONFIG" 2>/dev/null || exit 0

TOKEN="${TOKEN:-${TOPIC:-}}"   # ntfy calls this a "topic"; we expose it as TOKEN
SOUND="${SOUND:-on}"
SOUND_FILE="${SOUND_FILE:-/System/Library/Sounds/Glass.aiff}"
NOTIFY_ON_STOP="${NOTIFY_ON_STOP:-off}"
SERVER="${SERVER:-https://ntfy.sh}"

# "done" (turn end) fires on every turn, so it is opt-in.
if [ "$EVENT" = "done" ] && [ "$NOTIFY_ON_STOP" != "on" ]; then
  exit 0
fi

# ---- Decide the human-readable body, best -> fallback ----
# 1) explicit message passed on the command line
# 2) a note the agent left in ~/.notify-me/note (plain-language, task-aware)
# 3) the message Claude provided on the hook's JSON stdin
# 4) a generic default
MSG="$ARG_MSG"

NOTE=""
if [ -z "$MSG" ] && [ -f "$NOTE_FILE" ]; then
  NOTE="$(cat "$NOTE_FILE" 2>/dev/null || true)"
  rm -f "$NOTE_FILE" 2>/dev/null || true   # consume it: a note is used once
  [ -n "$NOTE" ] && MSG="$NOTE"
fi

if [ -z "$MSG" ] && [ ! -t 0 ]; then
  RAW="$(cat 2>/dev/null || true)"
  if [ -n "$RAW" ] && command -v python3 >/dev/null 2>&1; then
    MSG="$(printf '%s' "$RAW" | python3 -c 'import sys,json
try: print(json.load(sys.stdin).get("message",""))
except Exception: pass' 2>/dev/null || true)"
  fi
fi

if [ "$EVENT" = "blocked" ]; then
  TITLE="Agent needs you"; PRIORITY="high"; TAGS="bell"
  BODY="${MSG:-The agent is waiting on your decision.}"
else
  TITLE="Agent finished"; PRIORITY="default"; TAGS="white_check_mark"
  BODY="${MSG:-The agent finished and is waiting.}"
fi

# Local sound (backgrounded, failures ignored).
if [ "$SOUND" = "on" ] && [ -n "$SOUND_FILE" ]; then
  if [ "$SOUND_FILE" = "@system" ]; then
    # Play the OS's currently-selected alert sound (e.g. macOS "Crystal").
    if command -v osascript >/dev/null 2>&1; then
      ( osascript -e 'beep' >/dev/null 2>&1 & )
    elif command -v powershell.exe >/dev/null 2>&1; then
      ( powershell.exe -c "[console]::beep(880,400)" >/dev/null 2>&1 & )
    fi
  elif command -v afplay >/dev/null 2>&1; then
    ( afplay "$SOUND_FILE" >/dev/null 2>&1 & )
  elif command -v paplay >/dev/null 2>&1; then
    ( paplay "$SOUND_FILE" >/dev/null 2>&1 & )
  elif command -v aplay >/dev/null 2>&1; then
    ( aplay "$SOUND_FILE" >/dev/null 2>&1 & )
  elif command -v powershell.exe >/dev/null 2>&1; then
    ( powershell.exe -c "[console]::beep(880,400)" >/dev/null 2>&1 & )
  fi
fi

# Phone push via ntfy (backgrounded, failures ignored).
if [ -n "$TOKEN" ] && command -v curl >/dev/null 2>&1; then
  ( curl -s --max-time 8 \
      -H "Title: $TITLE" -H "Priority: $PRIORITY" -H "Tags: $TAGS" \
      -d "$BODY" "$SERVER/$TOKEN" >/dev/null 2>&1 & )
fi

exit 0
