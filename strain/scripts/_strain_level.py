#!/usr/bin/env python3
"""Record (or read) this session's strain tier.

    strain-level.sh <Healthy|Mid|High|Warning|Danger>   record a tier
    strain-level.sh UNMEASURED                          record that nothing was measured
    strain-level.sh <tier> --ctx-used N --ctx-source '<where>' [--ctx-provenance
                    host-reported|agent-estimated]      feed the host's own number
    strain-level.sh UNMEASURED --no-source --checked '<places looked>'
                                                        record that no number exists
    strain-level.sh --get                               print the current tier
    strain-level.sh --show                              print the whole state as JSON
    strain-level.sh <tier> --session <id>               name the session explicitly

A record needs a session key (0.8.0): --session, STRAIN_SESSION (printed in every tick,
and exported into the agent's shell where the host allows it) or the host's own shell
variable. Without one, a record is REFUSED with a list of candidate sessions -- it never
lands in a guessed one. --get / --show may guess, and say so.

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
from _strain_common import (TIERS, RECORDABLE, state_dir, session_path, load, save,
                            blank, now_iso, resolve_sid, resolve_for_write, settle_window,
                            why_unsaved, write_hint, state_lock)
import _strain_context as ctxmod


def _main(argv, lock_holder):
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("tier", nargs="?", default=None)
    ap.add_argument("--state-dir", default=None)
    ap.add_argument("--session", default=None)
    ap.add_argument("--get", action="store_true")
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    # 0.6.0 FEED DOOR: on a host strain cannot parse, the agent hands over the host's
    # OWN usage reading. Provenance rides along and the mode says "agent-fed" -- a fed
    # number is honest input, never dressed up as a measurement strain made itself.
    ap.add_argument("--ctx-used", type=int, default=None)
    ap.add_argument("--ctx-source", default=None)
    # 0.8.0 B3: where a fed number came from -- read from the host's own interface, or
    # the agent's own estimate. Optional, so a 0.6.0/0.7.0 feed still works.
    ap.add_argument("--ctx-provenance", default=None,
                    choices=["host-reported", "agent-estimated"])
    # 0.8.0 B3: the other way to end the "no source" checklist -- a visible record that
    # the agent looked and found nothing, instead of a silence.
    ap.add_argument("--no-source", action="store_true")
    ap.add_argument("--checked", default=None)
    args, _ = ap.parse_known_args(argv)

    sdir = state_dir(args.state_dir)
    reading = args.show or args.get or args.tier == "--get"
    if reading:
        sid, how = resolve_sid(sdir, args.session)
        if how.startswith("guessed"):
            sys.stderr.write("session %s %s -- pass --session or STRAIN_SESSION to be sure\n"
                             % (sid, how))
    else:
        sid, how, refusal = resolve_for_write(sdir, args.session, "strain-level.sh", argv)
        if refusal:
            sys.stderr.write(refusal)
            return 2
    path = session_path(sdir, sid)
    lock = state_lock(path)
    lock.__enter__()                   # 0.7.0: one read-modify-write at a time
    lock_holder.append(lock)
    st = load(path)

    if args.ctx_used is not None:
        if args.ctx_used <= 0:
            sys.stderr.write("--ctx-used must be a positive token count\n")
            return 2
        if not (args.ctx_source or "").strip():
            sys.stderr.write("--ctx-source is required with --ctx-used: say where the "
                             "number was read (e.g. 'host runtime log') -- an unsourced "
                             "reading cannot be trusted later\n")
            return 2
        if not st:
            st = blank(sid)
        # 0.7.0: the feed is an ANCHOR the tick scores and keeps -- it records what
        # would void it (a later compaction, a model switch) and the transcript size
        # now, so only bytes appended after the feed are ever added.
        prev = st.get("ctx") if isinstance(st.get("ctx"), dict) else {}
        tp = str(prev.get("transcript") or "")
        try:
            anchor = os.path.getsize(tp) if tp else None
        except Exception:
            anchor = None
        fed = {"mode": "agent-fed", "tokens": int(args.ctx_used),
               "source": args.ctx_source.strip(),
               "provenance": args.ctx_provenance or "",
               "fedTokens": int(args.ctx_used),
               "fedCompactions": int(st.get("compactions", 0) or 0),
               "fedModel": str(st.get("model") or ""), "model": str(st.get("model") or ""),
               "anchorBytes": anchor, "transcript": tp,
               "baseline": prev.get("baseline"),
               "fedAt": now_iso()}
        # 0.8.0 A1: the same denominator decision as the tick -- never another host's.
        fed, _look = settle_window(fed, sdir, st.get("substrate", ""))
        st["ctx"] = fed
        st["updated"] = now_iso()
        if not save(path, st):
            sys.stderr.write("could not write state: %s%s\n" % (why_unsaved(path), write_hint(path)))
            return 1
        sys.stdout.write("fill %.1f%% — agent-fed: %s of %s tokens (window: %s)\n"
                         % (fed["pct"], "{:,}".format(int(args.ctx_used)),
                            "{:,}".format(int(fed["limit"])), fed["limitSource"]))
        sys.stderr.write("source: %s · session %s (resolved by %s) -> %s\n"
                         % (args.ctx_source.strip(), sid or "unknown", how, path))
        if args.tier is None:
            return 0

    if args.no_source:
        if not (args.checked or "").strip():
            sys.stderr.write("--no-source needs --checked '<the places you looked>' -- the "
                             "record is only worth something if it says where\n")
            return 2
        if not st:
            st = blank(sid)
        st["noSource"] = {"checked": args.checked.strip(), "at": now_iso()}
        st["updated"] = now_iso()
        if not save(path, st):
            sys.stderr.write("could not write state: %s%s\n" % (why_unsaved(path), write_hint(path)))
            return 1
        sys.stderr.write("recorded: no context source on this host (checked: %s)\n"
                         % args.checked.strip())
        if args.tier is None:
            return 0

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
        sys.stderr.write("usage: strain-level.sh <%s> | --get | --show\n" % "|".join(RECORDABLE))
        return 2
    if args.tier not in RECORDABLE:
        # A typo must not become a reading.
        sys.stderr.write("unknown tier %r; expected one of %s\n"
                         % (args.tier, ", ".join(RECORDABLE)))
        return 2

    if not st:
        st = blank(sid)
    st["last"] = args.tier
    st["updated"] = now_iso()
    if not save(path, st):
        sys.stderr.write("could not write state: %s%s\n" % (why_unsaved(path), write_hint(path)))
        return 1

    sys.stdout.write(args.tier)
    if not args.quiet:
        sys.stderr.write("\nrecorded for session %s (resolved by %s) -> %s\n"
                         % (sid or "unknown", how, path))
    return 0


def main(argv):
    held = []
    try:
        return _main(argv, held)
    finally:
        for lk in held:
            lk.__exit__()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
