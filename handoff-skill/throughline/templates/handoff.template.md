<!--
  HANDOFF TEMPLATE (Throughline 0.3) — the structure every handoff shares.
  The sections a handoff must have are listed in rules/task-rules.json (handoff.sections). This
  template holds exactly those headings, and a test keeps the two equal; tools/handoff.py checks a
  finished handoff against the rule file.

  Fill every "## " section; "none" is a valid answer where a block is empty. Delete these comments.
  A handoff is a pointer-map, not a copy of the work: each item points at its row or file.
  A project whose tools read its own heading names keeps them and adds the alias at the END:
  "## Our next steps · Throughline: Next actions".
-->

# Handoff — <one-line title of the work>

## Machine fields

- session: <host session id> · <session number> · agent: <name> · model: <model> · host: <product>
- started <UTC time> · ended <UTC time>
- verdict: <frozen title> — <LANDED | PARTIAL | NOT-LANDED>

| file | md5 |
|---|---|
| `<path>` | <first 12 characters> |

<!-- A script reads this block. One "verdict:" line per MAIN, a generated copy of Done (Done is the
     home; the two must agree). With a MAIN id: "- verdict S12-1: <frozen title> — <verdict>". -->

## ⭐️ Goal

<the next session's MAIN, proposed — the human confirms it at the next start>

<!-- Exactly one anchored marker in the whole doc: this heading's ⭐️ (or a [MAIN] line, or a
     main_goal: true frontmatter line). The text must equal the first item of Next actions, without
     its row reference. -->

## Where this session stopped

<two or three sentences: where things stand, what is in flight, what is not verified yet>

## Done

### MAIN: <frozen title> — <LANDED | PARTIAL | NOT-LANDED>
Evidence: <the check that proves the verdict, and what it printed>
- 🔸 <subtask> · done
- 🔸 <subtask> · carried → <row ID or file path>
- 🔸 <subtask> · dropped · human: "<their words>"

<!-- One "### MAIN:" entry per MAIN of this session, under the title it was confirmed with; an
     optional id may follow the word MAIN ("### MAIN S12-1: …"). LANDED needs every subtask done.
     A subtask leaves the list three ways only: done (its test passed), carried to a named row or
     file, or dropped on the human's own words.
     A session with no MAIN (questions only, no file changed) writes instead, on the human's words:
     zero-MAIN · human: "<their words>" -->

## Next actions

1. <the next session's MAIN — the same text as the Goal> · <row ID or file path>
2. <the next one> · <row ID or file path>

<!-- Ranked, one line each, each ending with its durable row (a board row ID or a plan file). An
     optional "not before <time>" goes before the row. -->

## Waiting on others

<who — the human or another agent — owes what, with its row; or "none">

## Project state

<filled by the project's own module: versions, hashes, the last check result; or "none">

## Rulings not yet home

- <a decision made this session, in full> · <the row or file it must reach>

<!-- Each stays here, in full, until it is written into its home file; earlier ones by pointer only.
     "none" if there are none. -->

## Re-derive on pickup

<what to re-check before trusting any of this, with the expected result next to it: "run X, expect Y".
The file table in Machine fields is the first input.>

<!-- Secrets check: no API keys, tokens, passwords, or personal data anywhere above. -->
