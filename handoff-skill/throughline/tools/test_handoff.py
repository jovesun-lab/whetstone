#!/usr/bin/env python3
"""
test_handoff.py — tests for handoff.py, written FIRST for Throughline 0.3 (step S1).

Every fixture is synthetic: no real handoff is copied in (this repository is public).
Standard library only, like handoff.py.

Run:  python3 tools/test_handoff.py

The 0.3 handoff these tests describe — nine sections, in order:
  Machine fields · ⭐️ Goal · Where this session stopped · Done · Next actions ·
  Waiting on others · Project state · Rulings not yet home · Re-derive on pickup
Six of them are the blocks every handoff must carry (Machine fields, Where this session
stopped, Next actions, Waiting on others, Project state, Rulings not yet home).

In Done, each MAIN of the session sits under its frozen title with its verdict and its
🔸 subtasks (no ⭐️ there: the one live ⭐️ is the Goal):
  ### MAIN: <frozen title> — LANDED | PARTIAL | NOT-LANDED
  (an optional id may follow MAIN — `### MAIN S12-1: <title> — …` — and then the same id in Machine fields)
  - 🔸 <subtask> · done
  - 🔸 <subtask> · carried → <row ID or file path>
  - 🔸 <subtask> · dropped · human: "<their words>"
A session with no MAIN says so in Done, in the human's words:
  zero-MAIN · human: "<their words>"
Every item in Next actions and in Rulings not yet home points at its row (a row ID or a
file path); "none" is allowed. The Goal is the first Next action.

Cases (a)–(n) follow the plan; (o) keeps the template and the rule file on the same
sections; (p) checks the rule file itself; (q) that each rule's
anchor phrase is written in its file; (r) that every shipped example passes. Before the rule file and the new check exist, every case except (o) is red;
(o) holds today and must keep holding.
"""

import os
import re
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(HERE, "handoff.py")
TEMPLATE = os.path.normpath(os.path.join(HERE, "..", "templates", "handoff.template.md"))
RULES = os.path.normpath(os.path.join(HERE, "..", "rules", "task-rules.json"))

DONE_BODY = "\n".join([
    "### MAIN: Build the widget parser — LANDED",
    "Evidence: `python3 -m unittest tests/test_parser.py`, 12 passed.",
    "- 🔸 tokenizer · done",
    "- 🔸 grammar rules · done",
    "",
    "### MAIN: Draft the README — NOT-LANDED",
    "- 🔸 outline · done",
    "- 🔸 examples · carried → T-260105-1200-02",
])

VERDICT_LINES = ("- verdict: Build the widget parser — LANDED\n"
                 "- verdict: Draft the README — NOT-LANDED\n")

SIX_BLOCKS = ["Machine fields", "Where this session stopped", "Next actions",
              "Waiting on others", "Project state", "Rulings not yet home"]


def valid_parts():
    """The sections of a handoff that passes every check, as (heading, body) pairs."""
    return [
        ("# Handoff — Build the widget parser", ""),
        ("## Machine fields", (
            "- session: 0000-test · S12 · agent: Ada · model: test-model · host: test-host\n"
            "- started 2026-01-05T10:00Z · ended 2026-01-05T12:00Z\n"
            + VERDICT_LINES +
            "\n| file | md5 |\n|---|---|\n| `src/parser.py` | 0123456789ab |")),
        ("## ⭐️ Goal", "Write the widget parser's error messages"),
        ("## Where this session stopped", "The parser landed; the README draft is half done."),
        ("## Done", DONE_BODY),
        ("## Next actions", (
            "1. Write the widget parser's error messages · T-260105-1200-01\n"
            "2. Finish the README examples · T-260105-1200-02")),
        ("## Waiting on others", "none"),
        ("## Project state", "none"),
        ("## Rulings not yet home", "- Error messages are plain English, no codes · `plans/parser.md`"),
        ("## Re-derive on pickup", (
            "Re-run `python3 -m unittest tests/test_parser.py`, expect 12 passed; compare the md5 "
            "of `src/parser.py` against the table in Machine fields.")),
    ]


