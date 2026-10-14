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
Its sections are listed in [`../rules/task-rules.json`](../rules/task-rules.json) (`handoff.sections`); the
shared template, [`../templates/handoff.template.md`](../templates/handoff.template.md) (at the plugin root),
holds exactly those headings. Six of them are **blocks** every handoff carries:

1. **Machine fields** — session id, session number, agent, model, host, times in UTC, one verdict line per
   MAIN (a generated copy of Done), a file-hash table. A script reads it.
2. **Where this session stopped** — a short human summary; anything unverified marked as such.
3. **Next actions** — ranked, one line each, with an optional "not before" time.
4. **Waiting on others** — what the human and other agents owe.
5. **Project state** — filled by the project's own module (versions, hashes, the last check); "none" allowed.
6. **Rulings not yet home** — decisions made this session, in full, until each is written into its home
   file; earlier ones by pointer only.

Around them: **⭐️ Goal** — the next session's MAIN, a *proposal* the human confirms at the next start, and
the same text as Next actions #1 · **Done** — each MAIN of this session under its frozen title, with its
verdict (`LANDED` / `PARTIAL` / `NOT-LANDED`) and its 🔸 subtasks, each done, carried → a row, or dropped on
the human's words; a session with no MAIN says so on the human's words (`zero-MAIN`) · **Re-derive on
pickup** — what to re-check before trusting the doc, each check with its expected result.

**The one rule:** every item in Next actions and in Rulings not yet home has its own durable row — a board
row or a plan file — and the handoff only points at it. A "next" list that lives only in the newest handoff
is overwritten by the first session that pivots.

**A project keeps its own headings.** When a project's tools read its handoff by heading name, it does not
rename them: it adds `· Throughline: <name>` at the end of the heading, and that heading counts as the
section. Otherwise a section is found by its name — the heading text after any marker starts with it —
never by a word inside another heading.

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
  with where it's carried (each open 🔸 carried → a row that Next actions points at). The verdict is given to the goal's
  *frozen title*, never to a renamed version of it. This closes the quietest failure mode of
  all: the session that ends with everything vaguely "done" and nothing actually landed.

- **A skipped step is caught at the next pickup.** The protocol is self-healing *if* the resume
  side treats gaps as findings: a missing handoff, a stale date, an absent verdict, a thin
  re-derive section — each is evidence about how the last session ended, and it should be said
  out loud, not silently papered over. Every skip at wrap is caught by the next session's
  pickup — but only when the pickup actually looks.

## The skeleton every project shares

**The wrap runs seven steps, in order:** (1) ask before wrapping · (2) a verdict per MAIN · (3) close the
task list and its rows with those verdicts · (4) the session log — one file for this session plus one index
line (a recommendation; each project owns its log) · (5) rewrite the handoff · (6) run the checks · (7) name
the session, then the final report.

**The start mirrors it.** Before any work, copy Next actions verbatim (the queue freeze), so the wrap can
audit against it, and write the session-start brief to disk beside it — its parts drawn from the handoff:
the state from blocks 2 and 5, the proposed action from block 3's first item, what is waiting from block 4,
pending rulings from block 6. **An ID never stands alone:** every ID-like token in the brief carries words
saying what it is. `python3 tools/handoff.py brief <file>` warns on the ones that don't — a check after the
fact; whether the human can act on the brief stays the human's test.

**Beyond the skeleton, a project's own steps are modules.** Each declares when it runs (always, or on an
event such as "the engine changed"), what must run first, and its pass criteria, fixed in the module; a
module skipped as not needed satisfies its dependents; a check that fails three times stops the run; "today"
means the session, not the calendar date. The schema is `module_schema` in the rule file; the runner that
executes modules comes in a later version.

**Rules leave the handoff by kind:** a fixed-time step goes into the wrap or the start; a rule for certain
files becomes a path-scoped rule; a "stop it before it happens" rule becomes a hook; identity and voice go
to the agent's own file. The handoff carries state, not rules.

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
