# Throughline v0.1.0

*Keep the thread — within a session, and across them.*

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
