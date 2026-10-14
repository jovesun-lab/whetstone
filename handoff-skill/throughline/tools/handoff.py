#!/usr/bin/env python3
"""
handoff.py — optional helper for the Task-Track + Handoff skill (Throughline 0.3).

This script is OPTIONAL. The skill is fully usable as a pure prompt in any agent.
This helper only exists for environments that *can* run code (Claude Code, Cursor,
Codex, a local shell) and want the mechanizable half done deterministically.

Division of labour (on purpose):
  - The PROMPT does the judgement half: read the session, decide what matters,
    summarize, redact, write the prose. Only a model can do that.
  - THIS SCRIPT does the countable half: scaffold a blank handoff from the shared
    template, validate a finished one, and look over a session-start brief.

It never summarizes — so it never competes with the prompt, it just checks the skeleton.

Single source of truth: the rules are NOT hardcoded here. They are READ at runtime from
rules/task-rules.json — the sections, the MAIN entry, the subtask statuses, the row
references, the brief's ID rule. The template holds the same sections (a test keeps the
two equal). Change the rule file, the checks follow.

Zero dependencies: Python 3 standard library only. Runs anywhere python3 exists.

Usage:
  python3 handoff.py new                    # print a blank handoff to stdout
  python3 handoff.py new  > HANDOFF.md      # ...or redirect to a file
  python3 handoff.py check HANDOFF.md       # validate a finished handoff
  python3 handoff.py check -                # validate from stdin
  python3 handoff.py brief BRIEF.md         # warn on IDs in a session-start brief that carry no words
  add --rules <file> to check or brief to read another rule file (default: ../rules/task-rules.json)
"""

import argparse
import json
import os
import re
import sys

# Force UTF-8 output so the ⭐️ in the template/messages can't crash the script on a
# non-UTF-8 console (e.g. Windows GBK/cp936), where printing it would otherwise raise
# UnicodeEncodeError. Best-effort, stdlib-only — keeps the zero-dependency promise.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
# templates/ and rules/ are siblings of tools/
TEMPLATE = os.path.normpath(os.path.join(HERE, "..", "templates", "handoff.template.md"))
RULES = os.path.normpath(os.path.join(HERE, "..", "rules", "task-rules.json"))

MAIN_MARKER = "⭐"  # ⭐️ — the goal-anchor marker; exactly one per handoff.

# A goal anchor is matched STRUCTURALLY — a line that *starts* with the marker (after any
# leading markdown like '#', '-', '>') — not by counting the glyph anywhere in the document.
# This is deliberate: a prose line such as "this feature is worth 5⭐" must NOT inflate the
# count. Three equivalent forms are accepted, so the marker survives emoji-unfriendly tools:
#   ⭐️ ...            (the at-a-glance human marker)
#   [MAIN] ...        (plain-text equivalent — portable, renders everywhere)
#   main_goal: true   (explicit frontmatter form)
MAIN_LINE = re.compile(r"^[\s#>*\-]*(?:⭐|\[MAIN\]|main_goal\s*:\s*true)", re.IGNORECASE)

# Patterns that should never appear in a shareable handoff. This is a HEURISTIC BACKSTOP, not
# a guarantee — a regex can never catch every secret, which is why a hit is a WARN and never a
# PASS. Real redaction is the prompt's responsibility, with human review on top.
SECRET_PATTERNS = [
    (r"sk-[A-Za-z0-9]{16,}", "OpenAI-style API key (sk-...)"),
    (r"AKIA[0-9A-Z]{12,}", "AWS access key id (AKIA...)"),
    (r"ghp_[A-Za-z0-9]{20,}", "GitHub token (ghp_...)"),
    (r"xox[baprs]-[A-Za-z0-9-]{10,}", "Slack token (xox.-...)"),
    (r"AIza[0-9A-Za-z_\-]{30,}", "Google API key (AIza...)"),
    (r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]+", "JWT"),
    (r"(?i)\bBearer\s+[A-Za-z0-9._\-]{20,}", "Bearer token"),
    (r"-----BEGIN [A-Z ]*PRIVATE KEY-----", "private key block"),
]

