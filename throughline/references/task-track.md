# Task Track — the within-session half

> The companion to [`handoff.md`](handoff.md). Task Track keeps a single run on its goal;
> Handoff carries that goal across runs. They share one anchor — the **⭐️ MAIN** — which is why
> they ship as one skill.

## The problem it solves: reasoning drift

Long tasks rarely fail in one big wrong turn. They fail by a thousand small reasonable ones.

You set out to do X. Doing X surfaces a smaller problem, so you fix it. That fix reveals an
inconsistency, so you handle that too. Each step is locally rational — and none of them is X
anymore. By the end you've built something *adjacent* to what you were asked for, and no alarm
ever went off, because every individual step was fine.

This is **reasoning drift**: the work wanders off the goal as small unfixed or half-fixed problems
accumulate and quietly bend the trajectory. There's no external truth to check against
mid-flight — only the goal you started with. So the goal has to be *written down and kept in
view*, because the goal in your head drifts silently while the goal on the page does not.

## The mechanism: one anchor, tagged origins

Keep a task list with exactly **one ⭐️ MAIN** task — the goal anchor — and tag every other task
with a leading emoji that records *where it came from*:

| Tag | Meaning | Why it's tagged this way |
|---|---|---|
| **⭐️ MAIN** | The session's primary task / goal anchor. **Exactly one.** | This is the thing every other task is supposed to serve. Re-read it before load-bearing steps. |
| **🌶️ Critical** | A critical / high-impact task in service of the MAIN. | Distinguishes "must do, big blast radius" from ordinary subtasks. |
| **🍏 Temp this session** | Surfaced mid-session; not in any plan or log. A transient. | These are the drift carriers. Tagging them makes the transients countable at a glance. |
| **🍋 Logged + recurred / pulled-in** | A logged task that came back, OR a logged-but-unplanned task worth doing now. | Separates "we knew about this" from "this is brand new," so recurring problems are visible. |

Put the emoji **in the task title**, not only in a hidden field — the title is the channel that's
always visible no matter how the list is rendered. If your task UI also shows badges, use them
too, but never *only* the badge.

**A note on the marker (so it stays robust, not fragile).** Two rules keep the ⭐️ MAIN trustworthy
when something *parses* the list rather than just reads it:

- **The marker is anchored — it lives at the START of the task line/heading.** A ⭐ that happens to
  appear mid-sentence ("this is worth 5⭐") is decoration, not an anchor, and must not be counted as
  one. Match the position, don't count the glyph anywhere.
- **A plain-text form exists for portability.** Not every agent, terminal, or font renders emoji
  (we hit exactly this rendering the diagram for this skill). So `[MAIN]` at line-start is an
  accepted equivalent of ⭐️, and `main_goal: true` in frontmatter is the explicit machine form.
  Pick whichever survives your tools — the rule is unchanged: **exactly one anchored marker.** This
  mirrors the skill's capability-agnostic stance; the discipline shouldn't hinge on a glyph
  rendering.

## How to run it

- **At session start, once the goal is clear, write the ⭐️ MAIN.** This is the anchor. Phrase it
  so you can literally re-read it and self-check: *"Am I still solving this, or something it slid
  into?"*
- **One ⭐️ MAIN at a time.** If a second candidate for MAIN appears, that's a decision, not a
  default — surface it to the human rather than quietly running two main lines.
- **Tag new tasks as they appear.** A new problem mid-session is almost always 🍏 (transient) or
  🍋 (recurred/pulled-in). The act of tagging is the moment you notice you're adding scope.
- **Watch the 🍏 pile.** A transient that keeps growing — spawning sub-tasks, eating time — is the
  drift signal. When a 🍏 balloons past the MAIN's scope, **stop and re-confirm with the human**.
  Don't let a side-find silently become the main line.
- **Re-read the ⭐️ MAIN before any load-bearing step.** Not every step — that's paralysis. Just
  the ones the rest of the work will compound on.

## What "good" looks like

The list itself should read like a story of the session: one star at the top, a few critical
items under it, and a visible trail of transients. If you scan it and can't tell what the main
line is, or there are five transients and the star is buried, the list is telling you the work
has drifted — which is the whole point. The tags don't prevent drift; they make it *legible* early
enough to correct.

## Where it connects to Handoff

The ⭐️ MAIN is not just a within-session device. When you wrap up, it becomes the **⭐️ Goal** of
the handoff — the single thread the next session inherits. So the same anchor that kept *this*
run honest is what keeps the *next* run from starting unmoored. That hand-off of the anchor is the
correlation between the two halves; see [`handoff.md`](handoff.md).
