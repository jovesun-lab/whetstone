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
    consumed_wrap ts of the wrap marker that last triggered a reset (consume-once)
    ctx           context measurement, when the host exposes one (see _strain_context.py)

RESET BOUNDARY
    Counters reset on an unconsumed wrap marker, not on the host's session labels.
    A host may fire `resume` on every turn, so its vocabulary does not mark a unit of
    work -- finishing does. `strain-wrap.sh` writes the marker; SessionStart consumes it.
"""
import json, os, time

TIERS = ("Healthy", "Mid", "High", "Warning", "Danger")


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


def wrap_path(sdir):
    return os.environ.get("STRAIN_WRAP_MARKER") or os.path.join(sdir, "wrap-marker.json")


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
    idx = load(index_path(sdir))
    entries = idx.get("by_cwd") if isinstance(idx.get("by_cwd"), dict) else {}
    key = cwd or "-"
    entries[key] = {"sid": sid, "ts": now_iso()}
    idx["by_cwd"] = entries
    idx["last"] = {"sid": sid, "cwd": key, "ts": now_iso()}
    save(index_path(sdir), idx)


def resolve_sid(sdir, explicit=None, cwd=None):
    """Which session is 'this one' when nobody handed us a payload.

    Returns (sid, how) so callers can report the basis of the guess instead of hiding it.
    """
    if explicit:
        return explicit, "explicit"
    env = os.environ.get("STRAIN_SESSION")
    if env:
        return env, "STRAIN_SESSION"
    idx = load(index_path(sdir))
    cwd = cwd or os.getcwd()
    by_cwd = idx.get("by_cwd") if isinstance(idx.get("by_cwd"), dict) else {}
    hit = by_cwd.get(cwd)
    if isinstance(hit, dict) and hit.get("sid"):
        return hit["sid"], "cwd"
    last = idx.get("last")
    if isinstance(last, dict) and last.get("sid"):
        return last["sid"], "most-recent"
    return "", "none"


def blank(sid="", cwd=""):
    return {"sid": sid, "tick": 0, "last": "Healthy", "compactions": 0,
            "source": "", "model": "", "cwd": cwd, "updated": now_iso(),
            "consumed_wrap": "", "ctx": {}}


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