# Inline credential like `password = ...` — but only flag a real LITERAL value. A safe lookup
# (os.getenv / process.env / ${VAR}) or an obvious placeholder (***, <...>, REDACTED, "your-…")
# is not a leak, so it must not trip the WARN (that was a false-positive source).
INLINE_CRED = re.compile(
    r"""(?i)\b(password|passwd|secret|api[_-]?key|token|auth[_-]?token)\s*[:=]\s*['"]?([^\s'"]+)""")
SAFE_VALUE = re.compile(
    r"""(?i)(os\.getenv|process\.env|getenv|environ|\$\{|<[^>]+>|\*{3,}|redact|x{3,}|your[_-]|"""
    r"""placeholder|example|changeme|none|null|true|false|\.\.\.)""")

COMMENT = re.compile(r"<!--.*?-->", re.S)
ITEM = re.compile(r"^(?:[-*]|\d+[.)])\s+(.*\S)\s*$")
VERDICT_TAIL = re.compile(r"^(.*?)\s+[—–-]+\s+(\S+)\s*$")


def load_rules(path):
    """Read the rule file — the one source of every check below."""
    if not os.path.exists(path):
        sys.exit("error: cannot find the rule file at %s\n"
                 "       run this script from inside the skill folder so it can locate "
                 "rules/task-rules.json, or pass --rules <file>" % path)
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except ValueError as e:
        sys.exit("error: the rule file at %s is not valid JSON: %s" % (path, e))


def read_input(path):
    if path == "-":
        return sys.stdin.read(), "<stdin>"
    if not os.path.exists(path):
        sys.exit("error: no such file: %s" % path)
    with open(path, encoding="utf-8") as fh:
        return fh.read(), path


def strip_comments(text):
    """Blank out HTML comments, keeping their line breaks so line numbers stay true."""
    return COMMENT.sub(lambda m: "\n" * m.group(0).count("\n"), text)


def _norm(s):
    return re.sub(r"\s+", " ", s).strip().lower()


def _key(s):
    """A name without its leading marker or emoji: '⭐️ Goal' -> 'goal'."""
    return re.sub(r"^[^a-z0-9]+", "", _norm(s))


def _clean(s):
    return _norm(s).rstrip(" .:;")


def cmd_new(_args):
    """Print a blank handoff scaffold (the template, comments and all)."""
    with open(TEMPLATE, encoding="utf-8") as fh:
        sys.stdout.write(fh.read())
    return 0


def section_names_of(heading, names, alias):
    """The sections a '## ' heading counts as: by NAME (its text after any marker STARTS with the
    section's name — never a word inside another heading) or by the alias at its END
    ('· Throughline: <name>[ · <name>]'), so a project keeps its own heading names."""
    found, head = [], heading
    if alias and alias in heading:
        head, _, tail = heading.partition(alias)
        for part in tail.split("·"):
            k = _key(part)
            found += [n for n in names if k and k.startswith(_key(n))]
    k = _key(head)
    found += [n for n in names if k and k.startswith(_key(n))]
    return list(dict.fromkeys(found))


def split_sections(text, rules):
    """Map each section found to its body: the lines under its '## ' heading, up to the next
    '#' or '##' heading ('###' entries, such as a MAIN in Done, stay inside the body)."""
    names = [s["name"] for s in rules["handoff"]["sections"]]
    alias = rules["handoff"].get("alias", "").strip()
    bodies, current = {}, []
    for ln in text.splitlines():
        m = re.match(r"^(#{1,2})\s+(.*\S)\s*$", ln)
        if m:
            current = section_names_of(m.group(2), names, alias) if len(m.group(1)) == 2 else []
            for name in current:
                bodies.setdefault(name, [])
            continue
        for name in current:
            bodies[name].append(ln)
    return {k: "\n".join(v).strip() for k, v in bodies.items()}


def by_role(rules, role):
    for s in rules["handoff"]["sections"]:
        if s.get("role") == role:
            return s["name"]
    return None


def items_of(body):
    """Top-level list items ('- x', '* x', '1. x'), not indented continuation lines."""
    return [m.group(1) for ln in body.splitlines() for m in [ITEM.match(ln)] if m]


def has_row(text, rr):
    return bool(re.search(rr["id_pattern"], text) or re.search(rr["path_pattern"], text))


