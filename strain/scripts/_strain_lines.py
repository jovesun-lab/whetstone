#!/usr/bin/env python3
"""A user's own lines at fill levels -- each printed once, when the session's fill crosses it (0.11.0).

strain's tiers and directives are fixed text. A team that wants its own words at a fill level
("save a checkpoint at 50%") writes them in an optional lines file; strain prints each line once
per session, on the tool call that crosses it, and adds the command that records the line's mark
when the line names one. With no file, strain behaves exactly as before.

    {"strain_lines": 1,
     "lines": [{"at": 50, "say": "save a checkpoint", "mark": "backup"},
               {"at": 70, "say": "begin the hand-off", "mark": "wrap-start"}]}

Where: STRAIN_LINES (a path) > <state dir>/lines.json. A file that is there but cannot be used is
said once per session by the tick -- a broken setting is never silent -- and no line is printed
from it. Pure functions: the caller passes the folder, the environment, the fill and what is passed.
"""
import json, os

VERSION = 1
MAX_SAY = 300
MAX_LINES = 20
# mark -> the strain-wrap.sh arguments that record it
MARKS = {"backup": "--backup", "wrap-start": "--start"}


def lines_path(sdir, environ):
    """STRAIN_LINES when set, else the state folder's lines.json."""
    p = str((environ or {}).get("STRAIN_LINES") or "").strip()
    return os.path.expanduser(p) if p else os.path.join(sdir, "lines.json")


def key(at):
    """A line's key in the session state (JSON keys are text), lossless: 50 and 50.0 -> "50",
    52.5 -> "52.5", 50.00001 -> "50.00001" -- two distinct values never share a key."""
    f = float(at)
    return "%d" % f if f.is_integer() else repr(f)


def load_lines(path):
    """(lines, lowest first, None) for a usable file; ([], None) when there is no file;
    ([], reason) when a file is there but cannot be used -- a link to a file that is gone counts
    as there: someone set it up."""
    if not os.path.lexists(path):
        return [], None
    try:
        with open(path) as f:
            raw = f.read()
    except Exception as ex:
        return [], "cannot be read (%s)" % ex.__class__.__name__
    try:
        doc = json.loads(raw)
    except Exception:
        return [], "not valid JSON"
    if not isinstance(doc, dict):
        return [], "not a JSON object"
    ver = doc.get("strain_lines")
    if isinstance(ver, bool) or ver != VERSION:
        return [], "strain_lines must be %d" % VERSION
    items = doc.get("lines")
    if not isinstance(items, list) or not items:
        return [], "lines must be a non-empty list"
    if len(items) > MAX_LINES:
        return [], "at most %d lines" % MAX_LINES
    out, seen = [], set()
    for i, it in enumerate(items):
        where = "line %d" % (i + 1)
        if not isinstance(it, dict):
            return [], "%s is not an object" % where
        at = it.get("at")
        if isinstance(at, bool) or not isinstance(at, (int, float)) or not (0 < at <= 100):
            return [], "%s: at must be a number above 0 and at most 100" % where
        if key(at) in seen:
            return [], "%s: at %s appears twice" % (where, key(at))
        seen.add(key(at))
        say = it.get("say")
        if not isinstance(say, str) or not say.strip():
            return [], "%s: say must be text" % where
        if "\n" in say or "\r" in say:
            return [], "%s: say must be one line" % where
        if len(say) > MAX_SAY:
            return [], "%s: say is over %d characters" % (where, MAX_SAY)
        mark = it.get("mark")
        if mark is not None and (not isinstance(mark, str) or mark not in MARKS):
            return [], "%s: mark must be one of %s" % (where, ", ".join(sorted(MARKS)))
        line = {"at": at, "say": say.strip()}
        if mark:
            line["mark"] = mark
        out.append(line)
    out.sort(key=lambda l: l["at"])
    return out, None


def due_line(lines, fill, crossed):
    """(the line to print or None, the ats passed now). The highest line at or below the fill that
    is not passed yet is printed; every line at or below the fill is passed with it, so a jump past
    two lines prints only the higher one. No trusted fill (None): nothing. A fill that falls and
    rises again prints nothing new -- `crossed` remembers."""
    if fill is None:
        return None, []
    crossed = crossed if isinstance(crossed, dict) else {}
    passed = [l["at"] for l in lines if l["at"] <= fill and key(l["at"]) not in crossed]
    if not passed:
        return None, []
    top = max(passed)
    return next(l for l in lines if l["at"] == top), passed
