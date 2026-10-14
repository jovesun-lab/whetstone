# Throughline v0.3.0

*Keep the thread — within a session, and across them.*

## What's new in 0.3.0

The rules become data, and the handoff gets one shape every project can share.

- **One rule file, three readers.** `rules/task-rules.json` holds every rule as a record — its text, the moment it fires, why it
  exists, the condition it passes on, what checks it and where it is written. The handoff checker reads it, a project's own gates
  can read it, and the flow is drawn from it.
- **The handoff: nine sections, found by name.** Machine fields · ⭐️ Goal · Where this session stopped · Done · Next actions ·
  Waiting on others · Project state · Rulings not yet home · Re-derive on pickup. A section is found by its heading's name, not its
  position; the ⭐️ Goal is a proposal and must equal the first Next action; each MAIN's verdict has one home, Done.
- **The skeleton every project shares** (`references/handoff.md`): the wrap's seven steps in order, the start that copies the
  next actions verbatim and writes the session-start brief to disk, a project's own steps as modules, and rules that leave the
  handoff by kind.
- **Task-track rules sharpened:** a MAIN may carry an optional id (`### MAIN S12-1: …`); its title freezes when the human confirms
  it; LANDED needs every subtask done; a subtask leaves the list three ways only; 🌶️ says impact, not membership; the task list
  lives where the human sees it, and every next action or open ruling points at a row.
- **`tools/handoff.py`** — `new` (a blank scaffold), `check` (a finished handoff against the rule file) and `brief` (warns on IDs
  in a session-start brief that carry no words). 22 tests, `python3 tools/test_handoff.py`.
- **The interactive flow is now a rule map:** `assets/throughline-flow.html` draws every rule under the moment it first fires,
  generated from the rule file; a test goes red if the rule file changes and the map is not redrawn.
- **Breaking:** a 0.2.1 handoff fails the new check — the Done grammar changed too, so old headings are not kept as aliases. Start
  the next one from `python3 tools/handoff.py new`.

## What's new in 0.2.1

One rule, learned the hard way when a harness update silently changed which field a task
UI renders:

- **The marker must sit on the channel that actually renders.** Task UIs may expose more
  than one text field per task, and a newer field can supersede the title without warning
  — hiding a title-only ⭐️ exactly during the in-progress phase where drift happens. When
  a UI offers an extra display field, **omit it rather than mirror the marker into it**:
  an omitted field falls back to the title, which the rules already govern; a mirrored
  field is a second copy kept in sync by hand. (Known instance, 2026-09: the optional
  `activeForm` field in Claude-family task tools — leave it empty.)
- The old wording claiming the title is "always visible no matter how the list is
  rendered" was **falsified** by that instance and has been corrected in `SKILL.md` and
  `references/task-track.md`; the marker-robustness note now carries three rules
  (anchored · portable · channel).
- Also new: if your task list renders where you cannot read it back, treat a human saying
  "I can't see the star" as a report about the *channel*, not about your discipline.

---

# Throughline v0.2.0

## What's new in 0.2.0

Disciplines extracted from another year of daily multi-session use — each one closes a
failure that actually happened:

- **Frozen titles.** A goal's title freezes when it's confirmed and it closes under that
  same name — a MAIN renamed into whatever actually happened makes "done" unfalsifiable.
- **Verdicts, with evidence.** Every goal closes `LANDED` (evidence attached) / `PARTIAL` /
  `NOT-LANDED` (carried forward, visibly). Silence is not a verdict.
- **Redirects append.** A redirected goal takes an honest NOT-LANDED; the new direction is a
  new entry. The append trail is the proof that every shift was agreed, not drift.
- **One boot = one session.** However many wrap-ups happen inside a conversation; anything
  that counts sessions counts boots. Name the session early; the handoff header carries it.
- **Two-box checklists.** `built` and `verified` tick separately — `verified` only after the
  named check actually ran.
- **Decisions section.** Numbered, append-only — ends re-litigating and chat-log archaeology.
- **Atomic wraps.** Work landing after the handoff was written makes it stale; re-run the wrap.
- **Gaps are findings.** The resume side reports what the wrap side skipped, out loud.
- **Expected results in Re-derive.** "Run X, expect Y" — a named check with no expected value
  can't tell the next agent whether the world moved.