def item_text_and_ref(item, rr):
    """Split ' · <row ID or path>' off the end of an item, if it is there."""
    head, sep, tail = item.rpartition(" · ")
    if sep and has_row(tail, rr):
        return head.strip(), tail.strip()
    return item.strip(), ""


def human_words_re(rules):
    hw = rules["handoff"]["human_words"]
    quotes = hw.get("quotes", ["\""])
    closing = {"「": "」", "“": "”"}
    alts = "|".join(re.escape(q) + r"[^" + re.escape(closing.get(q, q)) + r"]+" + re.escape(closing.get(q, q))
                    for q in quotes)
    return re.compile(re.escape(hw["label"]) + r"\s*(?:" + alts + ")")


def parse_done(body, rules):
    """The MAIN entries of Done (### MAIN[ <id>]: <title> — <verdict>), their 🔸 subtasks, any
    zero-MAIN line, and the lines that sit under no MAIN."""
    h = rules["handoff"]
    me = h["main_entry"]
    entry = re.compile(r"^" + "#" * me["heading_level"] + r"\s+" + re.escape(me["word"])
                       + r"\b(?:\s+([^\s:]+))?\s*:\s*(.*?)\s*$")
    icon = rules["icons"]["subtask"]["icon"]
    sub = re.compile(r"^[-*]\s*" + re.escape(icon) + r"\s*(.*?)\s*$")
    zero_token = h["zero_main"]["token"].lower()
    mains, zero, loose, cur = [], [], [], None
    for ln in body.splitlines():
        s = ln.strip()
        if not s:
            continue
        m = entry.match(s)
        if m:
            t = VERDICT_TAIL.match(m.group(2))
            title, verdict = (t.group(1).strip(), t.group(2)) if t else (m.group(2).strip(), None)
            cur = {"id": m.group(1), "title": title, "verdict": verdict, "subtasks": []}
            mains.append(cur)
            continue
        if s.lower().startswith(zero_token):
            zero.append(s)
            cur = None
            continue
        m = sub.match(s)
        if m and cur is not None:
            cur["subtasks"].append(m.group(1))
        elif cur is None:
            loose.append(s)
    return mains, zero, loose


def check_done(sections, rules, errors):
    h = rules["handoff"]
    done = sections.get(by_role(rules, "done"))
    if done is None:
        return []
    mains, zero, loose = parse_done(done, rules)
    words = human_words_re(rules)
    rr = h["row_ref"]
    statuses = h["subtask_status"]
    marker = statuses.get("carried", {}).get("marker", "→")
    if not mains:
        if zero:
            if not any(words.search(z) for z in zero):
                errors.append("zero-MAIN needs the human's own words: '%s · human: \"<their words>\"'"
                              % h["zero_main"]["token"])
        else:
            errors.append("Done lists no MAIN entry ('### MAIN: <frozen title> — <verdict>') and no "
                          "zero-MAIN declaration on the human's words — work belongs to a MAIN")
        return mains
    if loose:
        errors.append("Done has lines under no MAIN entry (first: '%s') — put them under their MAIN" % loose[0])
    for mn in mains:
        title = mn["title"]
        if mn["verdict"] not in h["verdicts"]:
            errors.append("MAIN '%s' has no verdict — end its line with ' — %s'" % (title, " | ".join(h["verdicts"])))
        if not mn["subtasks"]:
            errors.append("MAIN '%s' lists no 🔸 subtask — every MAIN is broken into subtasks" % title)
        for st in mn["subtasks"]:
            parts = [p.strip() for p in st.split(" · ")]
            name = parts[0]
            rest = " · ".join(parts[1:])
            status = rest.split()[0].lower() if rest else ""
            if status not in statuses:
                errors.append("subtask '%s' (MAIN '%s') has no status — %s" % (name, title, " | ".join(statuses)))
                continue
            if status == "carried":
                dest = rest.partition(marker)[2]
                if not (marker in rest and has_row(dest, rr)):
                    errors.append("subtask '%s' is carried but names no destination — 'carried %s <row ID or file path>'"
                                  % (name, marker))
            if status == "dropped" and not words.search(rest):
                errors.append("subtask '%s' is dropped without the human's words — 'dropped · human: \"<their words>\"'"
                              % name)
            if mn["verdict"] == "LANDED" and status != "done":
                errors.append("MAIN '%s' is LANDED but subtask '%s' is %s — LANDED needs every subtask done"
                              % (title, name, status))
    return mains


