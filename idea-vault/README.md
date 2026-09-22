# Idea Vault

✅ Open source (MIT)  ·  ✅ Model-agnostic — runs in any agent that reads skills

*The ideas your sessions produce, kept where the next session finds them.*

Working with an agent produces ideas faster than it executes them — a "we should" in
the middle of a bug hunt, a "next time" right after a ship. They land in chat
scrollback, and scrollback is where ideas go to die. Idea Vault is a skill that makes
the agent catch them: one plain-markdown file, outside any single project, with just
enough structure to come back to.

## What it does

- **Capture on trigger.** "Good idea", "we should", "next time", "/idea" — the agent
  restates the idea in one sentence, shows a short preview card, and asks before
  saving. Never silently.
- **One vault, every project.** Entries carry project, status, priority, effort, tags,
  an optional reminder date, and a checklist. Default home: `~/IdeaVault/ideas.md`
  (asked once on first use).
- **A digest when a session opens.** Stale `new` items, anything `in-progress`, and
  reminders that have come due — five lines, at the top of the first real reply. This
  is the half that makes the vault alive: capture without review is a write-only
  notebook.
- **Review by question.** "Show my ideas", "any open ideas for X?", "what did I add
  this week", "what's overdue".
- **An archive that never rewrites history.** Done and dismissed entries move to
  `archive.md` with a closed date; nothing is edited in place.

## What it is

A single SKILL.md. No hooks, no scripts, no background process, no account. The vault
is a text file you can read, edit, and version yourself — the skill preserves anything
it doesn't understand.

## Honest limits

- Reminders fire **when a session opens**, not at the clock time — there is no daemon.
  A vault nobody opens stays quiet.
- One machine, one file. Sync across machines is your own business (the file lives
  happily in any synced folder).
- The digest depends on the agent actually reading the skill at session start; a host
  that loads skills lazily may need the user to ask once.

## Install

From the whetstone marketplace:

```
claude plugin install idea-vault@whetstone
```

Or copy `skills/idea-vault/SKILL.md` into any agent that reads skill files.

## Companions

From the same family: **throughline** (one ⭐️ MAIN goal per session, handoffs across
sessions) and **strain** (when to wrap a session before its answers degrade). Idea
Vault is the third leg: what to come back to, once the current thread is done.
