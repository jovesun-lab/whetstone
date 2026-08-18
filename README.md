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

| Skill | What it does | Works with any AI / model |
|---|---|---|
| **[Throughline](./handoff-skill/throughline)** | Task-Track & Handoff for AI agents on long, multi-session work — within a session, one ⭐️ MAIN goal anchor in an emoji-tagged task list so reasoning doesn't drift; across sessions or agents, a plain-markdown handoff the next agent re-derives before trusting. | ✅ Yes — prompt-first, agent-agnostic |
| **[Session Measurement](./session-measurement)** | Score an agent session by session and read the trend across versions — so a model / frame / skill change shows up as a real regression or improvement, not a vibe. Six honest counts per session, plain-markdown trend table (optional charts), any agent. | ✅ Yes — any agent |
| **[notify-me](./notify-me)** | Calls you back when an agent needs you — the moment it gets blocked waiting on your decision, it pushes to your phone (via [ntfy](https://ntfy.sh)) and/or chimes on your computer, so you can step away and still know when you're needed. Hook-based, no account, no background process. | ✅ Yes — any agent with hooks |
| **[strain](./strain)** | Tells you when a session has gone bad — before its answers do. Counts how loaded *one* conversation has become and makes the agent report it as a tier on a schedule it can't quietly skip, so you wrap before the work degrades. Reads the real context size where the host exposes one, and says so plainly where it doesn't. | ✅ Yes — prompt-first; auto-fires with hooks |
| _more coming_ | — | — |

## Install as a Claude plugin

Whetstone is a Claude plugin marketplace, so you can install these skills directly in Claude Code
or Cowork:

```
/plugin marketplace add jovesun-lab/whetstone
/plugin install session-measurement@whetstone
/plugin install throughline@whetstone
/plugin install notify-me@whetstone
/plugin install strain@whetstone
```

Installed skills are enabled by default and trigger automatically when relevant. Pull future updates
with `/plugin marketplace update whetstone`. Once Whetstone is accepted into Anthropic's plugin
directory, you'll also be able to find and install these from the in-app Plugins directory
(Customize ▸ Plugins) without adding the marketplace by hand.

## Use in any other agent

Each skill is a self-contained folder. Drop it where your tool reads skills / commands
(Claude Code, Cursor, …), or just paste the relevant file into any agent as a prompt. Start with
each skill's own `README.md`.

## Token footprint

Each Whetstone skill is built to be cheap to keep installed and modest to use (per skill,
approximate, tokenizer-dependent):

- **Installed, idle:** ~250 tokens — only the trigger description sits in context.
- **When it fires:** a few thousand tokens — the skill body plus whatever it produces (e.g. a
  Throughline session that writes one handoff runs ~3–5k).
- **Optional scripts / validators:** 0 model tokens — they run as code.

On progressive-disclosure hosts (Claude Code, Cursor) you pay the ~250 baseline and spend the rest
only when a skill actually fires — and triggers are scoped so short, one-pass tasks don't load them.

## License

Every Whetstone skill is **MIT** unless noted otherwise. Free to use, modify, embed, redistribute.

---

*Whetstone is by [guxcom](https://guxcom.io). Feedback, issues, and PRs welcome on any skill.*
