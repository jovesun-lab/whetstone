#!/usr/bin/env python3
"""Sign a session -- declare WHO is working it, and optionally which book it belongs to.

    strain-sign.sh --agent ana                          name this session's agent
    strain-sign.sh --agent ana --ledger ./Log.strain    ...and join a project ledger

Why signing exists: one machine, one state dir, more than one agent. The wrap marker
is a single file, so before 0.5.0 agent A finishing a piece of work would reset agent
B's live counters at B's next session start -- B's real strain, wiped by someone
else's finish line. The path cannot tell agents apart (two windows on one project
look identical to the hooks), so identity is DECLARED: an agent signs after it knows
who it is, the wrap it later marks carries that signature, and a signed marker resets
only sessions carrying the same signature. An unsigned marker behaves exactly as
before -- signing is opt-in, one command, and only matters once a second agent shows
up.

The ledger is the optional account book that comes with signing: an append-only JSONL
file (suggest `Log.strain` at the project root, gitignored) that receives one
`boot-sign` row now and one `wrap` row when this session marks its wrap. It records
the project's chain of sessions -- who worked, when, wrapped how -- without ever
inheriting counters across sessions (one session, one measurement, unchanged).
"""
import argparse, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _strain_common import (state_dir, session_path, load, save, now_iso,
                            resolve_sid, ledger_append)


def main(argv):
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--agent", default=None)
    ap.add_argument("--ledger", default=None)
    ap.add_argument("--session", default=None)
    ap.add_argument("--state-dir", default=None)
    args, _ = ap.parse_known_args(argv)

    agent = args.agent or os.environ.get("STRAIN_AGENT")
    if not agent:
        sys.stderr.write("usage: strain-sign.sh --agent <name> [--ledger <path>]\n")
        return 2

    sdir = state_dir(args.state_dir)
    sid, how = resolve_sid(sdir, args.session)
    if not sid:
        sys.stderr.write("no session to sign: no --session, no STRAIN_SESSION, and the "
                         "index knows nothing yet (a hook has to run once first)\n")
        return 2

    path = session_path(sdir, sid)
    st = load(path)
    st.setdefault("sid", sid)
    st["agent"] = agent
    ledger = args.ledger or str(st.get("ledger") or "")
    if args.ledger:
        ledger = os.path.abspath(args.ledger)
        st["ledger"] = ledger
    if not save(path, st):
        sys.stderr.write("could not write state to %s\n" % path)
        return 1

    note = ""
    if ledger:
        row = {"type": "boot-sign", "ts": now_iso(), "session": sid, "agent": agent}
        if ledger_append(ledger, row):
            note = " -- boot-sign row appended to %s" % ledger
        else:
            note = " -- WARNING: could not append to ledger %s" % ledger
    sys.stdout.write("signed %s (session %s, resolved via %s)%s\n"
                     % (agent, sid[:12], how, note))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