def render(parts):
    return "\n\n".join(h + ("\n\n" + b if b else "") for h, b in parts) + "\n"


def doc(swap=None, drop=()):
    """The valid handoff, with text swapped ({old: new}, each old must occur) and sections dropped."""
    text = render([(h, b) for h, b in valid_parts() if h not in drop])
    for old, new in (swap or {}).items():
        assert old in text, "fixture text not found: %r" % old
        text = text.replace(old, new)
    return text


def run(args, text=None, name="handoff.md"):
    """Run handoff.py; '{file}' in args becomes a temp file holding `text`."""
    with tempfile.TemporaryDirectory() as d:
        argv = list(args)
        if text is not None:
            path = os.path.join(d, name)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
            argv = [path if a == "{file}" else a for a in argv]
        return subprocess.run([sys.executable, TOOL] + argv, capture_output=True,
                              text=True, encoding="utf-8")


def check(text, *extra):
    return run(["check", "{file}"] + list(extra), text)


def lines(r, prefix):
    return [ln for ln in r.stdout.splitlines() if ln.startswith(prefix)]


def shown(r):
    return "exit %s\n--- stdout\n%s--- stderr\n%s" % (r.returncode, r.stdout, r.stderr)


class HandoffCheck(unittest.TestCase):

    def assertClean(self, r):
        self.assertEqual(r.returncode, 0, shown(r))
        self.assertEqual(lines(r, "FAIL"), [], shown(r))

    def assertFails(self, r, pattern):
        """Exit 1 and a FAIL line matching `pattern` (a regex, case-insensitive)."""
        self.assertEqual(r.returncode, 1, shown(r))
        self.assertTrue(any(re.search(pattern, ln, re.I) for ln in lines(r, "FAIL")),
                        "no FAIL line matches %r\n%s" % (pattern, shown(r)))

    def test_valid_handoff_passes(self):
        self.assertClean(check(doc()))

    def test_valid_handoff_with_optional_main_ids_passes(self):
        self.assertClean(check(doc(swap={
            "### MAIN: Build the widget parser — LANDED": "### MAIN S12-1: Build the widget parser — LANDED",
            "- verdict: Build the widget parser — LANDED": "- verdict S12-1: Build the widget parser — LANDED"})))

    def test_a_section_matched_by_name_not_by_a_word_inside_another_heading(self):
        # 0.2.1 matched "done" inside "Undone work" (a substring test) and passed by coincidence.
        self.assertFails(check(doc(swap={"## Done": "## Undone work"})), r"missing section.*\bDone\b")

    def test_b_alias_at_the_end_of_a_project_heading_counts_as_that_section(self):
        self.assertClean(check(doc(swap={"## Project state": "## Engine notes · Throughline: Project state"})))

    def test_c_a_main_needs_subtasks_and_a_verdict(self):
        with self.subTest("no 🔸 subtask"):
            r = check(doc(swap={"- 🔸 tokenizer · done\n- 🔸 grammar rules · done\n": ""}))
            self.assertFails(r, r"subtask")
        with self.subTest("no verdict"):
            r = check(doc(swap={"### MAIN: Build the widget parser — LANDED": "### MAIN: Build the widget parser"}))
            self.assertFails(r, r"verdict")

    def test_d_landed_needs_every_subtask_done(self):
        with self.subTest("a carried subtask under LANDED"):
            r = check(doc(swap={"- 🔸 grammar rules · done": "- 🔸 grammar rules · carried → T-260105-1200-03"}))
            self.assertFails(r, r"grammar rules")
        with self.subTest("a subtask with no status"):
            r = check(doc(swap={"- 🔸 grammar rules · done": "- 🔸 grammar rules"}))
            self.assertFails(r, r"grammar rules")

    def test_e_dropped_needs_the_humans_words(self):
        examples = "- 🔸 examples · carried → T-260105-1200-02"
        with self.subTest("without words"):
            self.assertFails(check(doc(swap={examples: "- 🔸 examples · dropped"})), r"examples")
        with self.subTest("with words"):
            self.assertClean(check(doc(swap={examples: '- 🔸 examples · dropped · human: "skip the examples for now"'})))

    def test_f_carried_needs_a_destination(self):
        examples = "- 🔸 examples · carried → T-260105-1200-02"
        for bad in ("- 🔸 examples · carried", "- 🔸 examples · carried → later"):
            with self.subTest(bad):
                self.assertFails(check(doc(swap={examples: bad})), r"examples")
        with self.subTest("a file path is a destination too"):
            self.assertClean(check(doc(swap={examples: "- 🔸 examples · carried → `plans/readme.md`"})))

    def test_g_zero_main_needs_the_humans_words(self):
        with self.subTest("with words"):
            r = check(doc(swap={VERDICT_LINES: "", DONE_BODY: 'zero-MAIN · human: "only answering questions today"'}))
            self.assertClean(r)
        with self.subTest("without words"):
            self.assertFails(check(doc(swap={VERDICT_LINES: "", DONE_BODY: "zero-MAIN"})), r"zero-MAIN")

    def test_h_done_listing_work_without_a_main_fails(self):
        r = check(doc(swap={VERDICT_LINES: "", DONE_BODY: "- fixed the tokenizer\n- wrote the parser tests"}))
        self.assertFails(r, r"MAIN")

    def test_i_a_missing_rule_file_is_a_clear_error(self):
        missing = os.path.join(tempfile.mkdtemp(), "no-such-folder", "task-rules.json")
        r = check(doc(), "--rules", missing)
        self.assertNotEqual(r.returncode, 0, shown(r))
        self.assertIn("rule file", r.stderr.lower(), shown(r))
        self.assertIn(missing, r.stderr, shown(r))

    def test_j_each_of_the_six_blocks_is_required(self):
        for block in SIX_BLOCKS:
            with self.subTest(block):
                self.assertFails(check(doc(drop=("## " + block,))), r"missing section.*" + re.escape(block))

    def test_k_next_actions_and_rulings_point_at_a_row(self):
        with self.subTest("a next action with no row"):
            r = check(doc(swap={"1. Write the widget parser's error messages · T-260105-1200-01":
                                "1. Write the widget parser's error messages"}))
            self.assertFails(r, r"row")
        with self.subTest("a ruling with no row"):
            r = check(doc(swap={"- Error messages are plain English, no codes · `plans/parser.md`":
                                "- Error messages are plain English, no codes"}))
            self.assertFails(r, r"row")
        with self.subTest("none is allowed"):
            self.assertClean(check(doc(swap={"- Error messages are plain English, no codes · `plans/parser.md`": "none"})))

    def test_m_the_goal_is_the_first_next_action(self):
        r = check(doc(swap={"## ⭐️ Goal\n\nWrite the widget parser's error messages":
                            "## ⭐️ Goal\n\nShip the parser to production"}))
        self.assertFails(r, r"goal")

    def test_n_machine_fields_verdicts_agree_with_done(self):
        r = check(doc(swap={"- verdict: Build the widget parser — LANDED": "- verdict: Build the widget parser — PARTIAL"}))
        self.assertFails(r, r"verdict")

    def test_r_every_shipped_example_passes(self):
        examples = os.path.normpath(os.path.join(HERE, "..", "examples"))
        for name in sorted(os.listdir(examples)):
            if name.endswith(".md"):
                with self.subTest(name):
                    self.assertClean(run(["check", os.path.join(examples, name)]))

    def test_o_the_template_holds_exactly_the_required_sections(self):
        # Expected green before and after: guards the template against the rule file (S2 vs S4).
        r = run(["check", TEMPLATE])
        self.assertEqual([ln for ln in lines(r, "FAIL") if "missing section" in ln], [], shown(r))


