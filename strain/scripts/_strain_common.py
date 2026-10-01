#!/usr/bin/env python3
"""Shared state helpers for the strain driver.

ONE SESSION, ONE MEASUREMENT
----------------------------
Strain is a property of a single conversation, so every counter lives in a file named
after that conversation's session id:

    <state_dir>/sessions/<session-id>.json

Two agents working the same project in two windows are two sessions, and they must not
add up. An earlier build kept one global state file with a single `sid` slot; a second
session simply overwrote the first and both counters became meaningless. The session id
is also the key the host uses for the transcript, so "whose strain is this" and "can I
read this session's real context size" are answered by the same identifier.

STATE SCHEMA (one JSON object per session file)
    sid           session id, from the hook payload
    tick          tool-calls counted since the last wrap
    last          last recorded tier (see TIERS) -- written by _strain_level.py
    compactions   how many times context was compacted since the last reset
    source        how the session started (startup/resume/clear/compact/fork)
    model         model string from the SessionStart payload, when the host supplies it
    cwd           working directory, used to resolve "the current session" from the CLI
    updated       ISO timestamp of the last write
    wrappedAt     ts of this session's last wrap stamp (strain-wrap.sh), 0.7.0
    wrapTick      the tick count at that stamp -- work after it makes the stamp stale
    ctx           context measurement, when the host exposes one (see _strain_context.py);
                  0.8.0: carries `source`, `limitSource` (where the window came from) and,
                  when it is not a usable number, `kind` + `why`
    noSource      0.8.0: {checked, at} -- the agent looked and the host shows no usage
    signedAt      0.8.0: first sign (the receipt prints once, at it)
    receiptShown  0.8.0: when the hook showed the receipt to the user (Claude Code)
    lastProposal  0.8.0: the last proposed tier, so a NEW UNMEASURED can be told once
    legacyNoted   0.8.0: the "old record has no model" note was given

NOTHING RESETS (0.7.0)
    A session's counters are never reset. A new session is a new file, so it starts at
    zero; a wrap only records that the session wrapped. (Until 0.6.0 a shared wrap
    marker reset counters at the next session start -- including another live
    session's, and a session still working in the same full context.)
"""
import json, os, time

TIERS = ("Healthy", "Mid", "High", "Warning", "Danger")
# 0.8.0: what an agent may RECORD. UNMEASURED is not a tier on the ladder -- it says the
# load was not measured -- but an agent with no number to feed must be able to record
# exactly that, instead of inventing a tier or keeping the default Healthy.
RECORDABLE = TIERS + ("UNMEASURED",)


def state_dir(explicit=None):
    """Where strain keeps its files.

    Order: explicit flag > STRAIN_STATE_DIR > $XDG_STATE_HOME/strain > ~/.local/state/strain.
    A plain, readable location on purpose: when a hook misbehaves you want to be able to
    open the state file and see whether it ran at all.
    """
    if explicit:
        return os.path.expanduser(explicit)
    env = os.environ.get("STRAIN_STATE_DIR")
    if env:
        return os.path.expanduser(env)
    xdg = os.environ.get("XDG_STATE_HOME")
    if xdg:
        return os.path.join(os.path.expanduser(xdg), "strain")
    return os.path.expanduser("~/.local/state/strain")


def session_path(sdir, sid):
    """The state file for one session. An empty/unknown sid gets its own bucket rather
    than silently sharing another session's counters."""
    safe = "".join(c for c in str(sid) if c.isalnum() or c in "-_") or "unknown-session"
    return os.path.join(sdir, "sessions", safe + ".json")


def index_path(sdir):
    return os.path.join(sdir, "index.json")


