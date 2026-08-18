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
from _strain_common import state_dir, wrap_path, load, save, now_iso, resolve_sid


def main(argv):
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--state-dir", default=None)
    ap.add_argument("--label", default="")
    ap.add_argument("--session", default=None)
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
    marker = {
        "ts": now_iso(),
        "verdict": "CLEAN-WITH-DEBT" if args.with_debt else "CLEAN",
        "label": args.label or "",
        "session": sid,
        "resolved_by": how,
    }
    if not save(path, marker):
        sys.stderr.write("could not write wrap marker to %s\n" % path)
        return 1
    sys.stdout.write("wrap marked (%s)%s\n"
                     % (marker["verdict"], " -- " + args.label if args.label else ""))
    sys.stderr.write("counters reset at the next session start; marker at %s\n" % path)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
