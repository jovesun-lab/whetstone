#!/usr/bin/env python3
"""SessionStart hook -- open this session's counter, and surface what it carries.

WHAT RESETS, AND WHY IT IS NOT THE HOST'S LABEL
-----------------------------------------------
Counters belong to one session id and are reset by an unconsumed wrap marker, never by
the host's session vocabulary. A host may fire `resume` on every single turn; that word
does not mark a unit of work. Finishing does. `strain-wrap.sh` writes the marker (or
your handoff step does), and the next session start consumes it exactly once.

    marker present, unconsumed -> reset the counters, record that it was consumed
    no marker                  -> keep counting (over-reporting beats wiping)
    `compact` source           -> not a fresh start: increment compactions and raise the
                                  tier floor, one way

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
from _strain_common import (state_dir, session_path, wrap_path, load, save, blank,
                            floor_tier, now_iso, touch_index, read_payload, log_model)

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
    st = load(path) or blank(sid, cwd)
    st["sid"] = sid or st.get("sid", "")
    st["source"] = source
    if cwd:
        st["cwd"] = cwd
    if model:
        st["model"] = model

    # THE RESET DECISION -- the wrap marker, nothing else.
    marker = load(wrap_path(sdir))
    marker_ts = str(marker.get("ts", "") or "")
    unconsumed = bool(marker_ts) and marker_ts != str(st.get("consumed_wrap", ""))
    reset = unconsumed and marker.get("verdict", "CLEAN") in ("CLEAN", "CLEAN-WITH-DEBT")
    if reset:
        st["tick"] = 0
        st["compactions"] = 0
        st["last"] = "Healthy"
        st["consumed_wrap"] = marker_ts

    note = ""
    if source == "compact":
        st["compactions"] = int(st.get("compactions", 0)) + 1
        st["last"] = floor_tier(st.get("last", "Healthy"),
                                "Warning" if st["compactions"] >= 2 else "High")
        note = ("Context was COMPACTED (%d time(s) since the last wrap) -- an objective sign "
                "the work has run long. Tier floored to %s." % (st["compactions"], st["last"]))

    st["updated"] = now_iso()
    save(path, st)
    touch_index(sdir, sid, cwd)
    # Log only when the host actually supplied a model. Most SessionStart payloads
    # don't, and a row that says model:"" records nothing -- the real observation
    # happens at tick time, from the transcript (see _strain_tick.py).
    if model:
        log_model(sdir, sid, source, model, cwd)
    prune(sdir)

    bits = []
    if reset:
        who = marker.get("label") or marker.get("session") or "a completed wrap"
        bits.append("Strain counters reset on %s." % who)
    if st.get("last", "Healthy") != "Healthy":
        bits.append("Carried strain tier: %s." % st["last"])
    if int(st.get("tick", 0)) > 0 and not reset:
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