- **Multi-agent rules.** One writer per shared artifact; workstream owners write their own
  work-package docs; the docs — not chat history — are the coordination channel.
- **Companion: [strain](../../strain).** Strain says *when* to wrap; Throughline is *how*.
- **New working-principle diagram** — drawn with [Arcgram](https://arcgram.io) as an
  interactive flow (`assets/throughline-flow.html`), exported to `assets/logic-flow.svg`
  with the engine's own SVG export.

Template change note: handoffs now have a **Decisions** section and a session-name header;
`handoff.py check` reads sections from the template, so it enforces the new shape
automatically — older handoffs will need the new section to pass.

---

# Throughline v0.1.0 (original release)

**A tiny, agent-agnostic skill that keeps work on-thread — within a session, and across the seam between sessions or agents. (Task Track + Handoff.)**

Long or multi-agent work fails two predictable ways. This release packages two linked habits, one for each.

## The problem

- **Within a session, reasoning drifts off the goal.** You solve a small problem, which surfaces another, which pulls you somewhere adjacent to where you started. Every step is locally reasonable; together they bend the trajectory, and no alarm ever fires.
- **Across sessions, the thread gets dropped.** A fresh run — or a different agent — starts cold, re-derives what was already known, or trusts a summary that has since gone stale.

## What it is

Two habits that share one anchor:

- **Task Track** — an emoji-tagged task list with exactly one **⭐️ MAIN** goal anchor, so you can see at a glance whether you're still on the main thing or chasing a transient (🌶️ critical · 🍏 temp · 🍋 logged/recurred).
- **Handoff** — compact a session into a plain-markdown document the next agent can pick up cleanly, then **re-derive against ground truth before trusting it** (the read side most handoff tools skip).

The load-bearing idea: **the ⭐️ MAIN tag is the shared goal anchor.** Task Track holds it *within* a run; the handoff's ⭐️ Goal carries it *across* runs. One sentence — **don't lose the thread, within a session or between them.**

## Why it's built this way

- **Capability-agnostic.** Works as a prompt in any agent — Claude, OpenAI, Gemini, Cursor, Cline, a local model — or as a skill / slash command where those exist. Every capability degrades gracefully: no file write → emit the handoff inline; no live access → re-derive from the artifacts you have; no code execution → skip the helper. The two disciplines (the goal anchor, and re-derive-don't-trust) have zero capability dependency, so they hold at the lowest common denominator.
- **Pure-prompt core, optional helper.** A single zero-dependency Python helper (stdlib only) does only the *mechanizable* half — scaffold a handoff, and validate one. It never summarizes; that stays the model's job.
- **It dogfoods its own rules.** The validator reads its required sections **from the shared template at runtime**, so the prompt and the checker can't drift apart — the skill's own single-source-of-truth rule, applied to itself.
- **Markers are anchored, not fragile.** The ⭐️ MAIN is matched at the *start of a line*, with `[MAIN]` and `main_goal: true` as plain-text equivalents — so a star buried in prose never miscounts, and the discipline never depends on an emoji rendering. The re-derive check looks for *actual* reconciliation steps, not just the word.

## What's in the box

`SKILL.md` · `commands/handoff.md` + `commands/resume.md` · `references/` (the two halves explained in depth, with the five anti-drift mechanisms) · `templates/handoff.template.md` · `examples/example-handoff.md` · `tools/handoff.py` (optional) · `assets/logic-flow.svg`.

## Use it

- **Any agent:** paste the relevant file in as a prompt.
- **Claude Code / Cursor:** drop the folder in — then `handoff` to wrap up, `resume` to pick up.
- **Optional, where you can run code:**
  ```bash
  python3 tools/handoff.py new                 # scaffold a blank handoff
  python3 tools/handoff.py check HANDOFF.md    # sections · one ⭐️ MAIN · re-derive content · secret sweep
  ```

## Designed in the open

This started as a discipline lived daily in a real multi-session project, then was generalized so any agent or team could use it. Several of the sharpest improvements in this release — hardening the goal-anchor check, scoping the re-derive check to real content, killing a secret-scan false positive — came from **cross-agent review**: one model proposing, another stress-testing. Fitting, for a skill about not losing the thread between agents.

Feedback, issues, and PRs welcome.

**License:** MIT.
