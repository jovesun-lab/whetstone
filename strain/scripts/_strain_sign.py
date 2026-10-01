#!/usr/bin/env python3
"""Sign a session -- declare WHO is working it, and optionally which book it belongs to.

    strain-sign.sh --agent ana                          name this session's agent
    strain-sign.sh --agent ana --ledger ./Log.strain    ...and join a project ledger

Why signing exists: one machine, one state dir, more than one agent. The path cannot
tell agents apart (two windows on one project look identical to the hooks), so
identity is DECLARED: an agent signs after it knows who it is. Signing is opt-in, one
command, and only matters once a second agent or a second session shows up.

The ledger is the optional account book that comes with signing: an append-only JSONL
file (suggest `Log.strain` at the project root, gitignored) that receives one
`boot-sign` row now and one `wrap` row when this session stamps its wrap. It records
the project's chain of sessions -- who worked, when, wrapped how -- without ever
inheriting counters across sessions (one session, one measurement, unchanged).

0.8.0 RECEIPT (0.8.1: split in two): the first sign prints ONE plain sentence for the
user on stdout -- is strain on, how full is this conversation -- and the agent's receipt
on stderr: host, session, where the reading comes from and when, its mode, the window and
where THAT came from, whether the hooks are saving, whether THIS shell can write, the
ledger. `strain-sign.sh --receipt` reprints both. Relay the sentence to the user as is;
keep the details for troubleshooting.

0.7.0 PREVIOUS SESSION REPORT: the FIRST sign of a session with a ledger reads the
newest EARLIER session of the same agent in that ledger and prints one plain line --
its tool calls, compactions, errors escaped / caught, whether it wrapped (and when),
and whether it kept working after the wrap. Read only: nothing is carried over.
"""
import argparse, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _strain_common import (state_dir, session_path, load, save, now_iso, resolve_sid,
                            resolve_for_write, ledger_append_why, load_ledgers, save_ledgers,
                            ledger_rows, signals_of, state_lock, user_line, details_line,
                            why_unsaved, write_hint)


def _when(ts):
    """"MM-DD HH:MM" in this machine's local time: parse, convert, then format (slicing
    the string printed a UTC time as if it were local)."""
    from datetime import datetime
    s = str(ts or "")
    try:
        t = s.replace("Z", "+00:00")
        m = re.match(r"^(.*\d\d:\d\d:\d\d(?:\.\d+)?)([+-]\d\d)(\d\d)$", t)
        if m:
            t = "%s%s:%s" % m.groups()
        dt = datetime.fromisoformat(t)
        if dt.tzinfo is not None:
            dt = dt.astimezone()
        return dt.strftime("%m-%d %H:%M")
    except Exception:
        return s[5:10] + " " + s[11:16] if re.match(r"^\d{4}-\d\d-\d\dT\d\d:\d\d", s) else s


def previous_session_report(sdir, rows, agent, sid):
    """One plain line about the newest EARLIER session of the same agent in this ledger."""
    pred = ""
    for r in rows:
        if (r.get("type") == "boot-sign" and str(r.get("agent") or "") == agent
                and r.get("session") and r.get("session") != sid):
            pred = str(r["session"])        # file order == append order: last is newest
    if not pred:
        return "no earlier session — first session of %s in this ledger" % agent
    pst = load(session_path(sdir, pred))
    parts = []
    if pst:
        sig = signals_of(pst)
        comp = int(pst.get("compactions", 0) or 0)
        parts.append("%d tool calls" % int(pst.get("tick", 0) or 0))
        parts.append("%d compaction%s" % (comp, "" if comp == 1 else "s"))
        parts.append("errors %d escaped, %d caught"
                     % (sum(1 for x in sig if x.get("escaped")),
                        sum(1 for x in sig if not x.get("escaped"))))
    else:
        parts.append("its counts are not reachable from here")
    wraps = [r for r in rows if r.get("type") == "wrap" and str(r.get("session") or "") == pred]
    if not wraps:
        parts.append("not wrapped")
    else:
        w = wraps[-1]
        parts.append("wrapped %s%s" % (_when(w.get("ts")),
                                       " (with known loose ends)"
                                       if w.get("verdict") in ("WRAPPED-WITH-DEBT",
                                                               "CLEAN-WITH-DEBT") else ""))
        if pst and w.get("tick") is not None:
            after = int(pst.get("tick", 0) or 0) - int(w.get("tick") or 0)
            if after > 0:
                parts.append("worked on after the wrap (%d calls), not re-wrapped" % after)
    return "previous session (%s · %s): %s" % (agent, pred[:8], " · ".join(parts))