class RuleFile(unittest.TestCase):

    def test_p_the_rule_file_loads_and_every_rule_says_why(self):
        import json
        self.assertTrue(os.path.exists(RULES), "no rule file at %s" % RULES)
        with open(RULES, encoding="utf-8") as fh:
            data = json.load(fh)
        fields = ("id", "text", "trigger", "kind", "enforced_by", "pass_condition", "why", "owner", "status",
                  "written_in", "related")
        ids = [r.get("id") for r in data["rules"]]
        self.assertEqual(len(ids), len(set(ids)), "duplicate rule ids")
        for rule in data["rules"]:
            with self.subTest(rule.get("id")):
                self.assertEqual(sorted(rule), sorted(fields))
                self.assertTrue(all(rule["why"].get(k) for k in ("ruling", "incident", "source")), rule["why"])


    def test_q_every_written_anchor_is_in_its_file(self):
        import json
        with open(RULES, encoding="utf-8") as fh:
            data = json.load(fh)
        root = os.path.dirname(os.path.dirname(RULES))
        for rule in data["rules"]:
            for w in rule["written_in"]:
                if not w["anchor"]:
                    continue
                with self.subTest(rule["id"]):
                    with open(os.path.join(root, w["file"]), encoding="utf-8") as fh:
                        text = re.sub(r"\s+", " ", fh.read()).lower()
                    self.assertIn(re.sub(r"\s+", " ", w["anchor"]).lower(), text, "%s: %r not in %s" % (rule["id"], w["anchor"], w["file"]))


