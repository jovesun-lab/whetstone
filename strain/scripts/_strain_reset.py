#!/usr/bin/env python3
"""SessionStart hook -- open this session's counter, and surface what it carries.

WHAT RESETS, AND WHY IT IS NOT THE HOST'S LABEL
-----------------------------------------------
Counters belong to one session id and are reset by an unconsumed wrap marker, never by
the host's session vocabulary. A host may fire `resume` on every single turn; that word
does not mark a unit of work. Finishing does. `strain-wrap.sh` writes the marker (or
your handoff step does), and the next session start consumes it exactly once.

    marker present, unconsumed -> reset the counters, record that it was consumed
    marker SIGNED (0.5.0)      -> reset only sessions carrying the same signature;
                                  someone else's finish line must not wipe your live
                                  counters (announced once, then quiet)
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
    st = load(path) or blank(sid, cwd)
    st["sid"] = sid or st.get("sid", "")
    st["source"] = source
    if cwd:
        st["cwd"] = cwd
    if model:
        st["model"] = model

    # THE RESET DECISION -- the wrap marker, nothing else. 0.5.0 adds SCOPE: a marker
    # signed by an agent (strain-sign.sh / strain-wrap.sh --agent) resets only sessions
    # carrying the same signature. Shipped failure this closes: two agents, one state
    # dir -- one agent marking its wrap reset the other's LIVE session at its next
    # session start, wiping real strain with someone else's finish line. An unsigned
    # marker keeps the pre-0.5.0 behaviour exactly (signing is opt-in).
    marker = load(wrap_path(sdir))
    marker_ts = str(marker.get("ts", "") or "")
    unconsumed = bool(marker_ts) and marker_ts != str(st.get("consumed_wrap", ""))
    clean = marker.get("verdict", "CLEAN") in ("CLEAN", "CLEAN-WITH-DEBT")
    m_agent = str(marker.get("agent", "") or "")
    mine = str(st.get("agent", "") or "")
    scoped_ok = (not m_agent) or (m_agent == mine)
    reset = unconsumed and clean and scoped_ok
    foreign = unconsumed and clean and not scoped_ok
    # A foreign marker is announced ONCE, then stays quiet -- a host may fire
    # SessionStart every turn, and a repeated line is noise, not information.
    foreign_new = foreign and str(st.get("foreign_wrap_seen", "")) != marker_ts
    if foreign_new:
        st["foreign_wrap_seen"] = marker_ts
    if reset:
        st["tick"] = 0
        st["compactions"] = 0
        st["last"] = "Healthy"
        st["signals"] = []
        st["consumed_wrap"] = marker_ts

    note = ""
    if source == "compact":
        st["compactions"] = int(st.get("compactions", 0)) + 1
        st["last"] = floor_tier(st.get("last", "Healthy"),
                                "Warning" if st["compactions"] >= 2 else "High")
        note = ("Context was COMPACTED (%d time(s) since the last wrap) -- an objective sign "
                "the work has run long. Tier floored to %s." % (st["compactions"], st["last"]))

    if not st.get("substrate"):
        st["substrate"] = ctxmod.detect_substrate(payload, cwd)
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
    # Calibration is OBSERVABLE at boot -- one line naming substrate, window, and bands,
    # derived from what was detected rather than a baked-in table, so a mis-calibration
    # is visible to the human instead of silently wrong. The window may still read as
    # the default here: the transcript often does not exist at SessionStart, so the
    # model (and with it the true denominator) is first observed at tick time -- the
    # tick prints the same line with the measured values.
    bits.append(ctxmod.calibration_line(st.get("ctx") or {}, st.get("substrate", "")) + ".")
    if reset:
        who = marker.get("label") or marker.get("session") or "a completed wrap"
        if m_agent:
            who = "%s (signed %s)" % (who, m_agent)
        bits.append("Strain counters reset on %s." % who)
    elif foreign_new:
        bits.append("A wrap marker signed by %s is present; this session keeps its "
                    "counters (different signature%s)."
                    % (m_agent,
                       "" if mine else " -- this session is unsigned; "
                       "strain-sign.sh --agent <name> to scope wraps"))
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
