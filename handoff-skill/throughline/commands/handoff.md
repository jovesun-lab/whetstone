---
name: handoff
description: "Capture this session as a Throughline handoff so any agent can resume it cleanly."
argument-hint: "(optional) what the next session will focus on"
---

Turn what matters about this session into a handoff the next person or agent can pick up cold —
including a different agent on a different platform. Build it from
`templates/handoff.template.md` (at the plugin root); that template owns the structure, so reuse its sections instead of
inventing your own.

**Where it goes.** Prefer writing the file somewhere the next session will look — a scratch or
temporary location, or an agreed handoff path, kept out of the working tree. If you can't write
files, just put the whole handoff in your reply: the text is the deliverable, not the file.

**Work through the template's sections, keeping each lean:**

- **Machine fields** — name the session writing this (its id and number, the agent, model and host,
  times in UTC), one verdict line per MAIN copied from Done, and a file-hash table. One boot = one
  session: if this conversation already wrapped once and kept going, it's still the same session —
  don't mint a second identity for it.
- **⭐️ Goal** — the next session's MAIN, proposed for the human to confirm at the next start, as one
  re-readable sentence; the same text as Next actions #1. Keep exactly one anchor, at the *start* of
  its line (`⭐️`, or the plain-text `[MAIN]`, or a `main_goal: true` line — a star buried
  mid-sentence doesn't count). If an argument was given, read it as that focus.
- **Where this session stopped** — the live picture right now. Flag anything you haven't verified.
- **Done** — close every MAIN this session carried, **under its frozen title**: `### MAIN: <title> —
  LANDED | PARTIAL | NOT-LANDED`, the evidence, and its 🔸 subtasks, each `done`, `carried → <row>` or
  `dropped · human: "<their words>"`. LANDED needs every subtask done. No silent closes; a redirected
  goal takes its honest NOT-LANDED and the new direction gets its own entry. A session with no MAIN
  writes `zero-MAIN · human: "<their words>"`.
- **Next actions** — ranked, one line each, each ending with its durable row (` · <row ID or path>`).
- **Waiting on others** — what the human and other agents owe, or "none".
- **Project state** — the project's own facts (versions, hashes, the last check), or "none".
- **Rulings not yet home** — this session's decisions in full, each with the row or file it must reach;
  earlier ones by pointer. "none" if none.
- **Re-derive on pickup** — spell out what the next agent should reconcile against reality before
  believing this doc: which files to reopen, which check to rerun, which numbers to re-confirm —
  and **what result to expect** from each. Leaving this out is how a stale snapshot quietly
  turns wrong.

**Three habits while you write:**

- **Link, don't restage.** If a fact already lives in another artifact, point to it rather than
  copying it in — a copy is one more thing that can fall out of date.
- **Strip anything sensitive.** No keys, tokens, credentials, or personal data should survive into
  the doc. Check before you hand it over.
- **Stay short and current.** A handoff is the latest state plus pointers, not a transcript. Send
  people to the longer record instead of reproducing it.

**The wrap is atomic with the end of the work.** If more work lands after the handoff is
written — the "wait, one more thing" pattern — the snapshot is stale the moment that work
starts. Re-run this whole operation and capture the new state; a stale handoff misleads the
next session worse than no handoff at all.

If you can run code, `python3 tools/handoff.py check <file>` confirms the sections, the single goal
anchor, and the re-derive content, and warns on obvious secrets. It's optional — the document is
complete without it.