class SessionStartBrief(unittest.TestCase):

    def test_l_an_id_that_carries_no_words_is_a_warning(self):
        bad = ("# Session start brief for the widget parser work\n\n"
               "Where we are: the parser landed.\n\n"
               "- D.5 two questions\n"
               "- next: M1 and C9\n")
        r = run(["brief", "{file}"], bad, name="brief.md")
        self.assertEqual(r.returncode, 0, shown(r))
        for token in ("D.5", "M1"):
            self.assertTrue(any(token in ln for ln in lines(r, "WARN")), "no WARN names %s\n%s" % (token, shown(r)))

    def test_l_ids_with_their_words_pass_quietly(self):
        good = ("# Session start brief for the widget parser work\n\n"
                "Where we are: the parser landed.\n\n"
                "- D.5, the two open questions on the brief format (spec section D.5)\n"
                "- next: release checklist item M1, signing the build\n")
        r = run(["brief", "{file}"], good, name="brief.md")
        self.assertEqual(r.returncode, 0, shown(r))
        self.assertEqual(lines(r, "WARN"), [], shown(r))



class FlowMatchesRules(unittest.TestCase):
    """assets/throughline-flow.html is generated from rules/task-rules.json; it carries the version and the first 16 hex of the
    rule file's sha256 in <meta name="throughline-rules">. A rule file changed after the flow was drawn turns this red: redraw."""

    def test_s_the_flow_is_drawn_from_the_current_rule_file(self):
        import hashlib, json
        flow = os.path.normpath(os.path.join(HERE, "..", "assets", "throughline-flow.html"))
        with open(flow, encoding="utf-8") as f:
            m = re.search(r'<meta name="throughline-rules" content="version=([^ "]+) sha256-16=([0-9a-f]{16})">', f.read())
        self.assertIsNotNone(m, "the flow carries no rule-file stamp - draw it from the rule file")
        with open(RULES, "rb") as f:
            raw = f.read()
        self.assertEqual(m.group(1), json.loads(raw.decode("utf-8"))["version"], "the flow was drawn from another version")
        self.assertEqual(m.group(2), hashlib.sha256(raw).hexdigest()[:16], "the rule file changed after the flow was drawn")


if __name__ == "__main__":
    unittest.main(verbosity=2)