def check_machine_verdicts(sections, rules, mains, errors):
    """Machine fields carries a generated copy of Done's verdicts; the two must agree."""
    body = sections.get(by_role(rules, "machine"))
    if body is None:
        return
    line = re.compile(r"^[-*]\s*verdict\b(?:\s+([^\s:]+))?\s*:\s*(.*?)\s*$", re.I)
    copies = []
    for ln in body.splitlines():
        m = line.match(ln.strip())
        if m:
            t = VERDICT_TAIL.match(m.group(2))
            copies.append((m.group(1), (t.group(1) if t else m.group(2)).strip(), t.group(2) if t else None))
    seen = set()
    for cid, ctitle, cverdict in copies:
        match = next((mn for mn in mains if cid and mn["id"] == cid), None) or \
            next((mn for mn in mains if _norm(mn["title"]) == _norm(ctitle)), None)
        if match is None:
            errors.append("Machine fields has a verdict for '%s' but Done has no such MAIN" % ctitle)
            continue
        seen.add(id(match))
        if cverdict != match["verdict"]:
            errors.append("the verdict for '%s' disagrees — Machine fields says %s, Done says %s (Done is the home)"
                          % (match["title"], cverdict, match["verdict"]))
    for mn in mains:
        if id(mn) not in seen:
            errors.append("MAIN '%s' has no verdict line in Machine fields (a copy of Done)" % mn["title"])


def check_rows(sections, rules, errors):
    """Every item of the row-ref blocks (next actions, rulings not yet home) points at its row."""
    rr = rules["handoff"]["row_ref"]
    for s in rules["handoff"]["sections"]:
        if s.get("block") not in rr["blocks"] or s["name"] not in sections:
            continue
        body = sections[s["name"]]
        if _clean(body) == rr["none_word"]:
            continue
        items = items_of(body)
        if not items:
            errors.append("'%s' has no items — list them, each ending with ' · <row ID or file path>', or write '%s'"
                          % (s["name"], rr["none_word"]))
        for it in items:
            if not item_text_and_ref(it, rr)[1]:
                errors.append("'%s' item has no row — end it with ' · <row ID or file path>': %s" % (s["name"], it))


def check_goal(sections, rules, errors):
    """The ⭐️ Goal is a proposal, and it is the first Next action — not a second list."""
    g = rules["handoff"].get("goal_is_first_next_action")
    if not g:
        return
    goal, nxt = sections.get(by_role(rules, g["goal"])), sections.get(by_role(rules, g["next"]))
    if not goal or not nxt:
        return
    goal_line = next((ln.strip() for ln in goal.splitlines() if ln.strip()), "")
    items = items_of(nxt)
    if not goal_line or not items:
        return
    first = item_text_and_ref(items[0], rules["handoff"]["row_ref"])[0]
    if _clean(goal_line) != _clean(first):
        errors.append("the ⭐️ Goal is not the first Next action — Goal: '%s' · Next actions #1: '%s'" % (goal_line, first))


