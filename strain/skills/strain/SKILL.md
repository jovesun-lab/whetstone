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
| **A context compaction** | **stated, never a tier input** | the tick says "compaction #N"; re-read your goal and handoff |

Soft signals are colour, not ladder. Hard signals are ABSOLUTE — the same on any window
size — but only the ones that **escaped** move the tier. A caught-and-fixed error is a
working immune system, not exhaustion: say so, record it, and let a repeat of the same
class earn a *pattern note* instead of a tier. Record every hard signal when it happens,
so the counters know what you know:

```
bash <strain>/scripts/strain-signal.sh <kind> --caught|--escaped
```

**Copy the full command from the tick line** — it carries this session's key, the state
folder and the plugin's absolute path. `$CLAUDE_PLUGIN_ROOT` exists only inside the hook
process, never in your shell, so a command built on it fails (fixed in 0.7.0).

A compaction cuts the context. Every tick after it says so ("compaction #N"), and a
one-time recovery directive asks you to re-read your goal and handoff — but it never
raises the tier: the fill after it is what measures the load (0.7.0).

## The tiers

Two lines are scored separately and the higher one wins. The tick computes and PROPOSES
the tier; your job is to confirm it or adjust it with what the counters cannot see.

- **Line A — capacity:** fill against caps **50 / 60 / 70 / 74%** → Mid / High / Warning /
  Danger (Danger is derived = throttle onset 80 − wrap budget 6, so a mandated wrap can
  finish before the model degrades). It **abstains** when the number cannot be trusted.
- **Line B — conduct:** escaped signals — 0–2 move nothing · 3 → Mid · 4 → High · 5+ →
  Warning. A burst usually shares one root cause (a capability gap), not exhaustion.
- **Combination:** fill already at Warning/Danger **and** 3+ escaped → Danger.
- **UNMEASURED** (0.7.0): Line A abstains and Line B says nothing → the proposal is
  `UNMEASURED`, never Healthy. Say you are counting behaviour only, and feed the host's
  own reading if it shows one (`strain-level.sh <tier> --ctx-used <n> --ctx-source "<where>"`).

| Tier | Fill cap | Also reached by | What it means |
|---|---|---|---|
| **Healthy** | under 50% | — | carry on |
| **Mid** | 50–60% | 3 escaped signals | fine, but the end is in sight |
| **High** | 60–70% | 4 escaped signals | wrap after the current thread |
| **Warning** | 70–74% | 5+ escaped signals | wrap now; new work should start fresh |
| **Danger** | 74%+ | Warning-level fill **plus** 3+ escaped | stop and hand off |

The caps are printed in every readout (the boot line and every tick show the same ones)
and are configurable; retune them to your setup.

**Escalate only on evidence, never on momentum.** Ticks accumulating is not evidence; a
previous high reading is not evidence. Fill crossing a band and fresh escaped signals
are the only ladders — and strain DECAYS: when the proposal comes in lower than the
carried tier and nothing new happened, record the lower tier. Floors from escaped
signals hold; everything else is allowed to relax. (The old
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
bash <strain>/scripts/strain-level.sh <Healthy|Mid|High|Warning|Danger>
```

(Again: copy the filled command from the tick line.)

An unrecorded tier is how this reading silently sits at its first value forever while
every check around it runs correctly.

## Wrapping

When the tier says wrap, wrap — and stamp it at the handoff:

```
bash <strain>/scripts/strain-wrap.sh --label "what was handed off"
```

A stamp means **this session wrapped / handed off** — not "the work is right" (that is
your project's own check). It resets nothing (0.7.0): a new session starts at zero
anyway, and resetting a session that keeps working in the same full context would hide
real load. If you keep working after the stamp, the tick says so ("N calls since the
wrap") — re-run it at the next handoff.

**Sign early** (once you know who you are), especially when another agent or a later
session will work the same project:

```
bash <strain>/scripts/strain-sign.sh --agent <your-name> [--ledger ./Log.strain]
```

With a ledger (an append-only account book: boot-sign and wrap rows), the FIRST sign of a
session also reports the previous session of the same agent — its tool calls,
compactions, errors escaped and caught, whether it wrapped and whether it kept working
after — so a handoff arrives with its numbers. It only reads; nothing is carried over.

**If the sign itself fails because your shell cannot reach the state home** (a
sandboxed or remote session), do not silently stay unsigned — deliver the sign by
hand: give the user ONE copy-paste line for a plain terminal on the host, with
everything filled in (the session id as `STRAIN_SESSION=…`, your `--agent` name, the
ledger path if the project has one — see "Signing from a bare terminal" in the
README). Put the command alone in its own code block, the steps outside it. The
`Owner: … — signed` line the user pastes back is your receipt; until it arrives,
report yourself as measured-but-unsigned, never as signed.

Strain says *when* to hand off. It does not do the handing off. Its companion for that is
**[Throughline](../../../handoff-skill/throughline)**, whose task track is also the
cleanest source for the behavioural counts above: one main goal anchor, every other task
tagged. If you use both, strain reads what throughline already records.

## Honest limits

- **Hooks are per-host.** Where they exist, the check fires whether or not the agent
  remembers. Where they do not, it is a discipline the agent has to keep — weaker, and
  worth naming out loud rather than papering over. On a hook-less host, adopt the
  manual cadence yourself: run the check every ~10 tool calls or at each milestone.
- **Context auto-parsing knows one host's transcript shape** (Claude Code's). On other
  hosts strain runs in counted mode even when the host shows its numbers on screen —
  in that case YOU are the adapter: record the window once
  (`strain-calibrate.sh --window <n> --basis nominal|runtime --source "<where>"`) and
  feed the usage at recording time (`strain-level.sh <tier> --ctx-used <n>
  --ctx-source "<where>"`). A fed reading is labelled agent-fed with its source —
  never report it as something strain measured itself.
- **Thresholds are guesses** until you retune them. They came from one agent-and-user pair
  over a long run; yours will differ.
- **The soft signals are judgement calls.** Counting them honestly is the whole job; a
  tier that is always Healthy is not a healthy session, it is a broken check.
