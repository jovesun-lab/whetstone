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

- **Header** — names the session that wrote this (session name + id, if the host exposes one),
  so every claim in the doc traces back to the session that made it.
- **⭐️ Goal** — the one thing the next session is for (the carried-forward MAIN), under its
  frozen title.
- **State** — where things stand now; unverified items marked as such.
- **Done** — what was completed, briefly — **each goal closed with an explicit verdict**
  (`LANDED` with evidence / `PARTIAL` / `NOT-LANDED` with where it's carried), under the title
  it was confirmed with. Silence is not a verdict.
- **Decisions** — what the human confirmed this session, numbered, append-only. Kills
  re-litigating and chat-log archaeology.
- **Open / Next** — open threads and the recommended next move, prioritized.
- **Re-derive on pickup** — what to reconcile against ground truth before trusting the doc,
  each check named **with its expected result**.
- **Suggested next steps / tools / skills** — concrete next actions and capabilities to reach for.
- **References** — pointers to plans, specs, issues, commits, diffs, docs, by path or URL.

## The seven anti-drift mechanisms

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

- **Write it in one step — and re-write it if work resumes.** When you wrap up, write the whole
  handoff — including the verification baseline ("re-derive against *this* check, expecting
  *these* numbers") — in one pass. If the state and its baseline are written separately, they
  drift apart, and the next session re-derives against a stale target. And the wrap is **atomic
  with the end of the work**: if a "wait, one more thing" lands *after* the handoff was written,
  the snapshot is stale — re-run the wrap and capture the new state. A stale handoff is worse
  than none: none makes the next session derive from scratch; stale makes it derive from a lie.

- **Close with a verdict, under the frozen name.** Every goal the session carried gets an
  explicit `LANDED` / `PARTIAL` / `NOT-LANDED` in Done — landed with the evidence, not-landed
  with where it's carried (it must reappear in Open / Next). The verdict is given to the goal's
  *frozen title*, never to a renamed version of it. This closes the quietest failure mode of
  all: the session that ends with everything vaguely "done" and nothing actually landed.

- **A skipped step is caught at the next pickup.** The protocol is self-healing *if* the resume
  side treats gaps as findings: a missing handoff, a stale date, an absent verdict, a thin
  re-derive section — each is evidence about how the last session ended, and it should be said
  out loud, not silently papered over. Every skip at wrap is caught by the next session's
  pickup — but only when the pickup actually looks.

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

## When more than one agent works the project

Throughline's single-file handoff covers the relay case: one session ends, the next picks up.
When **several agents (or several substrates of the same agent) work one project in parallel**,
three more rules keep the thread from forking:

- **Every shared artifact has exactly one writer.** The project's central record (the handoff,
  the log) is owned by one agent; the others never write it. Each non-owner keeps its **own
  progress note** — one line per work stint, newest first: date, who, what moved, what's next —
  and the owner folds those in at its wrap. Two writers on one record is how the same fact ends
  up with two values.
- **The workstream's owner writes its briefs.** Split parallel work into work packages, each
  owned by the agent doing it; the owner writes the package's doc (its decisions, its checklist
  rows with `built / verified` boxes, its progress log). Ownership of the work and authorship of
  its record travel together.
- **The doc is the coordination channel.** No agent should need another agent's chat history —
  everything that crosses the seam crosses in the artifact. If two agents can't coordinate
  through the files alone, the files are missing something; fix the files.

This is the same discipline as the rest of the skill at one more scale: single source of truth,
per artifact, with named ownership.

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
