# Whetstone

*Small, sharp, agent-agnostic skills that keep an AI agent's work honest.*

A whetstone doesn't make a tool — it keeps its edge true. **Whetstone** is a growing collection of
tiny open-source skills for AI agents: not frameworks, but **disciplines** that keep an agent's
work on-track, high-quality, and easy to hand off.

## What a Whetstone skill is

- **Small and self-contained.** One folder, one job. No build step, no install, no runtime.
- **Agent-agnostic.** Works as a plain prompt in any agent — Claude, OpenAI, Gemini, Cursor, a
  local model — and as a skill / slash command where those exist. Nothing assumes a particular
  platform; every capability degrades gracefully.
- **Prompt-first, optional tooling.** The discipline lives in plain language. Any helper script is
  optional, zero-dependency, and never required.
- **Honest by construction.** Checks are anchored to structure and substance, not vibes — a green
  light has to mean something.
- **Plain words over jargon.** If a reader has to learn a new token for an idea they already know,
  that's a defect, not concision.

## The skills

| Skill | What it does |
|---|---|
| **[Throughline](./handoff-skill/throughline)** | Keep the thread of work intact — within a session (an emoji-tagged task list with one ⭐️ goal anchor) and across sessions or agents (a plain-markdown handoff the next agent re-derives before trusting). |
| **[Session Measurement](./session-measurement)** | Score an agent session by session and read the trend across versions — so a model / frame / skill change shows up as a real regression or improvement, not a vibe. Six honest counts per session, plain-markdown trend table (optional charts), any agent. |
| _more coming_ | — |

## Use one

Each skill is a self-contained folder. Drop it where your tool reads skills/commands
(Claude Code, Cursor, …), or just paste the relevant file into any agent as a prompt. Start with
each skill's own `README.md`.
## Token footprint

Built to be cheap to keep installed and modest to use (approximate, tokenizer-dependent):

- **Installed, idle:** ~250 tokens — only the trigger description sits in context.
- **A session that writes one handoff:** ~3–5k tokens (skill body + a command + the template + the handoff it writes).
- **Optional validator:** 0 model tokens — it's a script.

On progressive-disclosure hosts (Claude Code, Cursor) you pay the ~250 baseline and spend the rest only when it actually fires — and the trigger is scoped so short, one-pass tasks don't load it at all.

## License

Every Whetstone skill is **MIT** unless noted otherwise. Free to use, modify, embed, redistribute.

---

*Whetstone is by [guxcom](https://guxcom.io). Feedback, issues, and PRs welcome on any skill.*
