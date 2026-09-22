# Changelog

## 0.1.0 — 2026-09-21

**First public release.**

- Capture-on-trigger with confirm-before-save (restate → preview card → ask).
- One cross-project vault: plain-markdown `ideas.md` + `archive.md`, default
  `~/IdeaVault/`, asked once on first use.
- Entry schema: project, status lifecycle (`new → planned → in-progress → done →
  archived`), priority, effort, tags, optional reminder date, checklist, source quote.
- Session-open digest: stale `new` (>7 days), all `in-progress`, due reminders —
  five items max.
- Review commands: by status, by project, by week/month, overdue.
- Archive discipline: entries move, history is never rewritten.
- Pure skill — no hooks, no scripts, no account.
