---
name: idea-vault
description: "Cross-project idea capture and review. A notebook-with-reminders that logs the user's ideas, plans, and checklists across every project, in one plain-markdown file. Use this skill whenever the conversation contains a new idea, plan, or intention the user might want to save for later, and whenever a project milestone, task completion, or session wrap-up is a natural moment to review or capture ideas. Triggers on: new idea, good idea, plan to do, I want to, we should, wouldn't it be cool if, next time, save this, add to idea vault, /idea, milestone reached, task done, shipped, launched, wrap up, show my ideas, review ideas, what did I add this week, what's overdue."
---

# Idea Vault

A lightweight, cross-project notebook for capturing ideas the user wants to come back
to — with checklists, priority, status, and optional reminders. The data lives in one
plain-markdown file outside any single project, so ideas from different projects all
land in the same place.

---

## Vault location

**Default data file:** `~/IdeaVault/ideas.md`
**Default archive file:** `~/IdeaVault/archive.md`

On first use: check the default location. If no vault exists there, ask the user ONCE
where the vault should live (accepting the default is fine), create the files from the
templates below, and remember the chosen path — in your persistent memory or the user's
agent config file, if your harness has one. From then on, always read and write that
path. Never scatter vault files per project: one vault, every project.

---

## Entry schema

Each idea is one block in `ideas.md`, separated by `---`. Newest entries go on top.

```markdown
## [YYYY-MM-DD] Idea title
- **Project:** {project name or "General"}
- **Status:** new | planned | in-progress | done | archived
- **Priority:** high | medium | low
- **Effort:** S | M | L
- **Tags:** #tag1 #tag2
- **Remind on:** YYYY-MM-DD  _(optional)_
- **Depends on:** {idea title}  _(optional)_

{one-to-three-sentence description — what, why, context}

**Checklist:**
- [ ] sub-task 1
- [ ] sub-task 2

**Source:** "{optional short quote from the conversation}"

---
```

`YYYY-MM-DD` is always today's absolute date. Resolve "today", "tomorrow", "next week"
to absolute dates before writing — a relative date in a file that outlives the
conversation is a date nobody can trust.

---

## When to trigger

### Phrase triggers (offer to save)

Treat any of these as a signal to offer capture. **Never save silently — always confirm
first.**

- "new idea", "good idea", "I have an idea"
- "plan to do", "I want to", "I'd like to", "we should"
- "wouldn't it be cool if", "what if we", "next time"
- "save this", "remember this", "add to idea vault"
- "/idea" (explicit command)

### Event triggers

Offer to capture or review at these moments:

- A task completes successfully (build passes, deploy ships, refactor lands)
- A project reaches a stated milestone
- The user says "shipped", "launched", "done with X", "wrap up"
- Start of a new session — if there are stale `new` or `in-progress` items, show a
  short digest (see Session-open digest below)

### Review triggers

- "show my ideas" / "what's in the vault"
- "review ideas" / "any open ideas for {project}?"
- "what did I add this week" / "this month"
- "what's overdue"

---

## Capture workflow

When a trigger fires:

1. **Restate** the idea in one sentence so the user can verify intent.
2. **Show a preview card** — a short block with proposed title, project, priority, and
   any checklist items inferred from the conversation.
3. **Ask**: Save / Edit first / Skip — using whatever confirmation mechanism your host
   provides (an in-chat question is fine). If the idea is vague, ask ONE clarifying
   question first (what project, what tag) — never more than one at a time.
4. If **Save**:
   - Read the current `ideas.md` (if it doesn't exist, create it from the template).
   - Prepend the new entry under the file header.
   - Stamp with today's absolute date.
5. Reply with a one-line confirmation and the file path.

Keep the preview card short. A capture that takes longer than the idea did is a capture
the user will stop asking for.

---

## Status lifecycle

```
new → planned → in-progress → done → archived
```

- `new` — just captured, not committed to
- `planned` — the user has decided to do it
- `in-progress` — actively being worked on
- `done` — completed
- `archived` — dismissed, superseded, or completed and aged out

### Status commands

- "mark {title} as in-progress"
- "mark {title} as done"
- "archive {title}"
- "move {title} to planned"

When marking `done` or `archived`, move the entry from `ideas.md` to `archive.md`
(prepend, with a `**Closed:** YYYY-MM-DD` line added).

---

## Session-open digest

At the start of a new session, if the conversation is likely to touch an active
project, quickly scan `ideas.md` for:

- Items with `Status: new` older than 7 days
- Items with `Status: in-progress` (any age)
- Items where `Remind on:` is today or earlier

Surface them as a short bullet list titled **"Open from the idea vault:"** near the top
of the first substantive reply. Five items max — if more, say "and N more — say 'show
my ideas' to see all".

Do not force this into conversations with no project context (one-shot factual
questions, casual chat).

---

## Review commands

### "show my ideas"
List all non-archived ideas, grouped by `Status`, sorted by priority within each group.
Compact — one line per idea with title, project tag, priority.

### "show {project} ideas"
Filter by project tag.

### "what did I add this week" / "this month"
Scan dates, return entries grouped by week/month.

### "what's overdue"
Entries where `Remind on:` is earlier than today and status is not `done` or
`archived`.

---

## Reminder field

When the user says "remind me on {date}" or "for next week" or similar:

- Parse to an absolute `YYYY-MM-DD`.
- Add a `Remind on:` line to the entry.
- Surface the item in the session-open digest on or after that date.

"Remind me in three days" → today + 3. "Next Monday" → the next Monday after today.
Reminders fire when a session opens — this skill has no background process, so a vault
nobody opens is a vault that stays quiet (see Honest limits).

---

## Writing style

- Keep language simple and direct — the vault may be read months later, out of context.
- Idea titles: concrete and short (≤ 60 chars). "Add AI parser for feedback files" —
  not "Implement a comprehensive AI-driven parsing subsystem".
- Descriptions: one to three sentences, plain words. No marketing phrasing.
- Use the project's own canonical terminology when the idea belongs to a project that
  keeps a glossary.

---

## Files not to modify

- Archived entries — do not rewrite history. Only prepend to `archive.md`.
- Ideas marked `in-progress` — do not silently change their content. If the user is
  updating one, confirm the change first.

---

## Initial templates

If `ideas.md` does not exist, create it with this header:

```markdown
# Idea Vault

Cross-project notebook for ideas, plans, and things to come back to. Newest on top.
Managed by the `idea-vault` skill — hand edits are fine; the skill preserves anything
it doesn't understand.

---

```

And `archive.md`:

```markdown
# Idea Vault — Archive

Done and dismissed entries. Newest on top.

---

```

---

## Example capture

> User: "oh good idea — next time we ship, we should add a changelog page to the docs
> site"

1. Restate: "I'd capture that as: add a changelog page to the docs site, triggered when
   the next version ships."
2. Preview card:
   ```
   Title: Add changelog page to docs site
   Project: Docs
   Priority: medium
   Tags: #feature #post-launch
   ```
3. Ask: Save / Edit / Skip.
4. On Save: prepend to `ideas.md`, stamp today's date, reply with one line + the path.
