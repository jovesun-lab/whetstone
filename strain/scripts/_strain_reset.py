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
                            now_iso, touch_index, read_payload, log_model, state_lock)
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

    if not st.get("substrate"):
        st["substrate"] = ctxmod.detect_substrate(payload, cwd)
    st["updated"] = now_iso()
    save(path, st)
    lock.__exit__()
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
    bits.append(caps_calibration_line(st.get("ctx") or {}, st.get("substrate", "")) + ".")
    if st.get("last", "Healthy") != "Healthy":
        bits.append("Carried strain tier: %s." % st["last"])
    if int(st.get("tick", 0)) > 0:
        bits.append("%d tool calls counted so far in this session." % int(st["tick"]))
    if note:
        bits.append(note)
    if bits:
        sys.stdout.write(json.dumps({"hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": "STRAIN STATE -- " + " ".join(bits),
        }}))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)   # never disturb a session start
