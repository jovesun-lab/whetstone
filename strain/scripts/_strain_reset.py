#!/usr/bin/env python3
"""SessionStart hook -- open this session's counter, and surface what it carries.

NOTHING RESETS A SESSION'S COUNTERS (0.7.0)
-------------------------------------------
Counters belong to one session id. Until 0.6.0 a wrap marker reset them at the next
session start -- which also reset another live session of the same signature, and
reset a session that kept working in the SAME full context after its own wrap. A wrap
now only records that the session wrapped (strain-wrap.sh); nothing here resets.

    `startup` / `resume`       -> keep counting this session's file
    `compact` source           -> count it and SAY it ("compaction #N"); it is never a
                                  tier floor -- the fill after it measures the load

HANDING THE SESSION ID TO THE AGENT'S SHELL (0.8.0)
    The hook knows this session's id; the agent's shell does not. On a host that offers
    a hand-over file (Claude Code: CLAUDE_ENV_FILE, written by SessionStart hooks and
    loaded into every later shell command) this hook appends
    `export STRAIN_SESSION=<id>`, so a record command lands in THIS session without the
    agent copying a key. Hosts without one still get the key printed in every tick.

A GENUINELY NEW SESSION STARTS CLEAN
    Each session id gets its own file, so a new conversation begins at zero rather than
    inheriting a number from whatever else was running. This is a deliberate departure
    from the internal build, which carried counters across sessions until a clean wrap.
    What is lost: a session that crashes mid-work no longer bleeds its strain into the
    next one. What is gained: two agents in two windows can never be summed into one
    meaningless total, and in measured mode the reading matches the truth anyway -- a new
    conversation really does start with an empty context window.
"""
import argparse, json, os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _strain_common import (state_dir, session_path, load, save, blank,
                            now_iso, touch_index, read_payload, log_model, state_lock,
                            settle_window, why_unsaved, user_messages_on)
from _strain_tick import caps_calibration_line
import _strain_context as ctxmod

PRUNE_DAYS = 30


def prune(sdir, days=PRUNE_DAYS):
    """Old session files are dead weight; drop them quietly. Never fails the hook."""
    try:
        d = os.path.join(sdir, "sessions")
        cutoff = time.time() - days * 86400
        for name in os.listdir(d):
            p = os.path.join(d, name)
            if os.path.isfile(p) and os.path.getmtime(p) < cutoff:
                os.remove(p)
    except Exception:
        pass


def hand_over(sid):
    """0.8.0 A7: append `export STRAIN_SESSION=<id>` to the host's env hand-over file.
    Never fails the session start; silent where the host offers no such file."""
    envf = os.environ.get("CLAUDE_ENV_FILE")
    if not (envf and sid):
        return
    try:
        import shlex
        with open(envf, "a") as f:
            f.write("export STRAIN_SESSION=%s\n" % shlex.quote(sid))
    except Exception:
        pass


def main():
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--state-dir", default=None)
    args, _ = ap.parse_known_args()

    sdir = state_dir(args.state_dir)
    payload = read_payload(sys.stdin)
    sid = str(payload.get("session_id", "") or "")
    source = str(payload.get("source", "") or "")
    model = str(payload.get("model", "") or "")
    cwd = str(payload.get("cwd", "") or "")

    path = session_path(sdir, sid)
    lock = state_lock(path)
    lock.__enter__()                   # 0.7.0: one read-modify-write at a time
    st = load(path) or blank(sid, cwd)
    st["sid"] = sid or st.get("sid", "")
    st["source"] = source
    if cwd:
        st["cwd"] = cwd
    if model:
        st["model"] = model

    note = ""
    if source == "compact":
        st["compactions"] = int(st.get("compactions", 0)) + 1
        note = ("Context was COMPACTED: compaction #%d this session -- stated, never a "
                "tier floor. Re-read your goal and handoff." % st["compactions"])

    if not st.get("substrate") or st.get("substrate") == "unknown":
        st["substrate"] = ctxmod.detect_substrate(payload, cwd)
    st["updated"] = now_iso()
    saved = save(path, st)
    lock.__exit__()
    hand_over(sid)
    unsaved = ""
    if not saved:
        # 0.8.0 A4: said, never swallowed.
        unsaved = why_unsaved(path)
        sys.stderr.write("strain: the session state could not be saved (%s)\n" % unsaved)
    else:
        touch_index(sdir, sid, cwd)
    # Log only when the host actually supplied a model. Most SessionStart payloads
    # don't, and a row that says model:"" records nothing -- the real observation
    # happens at tick time, from the transcript (see _strain_tick.py).
    if model:
        log_model(sdir, sid, source, model, cwd)
    prune(sdir)

    bits = []
    # Calibration is OBSERVABLE at boot -- and since 0.7.0 it is the SAME line the tick
    # prints (the cap ladder in force), so one session never shows two rulers. The
    # window may still read as the default here: the transcript often does not exist
    # at SessionStart, so the true denominator is first observed at tick time.
    # 0.8.0: the same denominator decision as the tick (one ruler), with its source named.
    boot_ctx = dict(st.get("ctx") or {})
    if not boot_ctx.get("limit"):
        boot_ctx["model"] = st.get("model") or ""
        boot_ctx, _look = settle_window(boot_ctx, sdir, st.get("substrate", ""))
    bits.append(caps_calibration_line(boot_ctx, st.get("substrate", "")) + ".")
    if unsaved:
        bits.append("The state file could not be saved (%s) -- nothing is recorded for this"
                    " session until it can be; tell the user." % unsaved)
    if st.get("last", "Healthy") != "Healthy":
        bits.append("Carried strain tier: %s." % st["last"])
    if int(st.get("tick", 0)) > 0:
        bits.append("%d tool calls counted so far in this session." % int(st["tick"]))
    if note:
        bits.append(note)
    if bits:
        out = {"hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": "STRAIN STATE -- " + " ".join(bits),
        }}
        if unsaved and user_messages_on(st.get("substrate")):
            out["systemMessage"] = "Strain: state write FAILED -- %s." % unsaved
        sys.stdout.write(json.dumps(out))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)   # never disturb a session start
