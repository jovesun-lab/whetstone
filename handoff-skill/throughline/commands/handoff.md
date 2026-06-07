---
name: handoff
description: "Capture this session as a Throughline handoff so any agent can resume it cleanly."
argument-hint: "(optional) what the next session will focus on"
---

Turn what matters about this session into a handoff the next person or agent can pick up cold —
including a different agent on a different platform. Build it from
`templates/handoff.template.md`; that template owns the structure, so reuse its sections instead of
inventing your own.

**Where it goes.** Prefer writing the file somewhere the next session will look — a scratch or
temporary location, or an agreed handoff path, kept out of the working tree. If you can't write
files, just put the whole handoff in your reply: the text is the deliverable, not the file.

**Work through the template's sections, keeping each lean:**

- **⭐️ Goal** — the single thing the next session exists to do, as one re-readable sentence. Keep
  exactly one anchor, at the *start* of its line (`⭐️`, or the plain-text `[MAIN]`, or a
  `main_goal: true` line — a star buried mid-sentence doesn't count). If an argument was given,
  read it as that focus and shape the rest of the doc around it.
- **State** — the live picture right now. Flag anything you haven't verified.
- **Done** — what got finished, in a line or two.
- **Open / Next** — what's unresolved, plus the move you'd make next, most important first.
- **Re-derive on pickup** — spell out what the next agent should reconcile against reality before
  believing this doc: which files to reopen, which check to rerun, which numbers to re-confirm.
  Leaving this out is how a stale snapshot quietly turns wrong.
- **Suggested next steps / tools / skills** — the concrete first actions, plus the capabilities to
  reach for. Describe the capability, not one app's button.
- **References** — link out to anything that already lives elsewhere (a plan, an issue, a commit, a
  diff, a doc) by path or URL.

**Three habits while you write:**

- **Link, don't restage.** If a fact already lives in another artifact, point to it rather than
  copying it in — a copy is one more thing that can fall out of date.
- **Strip anything sensitive.** No keys, tokens, credentials, or personal data should survive into
  the doc. Check before you hand it over.
- **Stay short and current.** A handoff is the latest state plus pointers, not a transcript. Send
  people to the longer record instead of reproducing it.

If you can run code, `python3 tools/handoff.py check <file>` confirms the sections, the single goal
anchor, and the re-derive content, and warns on obvious secrets. It's optional — the document is
complete without it.
