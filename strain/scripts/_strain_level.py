#!/usr/bin/env python3
"""Record (or read) this session's strain tier.

    strain-level.sh <Healthy|Mid|High|Warning|Danger>   record a tier
    strain-level.sh --get                               print the current tier
    strain-level.sh --show                              print the whole state as JSON
    strain-level.sh <tier> --session <id>               name the session explicitly

WHY THE WRITER MATTERS
    A tier that is computed and then not written is a tier nobody carries. In an earlier
    build the value was read in three places and written by none, so it sat at its first
    value forever while the checks around it did their work. Then the writer was added --
    and defaulted to a different file from the one the hooks used, so recording a tier
    still changed nothing visible. Both failures look identical from the outside: the
    number never moves.

    So: this command and the hooks resolve the state location through exactly one
    function, and this command prints which session it wrote to. If that is not the
    session you meant, you can see it immediately instead of discovering it a week later.
"""
import argparse, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _strain_common import (TIERS, state_dir, session_path, load, save, blank,
                            now_iso, resolve_sid)
import _strain_context as ctxmod


def main(argv):
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("tier", nargs="?", default=None)
    ap.add_argument("--state-dir", default=None)
    ap.add_argument("--session", default=None)
    ap.add_argument("--get", action="store_true")
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    args, _ = ap.parse_known_args(argv)

    sdir = state_dir(args.state_dir)
    sid, how = resolve_sid(sdir, args.session)
    path = session_path(sdir, sid)
    st = load(path)

    if args.show:
        view = dict(st)
        view["_state_file"] = path
        view["_session_resolved_by"] = how
        line = ctxmod.describe(st.get("ctx") or {})
        if line:
            view["_context"] = line
        sys.stdout.write(json.dumps(view, indent=1) + "\n")
        return 0

    if args.get or args.tier == "--get":
        sys.stdout.write(str(st.get("last", "Healthy")))
        return 0

    if args.tier is None:
        sys.stderr.write("usage: strain-level.sh <%s> | --get | --show\n" % "|".join(TIERS))
        return 2
    if args.tier not in TIERS:
        # A typo must not become a reading.
        sys.stderr.write("unknown tier %r; expected one of %s\n"
                         % (args.tier, ", ".join(TIERS)))
        return 2

    if not st:
        st = blank(sid)
    st["last"] = args.tier
    st["updated"] = now_iso()
    if not save(path, st):
        sys.stderr.write("could not write state to %s\n" % path)
        return 1

    sys.stdout.write(args.tier)
    if not args.quiet:
        sys.stderr.write("\nrecorded for session %s (resolved by %s) -> %s\n"
                         % (sid or "unknown", how, path))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
