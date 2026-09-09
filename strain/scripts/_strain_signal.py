#!/usr/bin/env python3
"""Record a hard signal for this session -- the accountability half of strain v2.

    strain-signal.sh <kind> --caught        an error caught in-cycle and fixed pre-delivery
    strain-signal.sh <kind> --escaped       an error that reached the user or shipped work
    strain-signal.sh --list                 print this session's signals
    strain-signal.sh <kind> --escaped --session <id>

`kind` is a short free-form class name: "factual-error", "regression", "self-revert",
"stale-read" -- whatever names the failure. The class matters because REPEATS of one
class earn a pattern note.

WHY CAUGHT AND ESCAPED ARE DIFFERENT
    Hard signals are ABSOLUTE -- a user-caught error counts the same on any window size;
    capacity never dilutes accountability. But v1 could only add, so three caught-and-
    fixed errors read the same as three shipped ones and the tier ratcheted to Danger at
    33% fill (fixture, 2026-08-15). A caught-and-fixed error is a working immune system:
    it is recorded here, it feeds the pattern note, and it does NOT move the tier. Only
    ESCAPED signals floor the tier (1 -> High, 2+ -> Warning; with fill already past the
    Warning band, an escaped signal is what justifies Danger).
"""
import argparse, json, sys, os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _strain_common import (state_dir, session_path, load, save, blank, now_iso,
                            resolve_sid, signals_of, signal_floor, pattern_note,
                            floor_tier)


def main(argv):
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("kind", nargs="?", default=None)
    ap.add_argument("--caught", action="store_true")
    ap.add_argument("--escaped", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--state-dir", default=None)
    ap.add_argument("--session", default=None)
    args, _ = ap.parse_known_args(argv)

    sdir = state_dir(args.state_dir)
    sid, how = resolve_sid(sdir, args.session)
    path = session_path(sdir, sid)
    st = load(path) or blank(sid)

    if args.list:
        sys.stdout.write(json.dumps(signals_of(st), indent=1) + "\n")
        return 0

    if not args.kind:
        sys.stderr.write("usage: strain-signal.sh <kind> --caught|--escaped | --list\n")
        return 2
    if args.caught == args.escaped:
        # Force the caller to say which it was: the distinction IS the feature, and a
        # default would quietly erase it.
        sys.stderr.write("say whether it escaped: --caught (fixed pre-delivery) or"
                         " --escaped (reached the user / shipped work)\n")
        return 2

    sig = {"ts": now_iso(), "kind": str(args.kind), "escaped": bool(args.escaped)}
    st.setdefault("signals", [])
    if not isinstance(st["signals"], list):
        st["signals"] = []
    st["signals"].append(sig)

    floor = signal_floor(st)
    if floor:
        st["last"] = floor_tier(st.get("last", "Healthy"), floor)
    st["updated"] = now_iso()
    if not save(path, st):
        sys.stderr.write("could not write state to %s\n" % path)
        return 1

    bits = ["recorded %s signal '%s' for session %s (resolved by %s)"
            % ("ESCAPED" if sig["escaped"] else "caught", sig["kind"],
               sid or "unknown", how)]
    if floor:
        bits.append("tier floored to at least %s (escaped signals are absolute)" % floor)
    note = pattern_note(st)
    if note:
        bits.append(note)
    sys.stdout.write("\n".join(bits) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
