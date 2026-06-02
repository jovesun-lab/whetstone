#!/usr/bin/env python3
"""
handoff.py — optional helper for the Task-Track + Handoff skill.

This script is OPTIONAL. The skill is fully usable as a pure prompt in any agent.
This helper only exists for environments that *can* run code (Claude Code, Cursor,
Codex, a local shell) and want the mechanizable half done deterministically.

Division of labour (on purpose):
  - The PROMPT does the judgement half: read the session, decide what matters,
    summarize, redact, write the prose. Only a model can do that.
  - THIS SCRIPT does the countable half: scaffold a blank handoff from the shared
    template, and validate a finished one (sections present, exactly one MAIN goal
    anchor, a re-derive note, and a warning sweep for obvious secrets).

It never summarizes — so it never competes with the prompt, it just checks the skeleton.

Single source of truth: the list of required sections is NOT hardcoded here.
It is READ from templates/handoff.template.md at runtime, so the prompt and this
validator can never drift on structure. Change the template, the checks follow.

Zero dependencies: Python 3 standard library only. Runs anywhere python3 exists.

Usage:
  python3 handoff.py new                 # print a blank handoff to stdout
  python3 handoff.py new  > HANDOFF.md   # ...or redirect to a file
  python3 handoff.py check HANDOFF.md    # validate a finished handoff
  python3 handoff.py check -             # validate from stdin
"""

import argparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# templates/ is a sibling of tools/
TEMPLATE = os.path.normpath(os.path.join(HERE, "..", "templates", "handoff.template.md"))

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


def read_template_sections(path=TEMPLATE):
    """Extract the required '## ' section headings from the shared template.
    This is what makes the validator and the prompt share one source of truth."""
    if not os.path.exists(path):
        sys.exit("error: cannot find the shared template at %s\n"
                 "       run this script from inside the skill folder so it can "
                 "locate templates/handoff.template.md" % path)
    sections = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            m = re.match(r"^##\s+(.*\S)\s*$", line)
            if m:
                sections.append(m.group(1).strip())
    return sections


def cmd_new(_args):
    """Print a blank handoff scaffold (the template, comments and all)."""
    with open(TEMPLATE, encoding="utf-8") as fh:
        sys.stdout.write(fh.read())
    return 0


def _norm(s):
    return re.sub(r"\s+", " ", s).strip().lower()


def _section_body(text, key):
    """Return the text under the first heading whose normalized title contains `key`,
    up to the next heading. Lets a check inspect ONE section, not the whole document."""
    body, capturing = [], False
    for ln in text.splitlines():
        m = re.match(r"^#{1,6}\s+(.*)$", ln)
        if m:
            capturing = key in _norm(m.group(1))
            continue
        if capturing:
            body.append(ln)
    return "\n".join(body).strip()


def cmd_check(args):
    """Validate a finished handoff against the template's structure."""
    if args.path == "-":
        text = sys.stdin.read()
        label = "<stdin>"
    else:
        if not os.path.exists(args.path):
            sys.exit("error: no such file: %s" % args.path)
        with open(args.path, encoding="utf-8") as fh:
            text = fh.read()
        label = args.path

    required = read_template_sections()
    present_headings = re.findall(r"^##\s+(.*\S)\s*$", text, flags=re.MULTILINE)
    present_norm = [_norm(h) for h in present_headings]

    errors = []
    warnings = []

    # 1. Every required section present. Matched on the core word(s) with any leading
    #    marker/emoji stripped, so "## Goal" and "## ⭐️ Goal" both satisfy "⭐️ Goal".
    strip_lead = lambda s: re.sub(r"^[^a-z0-9]+", "", s)
    present_keys = [strip_lead(p) for p in present_norm]
    for sec in required:
        key = strip_lead(_norm(sec).split(" / ")[0].split("(")[0]).strip()
        if not any(key and key in p for p in present_keys):
            errors.append("missing section: '## %s'" % sec)

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

    # 3. The Re-derive section must carry actual re-derivation CONTENT, not just the word.
    #    (A bare "re-derive" anywhere used to pass — too weak.) Scope to the section and look
    #    for substance + an action/reference cue. Still a WARN: concreteness is a judgement
    #    call the human owns; this only catches the obviously-empty case.
    rd = _section_body(text, "re-derive")
    rd_words = len(re.findall(r"\w+", rd))
    rd_cue = re.search(
        r"(?i)\b(re-?run|re-?read|re-?check|re-?confirm|re-?verify|verify|confirm|compare|"
        r"reconcile|against|re-?check|git|test|build|diff|spec|issue|\bpr\b|file|doc)", rd)
    if rd_words < 4 or not rd_cue:
        warnings.append("'Re-derive on pickup' section is thin — name WHAT to reconcile against "
                        "and HOW (e.g. 're-run the tests', 're-read the spec', 're-confirm the "
                        "figures), not just the word 're-derive'")

    # 4. Secret sweep (WARN backstop — see SECRET_PATTERNS; the prompt owns real redaction).
    for pat, why in SECRET_PATTERNS:
        if re.search(pat, text):
            warnings.append("possible leaked secret (%s) — redact before sharing" % why)
    for m in INLINE_CRED.finditer(text):
        val = m.group(2)
        if len(val) >= 6 and not SAFE_VALUE.search(val):
            warnings.append("possible inline credential (%s=…) — redact, or use an env lookup / "
                            "placeholder" % m.group(1))
            break

    # Report
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
    print("%s: OK — all sections present, one goal anchor, re-derive note present." % label)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Scaffold or validate a handoff document (optional helper).")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_new = sub.add_parser("new", help="print a blank handoff scaffold to stdout")
    p_new.set_defaults(func=cmd_new)

    p_check = sub.add_parser("check", help="validate a finished handoff")
    p_check.add_argument("path", help="path to the handoff .md, or - for stdin")
    p_check.set_defaults(func=cmd_check)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
