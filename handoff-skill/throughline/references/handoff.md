# Handoff — the across-session half

> The companion to [`task-track.md`](task-track.md). Task Track keeps a single run on its goal;
> Handoff carries that goal — and the state around it — across runs and across agents.

## The problem it solves: the dropped thread

When work spans more than one session, or more than one agent, the thread gets dropped at the
seam. A fresh run starts cold. It re-derives what was already figured out, or — worse — it trusts
a tidy summary that has since gone stale and builds on top of a fact that is no longer true.

A handoff fixes the seam by carrying the thread forward as a **plain-text artifact**. Plain text
is the universal interface: any agent on any platform can read it, and so can a human. It assumes
nothing about tools, memory systems, or who picks it up next.

## The artifact

A handoff is a short markdown document — *latest state plus pointers*, never a copy of the work.
Its structure is fixed by the shared template, [`../templates/handoff.template.md`](../templates/handoff.template.md),
which is the single source of truth for what sections a handoff has. The sections:

- **⭐️ Goal** — the one thing the next session is for (the carried-forward MAIN).
- **State** — where things stand now; unverified items marked as such.
- **Done** — what was completed, briefly.
- **Open / Next** — open threads and the recommended next move, prioritized.
- **Re-derive on pickup** — what to reconcile against ground truth before trusting the doc.
- **Suggested next steps / tools / skills** — concrete next actions and capabilities to reach for.
- **References** — pointers to plans, specs, issues, commits, diffs, docs, by path or URL.

## The five anti-drift mechanisms

These are *why* the handoff is shaped the way it is. Each one closes a specific failure mode.

- **Single source of truth.** Each fact lives in exactly one place; everything else *links* to it
  instead of restating it. This is why the handoff says "reference, don't duplicate," and why the
  validator reads its section list *from the template* rather than hardcoding it. Copies drift;
  references can't. The classic failure it prevents is a number hardcoded in two places that
  silently disagree.

- **Orient before executing** *(for ongoing human↔agent collaborations).* When a session opens,
  orient the human first — restate where things stand — before diving into the work. The
  reciprocal "here's where we are" is part of the job, not a step to skip on the way to the task.
  (For a one-shot, single-use handoff this matters less; for a continuing relationship it's what
  keeps the human in the loop.)

- **A checkable pickup.** Resuming is verifiable, not vibes: the first thing a resuming agent
  produces should show it both *oriented* (restated the ⭐️ Goal) and *reconciled* (re-derived
  state against ground truth). If either is missing, the pickup drifted — and you can tell
  immediately. The optional `tools/handoff.py check` makes the write-side equivalent countable too
  (sections present, one ⭐️ MAIN, re-derive content present).

- **Newest-only, bounded.** The handoff holds only the *latest* state plus a pointer to any longer
  history. It must not grow into a second running log — a bloated handoff is one nobody reads,
  which drops the thread just as surely as having none.

- **Write it in one step.** When you wrap up, write the whole handoff — including the verification
  baseline ("re-derive against *this* check, expecting *these* numbers") — in one pass. If the
  state and its baseline are written separately, they drift apart, and the next session re-derives
  against a stale target.

## Writing a handoff

See [`../commands/handoff.md`](../commands/handoff.md) for the operation. In short: fill the
template, reference don't duplicate, redact secrets, keep it bounded, and save it where the next
agent will look (or emit it inline if you can't write files).

## Resuming from a handoff

See [`../commands/resume.md`](../commands/resume.md). In short: **re-derive before you trust.** A
handoff is a snapshot from before the world moved. Re-read the named artifacts, re-run the named
checks, re-confirm cited facts. Where the snapshot and ground truth disagree, ground truth wins —
and say so. This read-side discipline is the half a write-only handoff tool leaves out, and it's
where most "the next session built on a stale fact" failures actually happen.

## Why both halves, together

Task Track and Handoff are the same discipline at two timescales. The **⭐️ MAIN goal anchor** is
the shared object: Task Track keeps it in view *within* a run; the handoff's **⭐️ Goal** carries
it *across* runs. Lose it in either place and the work drifts — sideways within a session, or into
a stale restart between them. One sentence holds both: **don't lose the thread.**

## One reference implementation

This skill was extracted from a long-running, multi-session collaboration on an interactive-diagram
engine, where the two habits were lived daily by an agent and its human collaborator. That origin is
just *an* example — the mechanism is general. Nothing here assumes a particular project, engine,
agent, or memory system; strip the example and the discipline stands on its own.
