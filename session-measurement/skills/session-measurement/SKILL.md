---
name: session-measurement
description: >-
  Measure an AI agent's per-session performance on a small, stable metric set and
  track it as a trend over a long run, so you can tell whether a change — a new model
  version, a new operating frame/scaffolding, a new skill set — actually improved the
  agent or regressed it. Use this whenever someone wants to benchmark, score, grade,
  or track an agent's performance across sessions; compare two agent versions or
  frames; build a "did this change help?" scorecard; or turn a finished session into a
  logged measurement. Triggers on: agent benchmark, session measurement, performance
  trend, score this session, grade the agent, A/B an agent version, regression
  tracking for an agent, "is the new model/frame better?", agent report card. Reach
  for it even if the user just says "measure how that session went" or "track this
  over time" without naming a metric.
license: MIT
---

# Session measurement — agent performance benchmark

> **For any AI agent reading this file.** The frontmatter uses Claude's skill format; the
> body is plain markdown. It works the same for Claude, OpenAI, Gemini, Cursor, Cline, Aider,
> or a local model — paste the body in as a prompt if your platform has no skill system.
> Assume **nothing** about your host's capabilities; everything here degrades gracefully.

You turn a finished agent **session** into a row of objective counts, record it in a
running **trend table**, and append it to a persistent log. Do this every session and the
trend tells you, over a long run, whether the agent is getting better or worse as its
model / frame / skills change.

**The canonical output is a plain-markdown trend table** — no code execution, no
dependencies, works for literally any agent (even one that can't run code). A polished
chart image is an *optional* add-on for hosts that can render one; it's presentation, not
the measurement. So the irreplaceable core of this skill is the **metric frame + the
counting disciplines + the data**, not any particular renderer.

This skill is **agent-agnostic and user-agnostic**. The metric frame and the disciplines
below work for any agent. Three things vary per project and live in a small `config.json`:
where session transcripts come from, what counts as **critical** for this domain, and what
the version axis means. On first use you set that config up (below), then every run reuses it.

---

## The metric spine (keep these constant — comparability over time is the whole point)

Six counts per session. Green = a strength (higher is better); red = a weakness (higher
is worse). Plus two per-session attributes (version, main-goal outcome).

| Metric | Color | Counts |
|---|---|---|
| Redefinitions absorbed | green | times the task was redefined and the agent folded the change in **without dropping** earlier constraints |
| Clarifying gates raised | green | times the agent **asked** instead of guessing on a genuine ambiguity/conflict |
| Errors the agent self-caught | green | flaws the agent caught in its **own** output before the human did |
| Misses the human caught | red | factual/craft misses the human had to send back |
| Critical bugs — agent caught | green | **severe** defects (see below) the agent caught itself |
| Critical bugs — human caught | red | severe defects that slipped to the human |

Two attributes carried alongside (plus one optional):
- **version** — which model / frame / build the session ran on (so trouble reads against version).
- **MAIN landed** — did the session's main goal land? `L` landed · `P` partial (reframed,
  shipped-with-a-regression, or one-of-two) · `N` not-landed (nothing shipped, reverted,
  or the session never wrapped). This is the task-completion signal. (A raw
  tasks-done/total rate is near-100% every clean session and tells you nothing — whether
  the *goal* landed is the discriminating signal.)
  `L / P / N` is the same verdict vocabulary our companion skill
  [Throughline](../../../handoff-skill/throughline) uses when a goal closes
  (`LANDED / PARTIAL / NOT-LANDED`, under its frozen title, evidence attached). If the
  project writes Throughline handoffs, the **Done** section's verdicts are a ready-made,
  already-grounded source for this attribute — read them instead of re-deriving.
- **strain tier at wrap** *(optional)* — how loaded the session was when it closed
  (`Healthy / Mid / High / Warning / Danger`), read from the
  [strain](../../../strain) skill's wrap reading if the project runs it. Not a spine
  metric — an attribute, like version: it lets the trend answer "do the bad sessions
  correlate with running long?" without changing what is measured. Omit if not tracked.

**"Critical" — the severe tier (default; a project may extend it in config):**
1. **Task forgetting** — a committed or in-progress task silently dropped.
2. **A previously-fixed bug recurs 2+ times** — the same defect keeps coming back.
3. **A bug that breaks existing functionality** — a working feature stops working, or the
   system dead-loops.

Critical is for *severe* defects, not craft nits (text overflow, an awkward report, a
small style miss — those live in self-caught / misses). Keep the bar high or the critical
rows stop meaning anything.

See `references/methodology.md` for fuller definitions, edge cases, and how to count
honestly.

---

## First run: set up the project config

Before the first measurement, create a `config.json` next to your `sessions.json`. There
are **two ways** to fill it — offer the user both:

- **Agent-proposes, user-supplements (default, guided).** Inspect the current project:
  what transcript source is available here, what kind of agent/work this is, what a
  "critical" defect would mean for this domain, what the version axis should track. Draft
  a `config.json` from that and show it to the user to confirm or top up. This is the
  light path — the user just reacts.
- **User-provides.** The user hands you the values directly; you write them in.

`config.json` shape:

```json
{
  "project": "what you're benchmarking (agent + project)",
  "version_axis_label": "what 'version' means here, e.g. 'model', 'frame', 'build'",
  "transcript_source": "how to obtain a session transcript in this environment",
  "critical_definition": "the 3 generic criteria PLUS any domain-specific severe defects",
  "grounding_source": "an authoritative record to check counts against, or 'none'",
  "exclusions": "session types to skip (and why), or 'none'"
}
```

Save it. Every later run reads it instead of re-asking. If the project changes shape, edit it.

---

## The run loop (once configured)

When asked to measure a session:

1. **Locate the session.** Use the `transcript_source` from config (a session-reader tool
   if the host exposes one; otherwise an exported/pasted transcript). Confirm you have the
   right session — titles and version numbers drift, so match on content, not just a label.
2. **Read it — full transcript if you can.** Counts derived from a partial/tail read are
   estimates; **say so** in a footnote. A full read is worth it for the sessions that matter.
3. **Derive the six counts** per the definitions. For each, you should be able to name the
   specific moment (which redefinition, which self-catch, which miss) — if you can't point
   at it, don't count it.
4. **Ground against the authoritative record** if `grounding_source` exists (a work log or
   status log, a task tracker, a status doc — or a Throughline handoff, whose per-goal
   verdicts map directly onto `MAIN landed`). Don't trust your own first read or a stale
   snapshot; reconcile. Note where grounding changed a count.
5. **Record it in the markdown log (canonical, zero-dependency).** Add the session's column
   to the markdown trend table and write a short per-session paragraph — what landed, the
   notable catch, the honest miss (`references/log-template.md` shows the structure). This
   markdown *is* the measurement; it works for any agent with no tooling.
6. **(Optional) Render a chart.** If you want a polished visual *and* the host has Python +
   cairosvg, also keep the session in `sessions.json` (shape below) and run
   `python3 tools/render_benchmark.py sessions.json <out_dir>` → a per-session bar chart + a styled
   trend image. If Python isn't available, skip it — or render the table however your host
   does visuals (inline SVG/HTML, a chart library). The chart never replaces the markdown
   table; it just dresses it up.

`sessions.json` shape (only needed for the optional chart renderer):

```json
{
  "project": "...",
  "version_axis_label": "version",
  "sessions": [
    {
      "id": "S1",
      "label": "2026-01-01 - session 1 - what it was about",
      "version": "v0.1",
      "tag": "short logic/change note for the trend header",
      "main_landed": "L",
      "metrics": {
        "Redefinitions absorbed": 3,
        "Clarifying gates raised (asked, not guessed)": 2,
        "Errors the agent self-caught": 2,
        "Misses the human caught": 1,
        "Critical bugs - agent caught": 0,
        "Critical bugs - human caught": 0
      },
      "callouts": {
        "Misses the human caught": ["one or two short lines drawn next to this bar -", "use for the notable finding of the session"]
      },
      "footnotes": ["what shipped + the honest caveat", "tail-read estimate, if applicable"]
    }
  ]
}
```

If you use the renderer, the metric **keys must match exactly** (it looks them up by name).
The critical-bug rows can be omitted on early sessions if the scanner wasn't in use yet —
they show as `-` until a session populates them.

---

## The disciplines that make a measurement trustworthy

These are the heart of the skill — the counts are only as good as the honesty behind them.

- **Prefer full reads; flag estimates.** A tail-read count is a guess wearing a number's
  clothes. Mark it.
- **No fabrication.** If a metric's data genuinely isn't retrievable (e.g. token cost when
  no tool reports it), **leave it out** — an empty cell is honest; a made-up number poisons
  the trend. Don't invent precision you don't have.
- **Ground, don't trust the snapshot.** Reconcile counts against the authoritative record;
  a self-graded "0 misses" off a quick read is exactly what's least reliable.
- **Hold the critical bar.** Severe defects only. If everything is "critical," nothing is.
- **Watch self-measurement bias.** When an agent scores its *own* sessions, the
  human-caught rows are the honesty anchor — they aren't self-reported. Don't let a
  self-graded strength row stand in for them.
- **Note exclusions and ambiguous attributions.** If a session is out of scope, say so. If
  a catch is unclear human-vs-agent, flag it rather than assigning it to flatter the agent.

A measurement that quietly flatters the agent is worse than none — the trend exists to
catch regressions, and it can only do that if the bad sessions show up as bad.

---

## Optional chart rendering

Only relevant if you choose to produce the chart image (step 6). The markdown table is the
real output and needs none of this.

- `tools/render_benchmark.py` needs Python + cairosvg: `pip install cairosvg --break-system-packages` once.
- **No emoji in any rendered text** — the rasteriser has no emoji font; emoji become empty
  boxes. Use plain words and the `L/P/N` letters. (This applies to the script; the markdown
  table can use whatever your reader supports.)
- The trend PNG auto-scales its resolution down as columns grow so it stays previewable;
  the SVG is always full quality for sharing.
- No Python in your environment? Skip the script entirely — keep the markdown trend table,
  or have your agent emit the table as inline SVG/HTML if its host renders that. Nothing
  about the measurement depends on the script.