# ---- CHAT SURFACE, two registers (0.5.1) ---------------------------------------------
# stdout is USER-SURFACE: what a person reads -- Owner-form, plain words, no flags,
# no filesystem paths (the selftest asserts this stays true). stderr is
# AGENT-DIRECTED detail -- paths, resolution basis -- for the agent to consume and
# relay in plain words, never to paste raw into a chat.


def main(argv):
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--agent", default=None)
    ap.add_argument("--ledger", default=None)
    ap.add_argument("--session", default=None)
    ap.add_argument("--state-dir", default=None)
    ap.add_argument("--receipt", action="store_true")
    args, _ = ap.parse_known_args(argv)

    sdir = state_dir(args.state_dir)
    if args.receipt:
        # A read: may guess, and says so.
        sid, how = resolve_sid(sdir, args.session)
        if not sid:
            sys.stderr.write("no session known yet (a hook has to run once first)\n")
            return 2
        path = session_path(sdir, sid)
        st = load(path)
        st.setdefault("sid", sid)
        sys.stdout.write(user_line(st) + "\n")
        sys.stderr.write(details_line(st, path, _ledger_state(st)) + "\n")
        sys.stderr.write("details: session %s (via %s) · state %s\n" % (sid, how, path))
        return 0

    agent = args.agent or os.environ.get("STRAIN_AGENT")
    if not agent:
        sys.stderr.write("usage: strain-sign.sh --agent <name> [--ledger <path>] | --receipt\n")
        return 2

    # 0.8.0 A7: a sign names the session's agent -- it must be THIS session.
    sid, how, refusal = resolve_for_write(sdir, args.session, "strain-sign.sh", argv)
    if refusal:
        sys.stderr.write(refusal)
        return 2

    path = session_path(sdir, sid)
    # 0.8.0 (S5): one read-modify-write at a time -- the 0.7.0 lock covered the hooks and
    # the recorders but not the sign, so a sign racing parallel ticks could drop counts.
    with state_lock(path):
        st = load(path)
        st.setdefault("sid", sid)
        st["agent"] = agent
        first_sign = not st.get("signedAt")
        st.setdefault("signedAt", now_iso())
        # 0.5.1 ledger resolution: explicit --ledger > this session's state > the
        # per-agent durable registry (so a later session signs with no --ledger at
        # all). The registry is a convenience pointer, never identity, and never
        # lends across agents.
        ledger_how = "none"
        if args.ledger:
            ledger = os.path.abspath(args.ledger)
            ledger_how = "explicit"
        else:
            ledger = str(st.get("ledger") or "")
            if ledger:
                ledger_how = "session-state"
            else:
                ledger = str((load_ledgers(sdir).get(str(agent)) or {})
                             .get("ledger") or "")
                if ledger:
                    ledger_how = "registry"
        if ledger:
            st["ledger"] = ledger
        if not save(path, st):
            sys.stderr.write("could not write state: %s%s\n" % (why_unsaved(path), write_hint(path)))
            return 1

    book_note, report, why = "", "", ""
    if ledger:
        rows = ledger_rows(ledger)
        if not any(r.get("type") == "boot-sign" and r.get("session") == sid for r in rows):
            report = previous_session_report(sdir, rows, str(agent), sid)   # first sign only
        row = {"type": "boot-sign", "ts": now_iso(), "session": sid, "agent": agent}
        why = ledger_append_why(ledger, row)
        if not why:
            book_note = " · booked"
            save_ledgers(sdir, agent, ledger)
        else:
            book_note = " · WARNING: the book could not be written"
            report = ""
    sys.stdout.write("Strain · Owner: %s — signed%s\n" % (agent, book_note))
    if report:
        sys.stdout.write(report + "\n")
    if first_sign:
        # 0.8.1: the user's sentence on stdout (relay it as is); the details for the agent.
        sys.stdout.write(user_line(st) + "\n")
        sys.stderr.write(details_line(st, path,
                                      ("ledger booked" if not why else "ledger write FAILED")
                                      if ledger else "no ledger") + "\n")
    if why:
        sys.stderr.write("ledger not written: %s\n" % why)
    sys.stderr.write("details: session %s (via %s)%s\n"
                     % (sid[:12], how,
                        (" · ledger %s (via %s)" % (ledger, ledger_how))
                        if ledger else " · no ledger"))
    return 0


def _ledger_state(st):
    ledger = str(st.get("ledger") or "")
    if not ledger:
        return "no ledger"
    d = os.path.dirname(os.path.abspath(ledger))
    ok = os.path.isdir(d) and os.access(d, os.W_OK) and \
        (not os.path.exists(ledger) or os.access(ledger, os.W_OK))
    return "ledger writable" if ok else "ledger write FAILED"


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
