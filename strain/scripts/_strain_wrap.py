#!/usr/bin/env python3
"""Mark a wrap -- the only thing that resets the counters.

    strain-wrap.sh                      mark this session wrapped
    strain-wrap.sh --label "phase 2"    name it, so the next boot can say what reset it
    strain-wrap.sh --with-debt          wrapped, but with known loose ends
    strain-wrap.sh --status             show the current marker

Run it when the work is actually finished: the handoff is written, the tests are green,
the thing is done. That is the objective event strain resets on. It is deliberately a
separate command from `strain-level.sh` -- recording that a session felt heavy and
declaring it finished are different claims, and letting one imply the other is how a
counter ends up being reset by a mood.

Pairs with any wrap discipline you already have. If you use a handoff step, call this as
its last line and the two stay in sync for free.
"""
import argparse, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _strain_common import (state_dir, wrap_path, session_path, load, save, now_iso,
                            resolve_sid, ledger_append)


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
    path = wrap_path(sdir)

    if args.status:
        m = load(path)
        sys.stdout.write(json.dumps(m, indent=1) + "\n" if m else "no wrap marker\n")
        return 0

    sid, how = resolve_sid(sdir, args.session)
    # 0.5.0: the marker carries the wrapping session's signature -- explicit --agent
    # first, else whatever the session signed as (strain-sign.sh). An unsigned wrap
    # writes agent "" and behaves exactly as before; a signed one resets only sessions
    # carrying the same signature (see _strain_reset.py).
    st = load(session_path(sdir, sid)) if sid else {}
    agent = args.agent or os.environ.get("STRAIN_AGENT") or str(st.get("agent") or "")
    marker = {
        "ts": now_iso(),
        "verdict": "CLEAN-WITH-DEBT" if args.with_debt else "CLEAN",
        "label": args.label or "",
        "session": sid,
        "resolved_by": how,
        "agent": agent,
    }
    if not save(path, marker):
        sys.stderr.write("could not write wrap marker to %s\n" % path)
        return 1
    # 0.5.0: a signed session with a ledger also books the wrap -- one row in the
    # project's account book, beside the boot-sign row the sign wrote.
    ledger = str(st.get("ledger") or "")
    booked = ""
    if ledger:
        ok = ledger_append(ledger, {
            "type": "wrap", "ts": marker["ts"], "session": sid, "agent": agent,
            "verdict": marker["verdict"], "label": marker["label"],
            "tier": str(st.get("last", "") or ""), "tick": int(st.get("tick", 0) or 0)})
        booked = " · booked" if ok else " · WARNING: the book could not be written"
    # CHAT SURFACE, two registers (0.5.1): stdout is USER-SURFACE -- Owner-form,
    # plain words, no paths; stderr carries the paths for the agent.
    if agent:
        sys.stdout.write("Strain · Owner: %s — wrap marked (%s)%s%s\n"
                         % (agent, marker["verdict"],
                            " · " + args.label if args.label else "", booked))
    else:
        sys.stdout.write("Strain — wrap marked (%s)%s%s\n"
                         % (marker["verdict"],
                            " · " + args.label if args.label else "", booked))
    sys.stderr.write("details: counters reset at the next session start%s · marker %s%s\n"
                     % (" (same-signature sessions only)" if agent else "", path,
                        (" · ledger " + ledger) if ledger else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
