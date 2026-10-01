#!/usr/bin/env python3
"""Stamp a wrap -- this session wrapped / handed off. It resets nothing (0.7.0).

    strain-wrap.sh                      stamp: this session wrapped
    strain-wrap.sh --label "phase 2"    name what was handed off
    strain-wrap.sh --with-debt          wrapped, with known loose ends
    strain-wrap.sh --status             show this session's wrap state

WHAT A STAMP MEANS: "this session wrapped / handed off" -- NOT "the work is right" (that
is your project's own check and your own judgement). Until 0.6.0 the stamp was a shared
marker that RESET counters at the next session start; that reset another live session
of the same signature, and reset a session that kept working in the same full context
after its own wrap. Now the stamp records wrappedAt / wrapTick in this session's own
state and, for a signed session with a ledger, appends one `wrap` row to the ledger.
A new session starts at zero anyway (one session, one file); the next session's sign
reports this one (strain-sign.sh). Work after a stamp makes it stale: the tick says so.
"""
import argparse, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _strain_common import (state_dir, session_path, load, save, now_iso, resolve_sid,
                            resolve_for_write, ledger_append_why, signals_of, state_lock,
                            why_unsaved)


def main(argv):
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--state-dir", default=None)
    ap.add_argument("--label", default="")
    ap.add_argument("--session", default=None)
    ap.add_argument("--agent", default=None)     # 0.5.0: sign the marker explicitly
    ap.add_argument("--with-debt", action="store_true")
    ap.add_argument("--status", action="store_true")
    args, _ = ap.parse_known_args(argv)

    sdir = state_dir(args.state_dir)
    if args.status:
        sid, how = resolve_sid(sdir, args.session)
        if how.startswith("guessed"):
            sys.stderr.write("session %s %s\n" % (sid, how))
    else:
        # 0.8.0 A7: a wrap stamp goes to the session that wrapped, never a guessed one.
        sid, how, refusal = resolve_for_write(sdir, args.session, "strain-wrap.sh", argv)
        if refusal:
            sys.stderr.write(refusal)
            return 2
    if not sid:
        sys.stderr.write("no session known yet (a hook has to run once first)\n")
        return 2
    path = session_path(sdir, sid)
    with state_lock(path):
        st = load(path)
        if args.status:
            sys.stdout.write(json.dumps({"session": sid, "agent": st.get("agent") or None,
                                         "wrappedAt": st.get("wrappedAt") or None,
                                         "wrapTick": st.get("wrapTick"),
                                         "tick": int(st.get("tick", 0) or 0)}, indent=1) + "\n")
            return 0
        agent = args.agent or os.environ.get("STRAIN_AGENT") or str(st.get("agent") or "")
        ts = now_iso()
        tick = int(st.get("tick", 0) or 0)
        verdict = "WRAPPED-WITH-DEBT" if args.with_debt else "WRAPPED"
        st["wrappedAt"] = ts
        st["wrapTick"] = tick
        st["updated"] = ts
        if not save(path, st):
            sys.stderr.write("could not write state: %s\n" % why_unsaved(path))
            return 1
    # a signed session with a ledger also books the stamp -- one row beside its boot-sign
    ledger = str(st.get("ledger") or "")
    booked = ""
    if ledger:
        sig = signals_of(st)
        why = ledger_append_why(ledger, {
            "type": "wrap", "ts": ts, "session": sid, "agent": agent, "verdict": verdict,
            "label": args.label or "", "tier": str(st.get("last", "") or ""), "tick": tick,
            "compactions": int(st.get("compactions", 0) or 0),
            "escaped": sum(1 for x in sig if x.get("escaped")),
            "caught": sum(1 for x in sig if not x.get("escaped"))})
        booked = " · booked" if not why else " · WARNING: the book could not be written"
        if why:
            sys.stderr.write("ledger not written: %s\n" % why)
    # CHAT SURFACE, two registers: stdout is USER-SURFACE -- plain words, no paths;
    # stderr carries the paths for the agent.
    extra = (" · " + args.label if args.label else "") + \
        (" · with known loose ends" if args.with_debt else "")
    if agent:
        sys.stdout.write("Strain · Owner: %s — wrapped%s%s\n" % (agent, extra, booked))
    else:
        sys.stdout.write("Strain — wrapped%s%s\n" % (extra, booked))
    sys.stderr.write("details: session %s (via %s) · tick %d · nothing reset%s\n"
                     % (sid[:12], how, tick, (" · ledger " + ledger) if ledger else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