def load(path):
    try:
        with open(path) as f:
            d = json.load(f)
            return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def save(path, obj):
    try:
        d = os.path.dirname(path)
        if d and not os.path.isdir(d):
            os.makedirs(d, exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(obj, f, indent=1)
        os.replace(tmp, path)
        return True
    except Exception:
        return False


class state_lock(object):
    """0.7.0: one read-modify-write of a session file at a time. Parallel tool calls
    fire parallel PostToolUse hooks; without a lock two of them read the same count and
    both write count+1 -- a lost update (0.6.0 selftest: 72 parallel ticks, counts lost).
    The save is already atomic (tmp + rename), so the lock only serialises the RMW.
    Best effort: a platform without fcntl runs unlocked, as before."""
    def __init__(self, path):
        self.path = path + ".lock"
        self.f = None

    def __enter__(self):
        try:
            import fcntl
            d = os.path.dirname(self.path)
            if d and not os.path.isdir(d):
                os.makedirs(d, exist_ok=True)
            self.f = open(self.path, "a")
            fcntl.flock(self.f, fcntl.LOCK_EX)
        except Exception:
            self.f = None
        return self

    def __exit__(self, *exc):
        try:
            if self.f is not None:
                import fcntl
                fcntl.flock(self.f, fcntl.LOCK_UN)
                self.f.close()
        except Exception:
            pass
        return False


def now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def log_model(sdir, sid, source, model, cwd):
    """A durable record of which model ran which session -- appended, never rewritten.

    Useful when you want to ask whether a model change moved the strain trend. Set
    STRAIN_NO_MODEL_LOG=1 to turn it off; nothing leaves the machine either way.

    Callers only log when they actually have a model string: the SessionStart payload
    usually omits it, so the real source is the transcript, read at tick time -- the
    same timing lesson as the context probe.
    """
    if os.environ.get("STRAIN_NO_MODEL_LOG"):
        return
    try:
        path = os.path.join(sdir, "model-log.jsonl")
        if not os.path.isdir(sdir):
            os.makedirs(sdir, exist_ok=True)
        with open(path, "a") as f:
            f.write(json.dumps({"ts": now_iso(), "session_id": sid, "source": source,
                                "model": model, "cwd": cwd}) + "\n")
    except Exception:
        pass


def touch_index(sdir, sid, cwd):
    """Record `this cwd was last driven by this session`.

    The hooks always know their session id because the host puts it in the payload. A
    command typed at a shell does not, so the CLI resolves the session through this
    index. It is a best-effort pointer, not a source of truth: two sessions sharing one
    working directory will take turns owning the entry, which is why `strain-level.sh`
    accepts an explicit --session and says which session it resolved to.
    """
    if not sid:
        return
    ip = index_path(sdir)
    existed = os.path.isfile(ip)
    idx = load(ip)
    if existed and not idx:
        # The index exists but could not be read: refuse the rewrite. load()'s {} fed
        # into save() would replace the whole file with this one entry -- a bad read
        # must not evaporate everyone else's rows. Skipping one best-effort update is
        # the cheap side of that trade.
        return
    entries = idx.get("by_cwd") if isinstance(idx.get("by_cwd"), dict) else {}
    key = cwd or "-"
    entries[key] = {"sid": sid, "ts": now_iso()}
    idx["by_cwd"] = entries
    idx["last"] = {"sid": sid, "cwd": key, "ts": now_iso()}
    save(index_path(sdir), idx)


def resolve_sid(sdir, explicit=None, cwd=None):
    """Which session is 'this one' for a READ (--get, --show, --list, --status).

    Returns (sid, how). A key the caller or the host handed over is used as given; with
    none, a read may GUESS from the index -- and `how` says "guessed (...)" so the guess
    is never mistaken for an identity. A WRITE never comes here: see resolve_for_write.
    """
    keys, _check = _session_keys(explicit)
    if keys:
        return keys[0][1], keys[0][0]
    idx = load(index_path(sdir))
    cwd = cwd or os.getcwd()
    by_cwd = idx.get("by_cwd") if isinstance(idx.get("by_cwd"), dict) else {}
    hit = by_cwd.get(cwd)
    if isinstance(hit, dict) and hit.get("sid"):
        return hit["sid"], "guessed (this folder)"
    last = idx.get("last")
    if isinstance(last, dict) and last.get("sid"):
        return last["sid"], "guessed (most recent session on this machine)"
    return "", "none"


# ---- 0.8.0 A7: IDENTITY IS HANDED OVER BY THE HOST, NEVER GUESSED ----------------------
# The only party that KNOWS a session's id is the host (it is in every hook payload); the
# party that ACTS is the agent's shell, which is never told. Before 0.8.0 a record command
# without a key fell back to "the session last seen in this folder", then "the most recent
# session on the machine" -- so with two agents active a tier, an escaped error or a wrap
# landed in whichever session fired a hook last, and the right session's number never
# moved. Sources, in order of trust:
#   --session <id>          typed by the caller
#   STRAIN_SESSION          the key the tick prints into every command; on Claude Code the
#                           SessionStart hook also exports it into the agent's shell
#                           (CLAUDE_ENV_FILE, the host's documented hand-over)
#   CODEX_THREAD_ID         Codex's own shell variable (= the hook's session id)
#   CLAUDE_CODE_SESSION_ID  present in Claude Code shells but undocumented: a CROSS-CHECK
#                           only, never the only source
# Sources that disagree -> refuse and say which. No source -> a write refuses (exit 2)
# and lists candidate sessions with ready commands; it never picks one.
HOST_KEYS = ("CODEX_THREAD_ID",)
CROSS_CHECKS = ("CLAUDE_CODE_SESSION_ID",)


def _session_keys(explicit=None):
    keys = []
    if explicit:
        keys.append(("--session", str(explicit)))
    if os.environ.get("STRAIN_SESSION"):
        keys.append(("STRAIN_SESSION", os.environ["STRAIN_SESSION"]))
    for k in HOST_KEYS:
        if os.environ.get(k):
            keys.append((k, os.environ[k]))
    checks = [(k, os.environ[k]) for k in CROSS_CHECKS if os.environ.get(k)]
    return keys, checks


def resolve_for_write(sdir, explicit=None, script="", args=()):
    """(sid, how, refusal). refusal is "" when the write may go ahead, else the full
    stderr text to print before exiting 2."""
    keys, checks = _session_keys(explicit)
    named = keys + checks
    if keys:
        sid = keys[0][1]
        off = [(k, v) for k, v in named if v != sid]
        if not off:
            return sid, keys[0][0], ""
        lines = ["the session sources disagree -- nothing recorded:"]
        lines += ["  %s = %s" % (k, v) for k, v in named]
        lines.append("A record must land in ONE session. If the key in your command is from an"
                     " earlier session, use the one this shell's host names; if you really mean"
                     " another session, run the command from a shell without the host variable"
                     " (env -u <variable> ...).")
        return "", "conflict", "\n".join(lines) + "\n"
    hinted = checks[0][1] if checks else ""
    return "", "none", refusal_text(sdir, script, args, hinted)


def candidate_sessions(sdir, cwd=None, hinted="", limit=3):
    """Up to `limit` recent sessions, the host-hinted one first, then this folder's, then
    the most recently updated. Read-only; for the refusal's list, never for a pick."""
    d = os.path.join(sdir, "sessions")
    rows = []
    try:
        names = [n for n in os.listdir(d) if n.endswith(".json")]
    except Exception:
        names = []
    for n in names:
        p = os.path.join(d, n)
        st = load(p)
        sid = str(st.get("sid") or n[:-5])
        try:
            mt = os.path.getmtime(p)
        except Exception:
            mt = 0
        rows.append((sid, st, mt))
    cwd = cwd or os.getcwd()
    rows.sort(key=lambda r: (r[0] != hinted, str(r[1].get("cwd") or "") != cwd, -r[2]))
    return rows[:limit]


def refusal_text(sdir, script, args, hinted=""):
    here = os.path.dirname(os.path.abspath(__file__))
    import shlex
    rest = " ".join(shlex.quote(str(a)) for a in args)
    lines = ["no session key -- nothing recorded. strain does not guess which session a record"
             " belongs to (a guess lands it in whichever session fired last). Run the command"
             " the latest strain tick printed (it carries STRAIN_SESSION=<this session>), or"
             " pick your session below:"]
    for sid, st, mt in candidate_sessions(sdir, hinted=hinted):
        tag = []
        if sid == hinted:
            tag.append("this shell's host names this one")
        if st.get("substrate"):
            tag.append(str(st["substrate"]))
        if st.get("agent"):
            tag.append("agent %s" % st["agent"])
        tag.append("%d tool calls" % int(st.get("tick", 0) or 0))
        if mt:
            tag.append("updated %s" % time.strftime("%m-%d %H:%M", time.localtime(mt)))
        if st.get("cwd"):
            tag.append("folder %s" % st["cwd"])
        lines.append("  %s  (%s)" % (sid, " · ".join(tag)))
        if script:
            lines.append("    STRAIN_SESSION=%s STRAIN_STATE_DIR=%s bash %s %s"
                         % (shlex.quote(sid), shlex.quote(sdir),
                            shlex.quote(os.path.join(here, script)), rest))
    if len(lines) == 1:
        lines.append("  (no session has been seen yet -- a hook has to run once first)")
    return "\n".join(lines) + "\n"


def blank(sid="", cwd=""):
    return {"sid": sid, "tick": 0, "last": "Healthy", "compactions": 0,
            "source": "", "model": "", "cwd": cwd, "updated": now_iso(),
            "ctx": {}, "substrate": "", "signals": []}


def signals_of(st):
    s = st.get("signals")
    return s if isinstance(s, list) else []


def signal_floor(st):
    """The tier hard signals justify on their own -- ABSOLUTE, never diluted by capacity.

    Only signals that ESCAPED (reached the user / shipped work before being caught)
    drive the tier. A caught-and-fixed error is a working immune system, not exhaustion
    -- it is recorded, and a repeat of the same class earns a pattern note, but the
    tier's job is to answer "can this session keep going?", which a caught error does
    not change. (Third fixture, 2026-08-15: three same-class caught-and-fixed errors at
    33% fill -- v1 ratcheted to Danger; the session was fine.)
    """
    escaped = sum(1 for s in signals_of(st) if s.get("escaped"))
    # v3 ladder -- TEAM POLICY, deliberately code constants and NOT env knobs (a
    # policy adjustable by environment fiddling is an instrument whose meaning can
    # drift silently; change these by team decision + edit, so the change is visible
    # in review). Rationale for the default: escaped errors often arrive in a burst
    # that shares ONE root cause (a capability gap -- the agent lacks a discipline
    # for some class of task), and a capability gap is not exhaustion. 0-2 escaped
    # move nothing on their own; a wider spread starts to look like degradation:
    # 3 -> Mid, 4 -> High, >=5 -> Warning. Tune to your team's error tolerance.
    if escaped >= 5:
        return "Warning"
    if escaped == 4:
        return "High"
    if escaped == 3:
        return "Mid"
    return None


def pattern_note(st):
    """A repeat of the same signal class is worth telling the human -- as a pattern,
    not as a tier. Returns "" when there is nothing to say."""
    seen = {}
    for s in signals_of(st):
        k = str(s.get("kind") or "unspecified")
        seen[k] = seen.get(k, 0) + 1
    rep = ["%s x%d" % (k, n) for k, n in sorted(seen.items()) if n >= 2]
    if not rep:
        return ""
    return "Pattern note: repeated signal class(es): %s -- name the pattern to the user." \
        % ", ".join(rep)


def floor_tier(current, minimum):
    """Raise `current` to at least `minimum`; never lower it.

    An escalation is one-way within a session: a compaction happened, and a later
    optimistic reading does not un-happen it.
    """
    try:
        ci = TIERS.index(current)
    except ValueError:
        ci = 0
    try:
        mi = TIERS.index(minimum)
    except ValueError:
        mi = 0
    return TIERS[max(ci, mi)]


def read_payload(stdin):
    """Hook payloads arrive as JSON on stdin.

    Must be a real file or pipe. Running the script from a shell heredoc makes the
    heredoc itself stdin, the payload is then unreadable, and the hook silently records
    an empty session id -- a failure that looks exactly like 'the hook never ran'.
    """
    try:
        raw = stdin.read() if not stdin.isatty() else ""
    except Exception:
        return {}
    try:
        p = json.loads(raw) if raw.strip() else {}
        return p if isinstance(p, dict) else {}
    except Exception:
        return {}


# ---- the project ledger (0.5.0) ------------------------------------------------------
# A durable, append-only account book a project can keep of its sessions: one JSONL row
# per event (boot-sign, wrap). Optional -- nothing here runs unless a session signs with
# a ledger path. The file lives wherever you point it; we suggest `Log.strain` at the
# project root, gitignored. Append-only on purpose: an account book that gets rewritten
# whole is one bad read away from evaporating (the same failure class the index guard
# below refuses).

def ledger_append(path, row):
    """Append ONE JSONL row, flock-guarded so two agents signing or wrapping at the
    same moment cannot interleave. Creates the file on first append; never rewrites
    existing content. Returns True on success."""
    try:
        import fcntl
        line = json.dumps(row) + "\n"
        with open(path, "a") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                f.write(line)
                f.flush()
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
        return True
    except Exception:
        return False


def ledger_append_why(path, row):
    """0.7.0: the same append, returning "" on success or WHY it failed -- a missing
    folder, a read-only file and a lock failure used to read the same."""
    if ledger_append(path, row):
        return ""
    d = os.path.dirname(os.path.abspath(path))
    if not os.path.isdir(d):
        return "the folder %s does not exist" % d
    if os.path.exists(path) and not os.access(path, os.W_OK):
        return "no write permission on %s" % path
    if not os.access(d, os.W_OK):
        return "no write permission in the folder %s" % d
    return "the append failed (lock or write error) on %s" % path


def ledgers_registry_path(sdir):
    return os.path.join(sdir, "ledgers.json")


def load_ledgers(sdir):
    """0.5.1: the per-AGENT durable ledger registry -- cross-session memory for
    'where is my book', so a later session signs with no --ledger. A convenience
    pointer, never identity: identity stays in the ledger's own signed rows."""
    d = load(ledgers_registry_path(sdir))
    return d if isinstance(d, dict) else {}


def save_ledgers(sdir, agent, ledger):
    """Upsert one agent's row, flock-guarded, refusing to rewrite an EXISTING but
    unreadable registry (a bad read must not evaporate everyone else's rows --
    the same discipline as touch_index)."""
    try:
        import fcntl
        ip = ledgers_registry_path(sdir)
        lock = open(ip + ".lock", "w")
        try:
            fcntl.flock(lock, fcntl.LOCK_EX)
            existed = os.path.isfile(ip)
            reg = load(ip)
            if existed and not reg:
                return False
            reg[str(agent)] = {"ledger": str(ledger), "ts": now_iso()}
            return save(ip, reg)
        finally:
            try:
                fcntl.flock(lock, fcntl.LOCK_UN)
            except Exception:
                pass
            lock.close()
    except Exception:
        return False


def ledger_rows(path):
    """The ledger's rows, file order. Unparseable lines are skipped, never fatal -- a
    torn tail must not hide the rest of the book."""
    rows = []
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                    if isinstance(r, dict):
                        rows.append(r)
                except Exception:
                    continue
    except Exception:
        pass
    return rows


# ---- 0.6.0: the context FEED DOOR -----------------------------------------------------
# First cross-model field report (a gpt-6 / Codex-family session, 2026-09-22): the host
# REPORTED its runtime window and per-turn usage, and strain could parse none of it --
# the transcript reader knows one host's shape. "The host does not expose a reading" and
# "the host exposes one strain cannot read" landed in the same coarse mode. The fix is a
# front door, not more adapters: the AGENT can usually see its host's own numbers, so let
# it hand them over -- with provenance, never dressed up as a measurement strain made.

def calibration_path(sdir):
    return os.path.join(sdir, "calibration.json")


def calibration_valid(cal):
    """(ok, why). A capacity nobody sourced is a stale ruler waiting to happen: the
    record must carry a positive window, a source, a fresh checkedAt (default 30 days,
    STRAIN_CALIBRATION_MAX_DAYS), and say which KIND of number it is -- `nominal` (the
    published capacity) or `runtime` (what the host reports live, e.g. a post-compaction
    window). Mixing the two is how a runtime reading gets mistaken for the model's size."""
    if not isinstance(cal, dict) or not cal:
        return False, "no calibration record"
    try:
        w = int(cal.get("window") or 0)
    except Exception:
        w = 0
    if w <= 0:
        return False, "window missing or invalid"
    if not str(cal.get("source") or "").strip():
        return False, "record carries no source"
    basis = str(cal.get("basis") or "")
    if basis not in ("nominal", "runtime"):
        return False, "basis must be 'nominal' or 'runtime'"
    ca = str(cal.get("checkedAt") or "")[:10]
    try:
        age = (time.time() - time.mktime(time.strptime(ca, "%Y-%m-%d"))) / 86400.0
    except Exception:
        return False, "checkedAt unreadable"
    max_days = int(os.environ.get("STRAIN_CALIBRATION_MAX_DAYS", "30"))
    if age > max_days:
        return False, "stale: checked %s (%dd > %dd)" % (ca, int(age), max_days)
    return True, "calibrated %s (%s, %s window %d)" % (ca, cal.get("product") or "?",
                                                       basis, w)


# ---- 0.8.0 A1: THE MODEL REGISTRY -- a capacity belongs to one <product> · <model> -----
# 0.6.0/0.7.0 kept ONE calibration.json per machine and exported any valid record into the
# window of EVERY session: a Codex session recorded its 258,400-token window, and from the
# next tool call on every Claude Code session on that machine divided by it (a session 19%
# full was told "Danger -- wrap now"). The record named its product and model; nothing
# ever compared them. Now: models.json, one entry per "<product> · <model>", and a record
# applies only where it fits:
#   - the model must match, always;
#   - on a host strain recognises (Claude Code, Cowork, cloud Cowork, Codex) the product
#     must match too -- Sonnet 5 compacts at 500K in Cowork, not in Claude Code;
#   - on a host strain does not recognise, the model alone picks, among records made for
#     unrecognised hosts, and only when exactly one fits.
# calibration.json is never written again; an old one is read as one more entry, keyed by
# its own product · model, and one with no model is never applied.
PRODUCT_OF_SUBSTRATE = {"claude-code": "Claude Code", "cowork": "Cowork",
                        "cowork-cloud": "Cowork", "codex": "Codex"}
RECOGNISED_PRODUCTS = ("Claude Code", "Cowork", "Codex")


def canon_product(product):
    """One spelling per product, at write AND lookup."""
    p = " ".join(str(product or "").replace("-", " ").split())
    low = p.lower()
    if low in ("claude code", "claudecode"):
        return "Claude Code"
    if low in ("cowork", "claude cowork"):
        return "Cowork"
    if low == "codex" or low.startswith("codex "):
        return "Codex"
    return p


def model_key(product, model):
    p, m = canon_product(product), str(model or "").strip().lower()
    return "%s · %s" % (p, m) if (p and m) else ""


def models_path(sdir):
    return os.path.join(sdir, "models.json")


def load_models(sdir):
    d = load(models_path(sdir))
    return d if isinstance(d, dict) else {}


def save_model(sdir, rec):
    """Upsert one entry under a lock; an EXISTING but unreadable registry refuses the
    rewrite (entries must not evaporate). Returns "" on success, else why."""
    key = model_key(rec.get("product"), rec.get("model"))
    if not key:
        return "a record needs both a product and a model"
    try:
        import fcntl
        ip = models_path(sdir)
        if not os.path.isdir(sdir):
            os.makedirs(sdir, exist_ok=True)
        lock = open(ip + ".lock", "a")
        try:
            fcntl.flock(lock, fcntl.LOCK_EX)
            reg = {}
            if os.path.isfile(ip) and os.path.getsize(ip) > 0:
                try:
                    with open(ip) as f:
                        reg = json.load(f)
                except Exception:
                    reg = None
                if not isinstance(reg, dict):
                    return "models.json exists but cannot be read -- not rewriting it"
            reg[key] = dict(rec, product=canon_product(rec.get("product")),
                            model=str(rec.get("model")).strip().lower())
            return "" if save(ip, reg) else why_unsaved(ip)
        finally:
            try:
                fcntl.flock(lock, fcntl.LOCK_UN)
            except Exception:
                pass
            lock.close()
    except Exception as e:
        return "the registry could not be written (%s)" % type(e).__name__


def registry_entries(sdir):
    """[(key, record, origin)] -- models.json entries, then a legacy calibration.json as
    one more entry (origin "legacy"); a legacy record with no model gets key ""."""
    out = [(k, v, "models.json") for k, v in sorted(load_models(sdir).items())
           if isinstance(v, dict)]
    leg = load(calibration_path(sdir))
    if leg:
        out.append((model_key(leg.get("product"), leg.get("model")), leg, "legacy"))
    return out


def lookup_window(sdir, substrate, model):
    """The record that rules this session, if any. Returns a dict:
        window   int or None
        key      "<product> · <model>" of the record used, or ""
        note     why nothing applied, or "" (e.g. "2 candidates, none applied")
        legacyNoModel  True when an old record without a model exists (said once)."""
    product = PRODUCT_OF_SUBSTRATE.get(str(substrate or ""), "")
    m = str(model or "").strip().lower()
    res = {"window": None, "key": "", "note": "", "legacyNoModel": False}
    cands = []
    for key, rec, origin in registry_entries(sdir):
        if not key:
            if origin == "legacy":
                res["legacyNoModel"] = True
            continue
        ok, why = calibration_valid(rec)
        if not ok:
            continue
        rp = canon_product(rec.get("product"))
        rm = str(rec.get("model") or "").strip().lower()
        if product:
            if rp == product and rm == m and m:
                cands.append((key, rec))
        else:
            if rp in RECOGNISED_PRODUCTS:
                continue
            if not m or rm == m:
                cands.append((key, rec))
    seen = {}
    for key, rec in cands:                     # models.json wins over a legacy duplicate
        seen.setdefault(key, rec)
    if len(seen) == 1:
        key, rec = list(seen.items())[0]
        res.update(window=int(rec["window"]), key=key)
    elif len(seen) > 1:
        res["note"] = "%d candidates, none applied" % len(seen)
    return res


def k_tokens(n):
    try:
        n = int(n)
    except Exception:
        return "?"
    return ("%gM" % (n / 1000000.0)) if n >= 1000000 else ("%.0fk" % (n / 1000.0))


def settle_window(ctx, sdir, substrate):
    """The ONE denominator decision, for the tick and the feed alike: env override >
    a window the host reports live > the matching registry record > the engine's model
    hint > its default. Re-divides the reading and names the source (`limitSource`)."""
    if not isinstance(ctx, dict):
        return ctx, {}
    import _strain_context as ctxmod
    env = os.environ.get("STRAIN_CONTEXT_LIMIT")
    look = {}
    window, src = None, ""
    try:
        if env and int(env) > 0:
            window, src = int(env), "env override"
    except Exception:
        pass
    if window is None and str(ctx.get("limitSource") or "").startswith("host-reported") \
            and ctx.get("limit"):
        window, src = int(ctx["limit"]), ctx["limitSource"]
    if window is None:
        look = lookup_window(sdir, substrate, ctx.get("model") or "")
        if look.get("window"):
            window, src = look["window"], "calibrated: %s" % look["key"]
    if window is None:
        window, src = ctxmod.limit_and_source(ctx.get("model") or "")
        if look.get("note"):
            src += " · " + look["note"]
    ctx["limit"] = int(window)
    ctx["limitSource"] = src
    if ctx.get("tokens") is not None and ctx.get("mode") in ("measured", "estimated",
                                                              "agent-fed"):
        ctx["pct"] = round(100.0 * float(ctx["tokens"]) / float(window), 1)
    return ctx, look


# ---- 0.8.0 A4: a failed save is SAID, never swallowed ----------------------------------

def why_unsaved(path):
    d = os.path.dirname(os.path.abspath(path))
    if not os.path.isdir(d):
        return "the folder %s does not exist or cannot be created" % d
    if not os.access(d, os.W_OK):
        return "no write permission in the folder %s" % d
    if os.path.exists(path) and not os.access(path, os.W_OK):
        return "no write permission on %s" % path
    return "the write to %s failed" % path


def can_write(path):
    d = os.path.dirname(os.path.abspath(path))
    return os.path.isdir(d) and os.access(d, os.W_OK) and \
        (not os.path.exists(path) or os.access(path, os.W_OK))


def unsaved_marker(sdir, sid):
    """A marker OUTSIDE the state dir (which may be the thing that cannot be written),
    keyed by state dir + session, so 'could not be saved' is said once, and the next
    saved reading can say there was a gap."""
    import hashlib, tempfile
    h = hashlib.sha1(("%s\0%s" % (os.path.abspath(sdir), sid)).encode()).hexdigest()[:16]
    return os.path.join(tempfile.gettempdir(), "strain-unsaved-%s" % h)


# ---- 0.8.0 B4: what strain may show the USER directly ----------------------------------
# Claude Code shows a hook's `systemMessage` to the user. strain uses it for three things
# only -- the session's receipt (once), a state file that cannot be saved, and a reading
# that just became UNMEASURED -- so those never depend on the agent choosing to relay
# them. Other hosts: the SKILL asks the agent to relay the one-line receipt verbatim.
USER_MESSAGE_HOSTS = ("claude-code",)


def user_messages_on(substrate):
    if os.environ.get("STRAIN_USER_MESSAGES", "on").strip().lower() in ("off", "0", "no"):
        return False
    return str(substrate or "") in USER_MESSAGE_HOSTS


def reading_line(ctx):
    """(source label, mode label) for the receipt -- plain words, no paths."""
    ctx = ctx or {}
    src = {"claude-transcript": "Claude transcript", "codex-rollout": "Codex log",
           "transcript-bytes": "transcript size (estimate)"}.get(str(ctx.get("source") or ""))
    if ctx.get("mode") == "agent-fed":
        src = "agent-fed (%s)" % (ctx.get("provenance") or "provenance not stated")
    return src or "none", str(ctx.get("mode") or "pending")


def receipt(st, sdir, path, ledger_state):
    """The one-line receipt: host · session · reading source · when · mode (+ kind) ·
    window and where it came from · state file · ledger. stdout-safe: no paths, no flags."""
    ctx = st.get("ctx") if isinstance(st.get("ctx"), dict) else {}
    host = PRODUCT_OF_SUBSTRATE.get(str(st.get("substrate") or ""), "") or \
        ("unrecognised host" if st.get("substrate") else "host not seen yet")
    src, mode = reading_line(ctx)
    when = str(ctx.get("observedAt") or st.get("updated") or "")
    when = _short_when(when)
    parts = ["host %s" % host, "session %s" % str(st.get("sid") or "?")[:8]]
    parts.append("reading %s%s" % (src, (" at " + when) if (when and src != "none") else ""))
    kind = str(ctx.get("kind") or "")
    parts.append(mode + ((" · " + kind) if kind and mode not in ("measured",) else ""))
    if ctx.get("limit"):
        parts.append("window %s (%s)" % (k_tokens(ctx["limit"]), ctx.get("limitSource") or "?"))
    parts.append("state saved" if can_write(path) else "state write FAILED")
    parts.append(ledger_state)
    return "Strain receipt — " + " · ".join(parts)


def _short_when(ts):
    import re
    m = re.match(r"^\d{4}-(\d\d)-(\d\d)T(\d\d):(\d\d)", str(ts or ""))
    if not m:
        return ""
    try:
        from datetime import datetime
        t = str(ts).replace("Z", "+00:00")
        mm = re.match(r"^(.*\d\d:\d\d:\d\d(?:\.\d+)?)([+-]\d\d)(\d\d)$", t)
        if mm:
            t = "%s%s:%s" % mm.groups()
        dt = datetime.fromisoformat(t)
        if dt.tzinfo is not None:
            dt = dt.astimezone()
        return dt.strftime("%m-%d %H:%M")
    except Exception:
        return "%s-%s %s:%s" % m.groups()
