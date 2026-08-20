# Session Measurement v0.1.1

*Score an agent session by session; read the trend across versions.*

## What's new in 0.1.1

Alignment with its Whetstone siblings — the metric spine is untouched:

- **Verdict vocabulary unified with Throughline 0.2.0.** `MAIN landed`'s `L / P / N` is the
  same enum Throughline uses at goal close (`LANDED / PARTIAL / NOT-LANDED`, under the goal's
  frozen title, with evidence). If the project writes Throughline handoffs, the Done section's
  verdicts are a ready-made, already-grounded source for this attribute — read, don't re-derive.
- **New optional attribute: `strain tier at wrap`** (`Healthy / Mid / High / Warning / Danger`,
  from the strain skill's wrap reading). An attribute like `version`, not a spine metric — it
  lets the trend answer "do the bad sessions correlate with running long?" without changing
  what is measured. Omit it if the project doesn't run strain.
- License attribution → arcgram.io.

---

# Session Measurement v0.1.0 (original release)

**A tiny, agent-agnostic skill that turns each finished session into a small set of honest counts and tracks them as a long-run trend — so a change to the model, the frame, or the skills shows up as a real regression or improvement, not a vibe.**

## The problem

You change something about an AI agent and you want to know whether it helped. But:

- **A single session is noise.** One good or bad run tells you almost nothing — low-conflict sessions look great, hard ones look bad, regardless of the change.
- **"Feels better" doesn't compound.** Without a stable yardstick read the same way every time, improvements and regressions blur together and you ship the wrong conclusion.

## What it is

Per session, six counts (green = strength, red = weakness):

- **Redefinitions absorbed** — folded a moving goalpost in without dropping a constraint.
- **Clarifying gates raised** — asked instead of guessing on a genuine ambiguity.
- **Errors the agent self-caught** — caught its own mistake before the human.
- **Misses the human caught** — had to be sent back.
- **Critical bugs — agent caught / human caught** — severe defects, split by who caught them.

Plus **version** (model/frame/build — so trouble reads against what changed) and **MAIN landed** (`L`/`P`/`N` — did the goal land). Kept in a plain-markdown trend table you read across versions.

The load-bearing idea: **the markdown trend table is the measurement, and the disciplines are what make it trustworthy.** Everything else (the chart) is decoration.

## Why it's built this way

- **Agent-agnostic, markdown-first.** The metric frame, the disciplines, and the canonical output are pure prompt — they run as a skill, a slash command, or a pasted-in prompt on Claude / OpenAI / Gemini / Cursor / Cline / a local model. The markdown table needs no code and no dependencies, so it works even on a host that can't execute anything. An optional Python helper renders charts; it never replaces the table.
- **Honest by construction.** The disciplines are the point: prefer full reads and flag estimates; **never fabricate** a number you can't retrieve (an empty cell is honest, a made-up one corrupts the trend); ground counts against an authoritative record instead of a snapshot; hold the "critical" bar to *severe* defects; and when an agent scores its own work, the human-caught rows are the anchor that can't be self-flattered.
- **Completion that discriminates.** A raw tasks-done/total rate is ~100% every clean session and says nothing; **MAIN landed** measures whether the *goal* landed, which is the signal that actually moves.
- **Configured once, per project.** Three things vary — where transcripts come from, what "critical" means in this domain, what the version axis tracks — and live in a tiny `config.json` the agent can propose for you on first run. Everything else is universal.

## What's in the box

- `skills/session-measurement/SKILL.md` — the skill body: trigger, run loop, metric spine, first-run config onboarding.
- `references/methodology.md` — how to count each metric honestly, the critical definition, the disciplines.
- `references/config-template.md` — the per-project config + field notes.
- `references/log-template.md` — the persistent log structure.
- `tools/render_benchmark.py` — the **optional** chart renderer (Python + cairosvg).
- `examples/` — a neutral worked example + a `sessions.json`.
- `assets/logic-flow.svg` — the flow, color-coded by what's universal vs config vs optional.

## Compatibility

Works as a skill / plugin where those exist (Claude Code, Cursor, …) and as a plain paste-in prompt anywhere else. The only thing it needs is access to the session content — a reader tool, or the transcript pasted in. MIT.
