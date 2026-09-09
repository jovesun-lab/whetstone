---
name: strain
description: >-
  Read how loaded the current session has become and report it as a tier, so a
  conversation gets wrapped before its answers start degrading. Use whenever someone asks
  how the session is holding up, whether it is time to wrap or start fresh, why the agent
  feels sluggish or forgetful; whenever a strain tick fires; and as a standing habit on
  long multi-hour work. Triggers on: session strain, is this session too long, should we
  wrap, context is filling up, running out of context, start a fresh session, why is the
  agent getting worse, session health, strain check, strain tier. Counts the real context
  size where the host exposes one, and counts behaviour where it does not. Not for short
  one-pass tasks — there is nothing to measure.
---

# Strain

A long session degrades before it fails. The context window fills, the same problem comes
back a third time, an earlier answer turns out to be wrong — and the work keeps going,
because nothing in the loop is watching the loop. Strain is the thing that watches: a
small, countable reading of how loaded this conversation has become, reported on a
schedule, in a form the user can act on.

The failure this exists to prevent is not a crash. It is **silence** — the agent that
never mentions the session has gone bad, and lets the user find out from the output.

## The one rule

**One session, one reading.** Strain measures a single conversation, identified by its
session id. Two agents working the same project in two windows are two sessions and their
counts never add up. If you cannot tell which session a number belongs to, it is not a
measurement.

## When to run the check

Run it when any of these happen — not on a feeling that it might be time:

1. **A strain tick fires.** On hosts with hooks, a tick arrives every N tool calls
   (default 10) and says so explicitly. Run the check before continuing the work.
2. **A hard signal lands** (see the table below) — a factual error caught, a regression
   introduced, a revert of your own work, a context compaction.
3. **The task list changes shape** — a new side task, a goal switch, a task that balloons
   past the one it was supposed to serve.
4. **The user asks** how the session is doing, or whether to wrap.

On a host with no hooks, 2–4 still work. That is the cooperative half, and it is weaker:
say so rather than implying the check is firing on its own when it is not.

## What to count

Two inputs, and they are not equally strong.

### Context occupancy — measured, when the host allows it

Some hosts publish a per-session transcript carrying token usage. Where that exists, the
context reading is a real number, not an impression:

- **current** = the input side of the most recent turn (`input + cache_read +
  cache_creation` — cached tokens are still context the model is carrying)
- **baseline** = the same sum on the first turn: what the boot alone cost before any work
  happened. System prompt, tool schemas, project instructions, skills. It is the floor the
  session can never get back under, and it is usually larger than people expect.

The tick directive quotes both when it can. When it cannot, it says so — and then you
count behaviour instead. **Never quote a context number you did not measure.**

### Behavioural signals — always available

| Signal | Weight | How it is counted |
|---|---|---|
| Distinct subjects touched | soft | count of side tasks + goal switches in the task list |
| A side task that balloons past the main one | soft | it spawned sub-tasks of its own |
| A problem that came back | soft | it was already solved once this session |
| Critical / blocking tasks open | soft | count them |
| A second main goal appeared | soft | more than one thing claims to be the point |
| **A factual error that ESCAPED to the user** | **hard, escaped** | one per error; record it |
| **A regression that reached shipped work** | **hard, escaped** | one per regression; record it |
| **An error you caught and fixed pre-delivery** | **hard, caught** | recorded, tiers nothing |
| **A revert of your own work** | **hard** | escaped if the user saw the churn |
| **A context compaction** | **hard** | the host compacted; the session has run long |

Soft signals are colour, not ladder. Hard signals are ABSOLUTE — the same on any window
size — but only the ones that **escaped** move the tier. A caught-and-fixed error is a
working immune system, not exhaustion: say so, record it, and let a repeat of the same
class earn a *pattern note* instead of a tier. Record every hard signal when it happens,
so the counters know what you know:

```
bash "$CLAUDE_PLUGIN_ROOT/scripts/strain-signal.sh" <kind> --caught|--escaped
```

A compaction is not a fresh start — it is the clearest evidence there is that the
session has run long.

## The tiers

Fill is the PRIMARY signal: what fraction of the detected context window is occupied.
The default bands are **40 / 60 / 75 / 85%**, calibrated to the window the plugin
detects at boot (a 200k and a 1M session get different absolute budgets from the same
bands — no per-host table). The tick computes and PROPOSES the tier; your job is to
confirm it or adjust it with what the counters cannot see.

| Tier | Fill band | Also reached by | What it means |
|---|---|---|---|
| **Healthy** | under 40% | — | carry on |
| **Mid** | 40–60% | — | fine, but the end is in sight |
| **High** | 60–75% | 1 escaped signal, or 1 compaction | wrap after the current thread |
| **Warning** | 75–85% | 2+ escaped signals, or 2+ compactions | wrap now; new work should start fresh |
| **Danger** | 85%+ | Warning-band fill **plus** an escaped signal | stop and hand off |

The bands are printed in every readout and are configurable; retune them to your setup.

**Escalate only on evidence, never on momentum.** Ticks accumulating is not evidence; a
previous high reading is not evidence. Fill crossing a band and fresh escaped signals
are the only ladders — and strain DECAYS: when the proposal comes in lower than the
carried tier and nothing new happened, record the lower tier. Floors from compactions
and escaped signals hold; everything else is allowed to relax. (The old
"continuing past a Warning ⇒ Danger" rule is deleted — it pinned Danger at a measured
33% fill, three sessions running.)

## How to report it

Match the shape to the tier. The point is that the user can act without asking follow-ups.

- **Healthy** — one line, or nothing at all if the user did not ask. Do not pad.
- **Mid / High** — the counts, and a suggestion to wrap soon:
  > 🟡 High — context 136k/200k (68%), of which 70k was the boot. 1 main goal, 3 side
  > tasks. Suggest finishing the current thread and wrapping.
- **Warning / Danger** — the counts, **which hard signals fired and whether they
  escaped**, why it matters, and a recommendation to wrap now:
  > 🔴 Warning — context 158k/200k (79%), 2 compactions, 1 escaped regression. The fix
  > shipped broken and the window is nearly full. Recommend wrapping and starting
  > fresh; I will write the handoff first.

Then **record it**, so the next tick carries it forward instead of starting over:

```
bash "$CLAUDE_PLUGIN_ROOT/scripts/strain-level.sh" <Healthy|Mid|High|Warning|Danger>
```

An unrecorded tier is how this reading silently sits at its first value forever while
every check around it runs correctly.

## Wrapping

When the tier says wrap, wrap — and mark it, because that is the only thing that resets
the counters:

```
bash "$CLAUDE_PLUGIN_ROOT/scripts/strain-wrap.sh" --label "what was finished"
```

A wrap means the work is actually closed: the handoff is written, the tests are green,
the thing is done. Recording that a session felt heavy and declaring it finished are
different claims — do not let one imply the other.

Strain says *when* to hand off. It does not do the handing off. Its companion for that is
**[Throughline](../../../handoff-skill/throughline)**, whose task track is also the
cleanest source for the behavioural counts above: one main goal anchor, every other task
tagged. If you use both, strain reads what throughline already records.

## Honest limits

- **Hooks are per-host.** Where they exist, the check fires whether or not the agent
  remembers. Where they do not, it is a discipline the agent has to keep — weaker, and
  worth naming out loud rather than papering over.
- **Thresholds are guesses** until you retune them. They came from one agent-and-user pair
  over a long run; yours will differ.
- **The soft signals are judgement calls.** Counting them honestly is the whole job; a
  tier that is always Healthy is not a healthy session, it is a broken check.