def cmd_check(args):
    """Validate a finished handoff against the rule file."""
    rules = load_rules(args.rules)
    raw, label = read_input(args.path)
    text = strip_comments(raw)
    sections = split_sections(text, rules)
    errors, warnings = [], []

    # 1. Every required section present — by name or by alias, never by a word inside another heading.
    for s in rules["handoff"]["sections"]:
        if s["name"] not in sections:
            errors.append("missing section: '## %s'" % s["name"])

    # 2. Exactly one MAIN goal anchor — counted STRUCTURALLY (lines that START with the
    #    marker), never by counting the glyph anywhere, so a body line like "worth 5⭐"
    #    cannot inflate the count. ⭐️ / [MAIN] / `main_goal: true` are all accepted.
    main_count = sum(1 for ln in text.splitlines() if MAIN_LINE.match(ln))
    if main_count == 0:
        errors.append("no goal anchor: expected exactly one line starting with %s or [MAIN] "
                      "(or a 'main_goal: true' frontmatter line), found none" % MAIN_MARKER)
    elif main_count > 1:
        errors.append("multiple goal anchors: found %d anchored markers, expected exactly one"
                      % main_count)

    # 3. Done: a verdict and 🔸 subtasks per MAIN, the three ways a subtask leaves, LANDED only
    #    when every subtask is done, zero-MAIN only on the human's words.
    mains = check_done(sections, rules, errors)

    # 4. Machine fields' verdicts are a copy of Done's.
    check_machine_verdicts(sections, rules, mains, errors)

    # 5. Next actions and rulings not yet home each point at a durable row.
    check_rows(sections, rules, errors)

    # 6. The Goal is Next actions #1.
    check_goal(sections, rules, errors)

    # 7. The Re-derive section must carry actual re-derivation CONTENT, not just the word.
    #    Still a WARN: concreteness is a judgement call the human owns; this only catches the
    #    obviously-empty case.
    rd = sections.get(by_role(rules, "rederive"), "")
    rd_words = len(re.findall(r"\w+", rd))
    rd_cue = re.search(
        r"(?i)\b(re-?run|re-?read|re-?check|re-?confirm|re-?verify|verify|confirm|compare|"
        r"reconcile|against|git|test|build|diff|spec|issue|\bpr\b|file|doc)", rd)
    if rd_words < 4 or not rd_cue:
        warnings.append("'Re-derive on pickup' section is thin — name WHAT to reconcile against "
                        "and HOW (e.g. 're-run the tests', 're-read the spec', 're-confirm the "
                        "figures'), not just the word 're-derive'")

    # 8. Secret sweep (WARN backstop — see SECRET_PATTERNS; the prompt owns real redaction).
    for pat, why in SECRET_PATTERNS:
        if re.search(pat, raw):
            warnings.append("possible leaked secret (%s) — redact before sharing" % why)
    for m in INLINE_CRED.finditer(raw):
        val = m.group(2)
        if len(val) >= 6 and not SAFE_VALUE.search(val):
            warnings.append("possible inline credential (%s=…) — redact, or use an env lookup / "
                            "placeholder" % m.group(1))
            break

    for w in warnings:
        print("WARN  %s" % w)
    for e in errors:
        print("FAIL  %s" % e)
    if errors:
        print("\n%s: %d problem(s) — handoff not ready." % (label, len(errors)))
        return 1
    if warnings:
        print("\n%s: structure OK, %d warning(s) to review." % (label, len(warnings)))
        return 0
    print("%s: OK — every section present, one goal anchor, every MAIN closed by the rules." % label)
    return 0


def cmd_brief(args):
    """Warn on ID-like tokens in a session-start brief that carry no words saying what they are.
    Detection after the fact: whether the human can act on the brief stays the human's test."""
    rules = load_rules(args.rules)
    raw, label = read_input(args.path)
    b = rules["brief"]
    token = re.compile(b["id_token_pattern"])
    warnings = []
    for n, ln in enumerate(strip_comments(raw).splitlines(), 1):
        ids = token.findall(ln)
        if not ids:
            continue
        words = re.findall(r"[^\W\d_]+(?:['’-][^\W\d_]+)*", token.sub(" ", ln))
        if len(words) < b["min_words"]:
            warnings.append("line %d: %s — an ID never stands alone; say what it is: %s"
                            % (n, ", ".join(ids), ln.strip()))
    for w in warnings:
        print("WARN  %s" % w)
    if warnings:
        print("\n%s: %d line(s) where an ID carries no words." % (label, len(warnings)))
    else:
        print("%s: OK — every ID carries its words." % label)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Scaffold or validate a handoff document, or look over a session-start brief (optional helper).")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_new = sub.add_parser("new", help="print a blank handoff scaffold to stdout")
    p_new.set_defaults(func=cmd_new)

    p_check = sub.add_parser("check", help="validate a finished handoff")
    p_check.add_argument("path", help="path to the handoff .md, or - for stdin")
    p_check.add_argument("--rules", default=RULES, help="the rule file (default: ../rules/task-rules.json)")
    p_check.set_defaults(func=cmd_check)

    p_brief = sub.add_parser("brief", help="warn on IDs in a session-start brief that carry no words")
    p_brief.add_argument("path", help="path to the brief .md, or - for stdin")
    p_brief.add_argument("--rules", default=RULES, help="the rule file (default: ../rules/task-rules.json)")
    p_brief.set_defaults(func=cmd_brief)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
