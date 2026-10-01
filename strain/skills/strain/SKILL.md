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

Every place below that asks you to DO something is a numbered procedure. Follow the steps
in order and do not skip one because it seems implied. Every command you need is printed,
filled in, in the latest strain tick — copy it from there (it carries this session's key,
the state folder and the plugin's path).

## At the start of a session

1. **Sign.** Run `strain-sign.sh --agent <your name>` (add `--ledger ./Log.strain` if the
   project keeps one). The first strain tick also prints this command, filled in, if you
   have not signed yet.
2. **Tell the user the one sentence it prints** — for example "Strain is on. This
   conversation is 12% full — strain will tell you when it's time to wrap up and start
   fresh." Copy it as it is. The longer "Strain receipt" line goes to stderr for you; do
   not paste it at the user.
3. **If step 1 was refused**, go to *When a record command is refused* below, then come
   back and sign.
4. **If there is a ledger,** the sign also prints one line about the previous session of
   the same agent. Tell the user that line too.

## When the tick fires

A tick arrives every N tool calls (default 10) on hosts with hooks. It says
"🩺 STRAIN TICK" and proposes a tier.

1. **Read the proposed tier and the reason** in the tick.
2. **Check what the counters cannot see:** did an error of yours reach the user since the
   last tick? Did a side task grow past the main one?
3. **If an error reached the user** (or shipped work), record it first:
   `strain-signal.sh <short-name> --escaped`. If you caught and fixed it before anyone
   saw it, record it with `--caught` — that does not move the tier.
4. **Record the tier:** `strain-level.sh <Healthy|Mid|High|Warning|Danger|UNMEASURED>`.
   Record the proposal unless step 2 or 3 gives a reason to change it. A lower proposal
   than last time is allowed — strain goes down when the load does.
5. **If the proposal is UNMEASURED,** follow *When strain cannot measure* below.
6. **Tell the user** in the shape for that tier (*How to report it*).

## When strain cannot measure (UNMEASURED)

UNMEASURED is never Healthy. The tick names the kind; follow the steps for that kind.

**`no source`** — strain found no log it can read.
1. Look where hosts keep usage: a session or usage log, a status or usage command, a usage
   API, the host's settings or status pane.
2. If you find a number, record it: `strain-level.sh <tier> --ctx-used <tokens>
   --ctx-source "<where you read it>" --ctx-provenance host-reported` (or
   `agent-estimated` if you worked it out yourself).
3. If you find nothing, record that: `strain-level.sh UNMEASURED --no-source --checked
   "<the places you looked>"`.
4. The tick repeats the checklist until step 2 or step 3 is done.

**`unusable`** — a source was read but gave no usable number.
1. If the fill is past 100%: tell the user that strain's own arithmetic is off (not their
   session), and quote the used count as a lower bound.
2. Offer a bug report: run `strain-report.sh --note "<what you saw, no paths>"`, tell the
   user where the draft is, and say nothing was sent. They decide whether to send it.
3. If your host shows its own usage number, feed it (step 2 of `no source`).
4. If the number lives in a durable log strain cannot read, draft an adapter proposal the
   same way (`strain-report.sh --note "<where the log is, which fields, one redacted
   sample line>"`). Do not edit the installed plugin.

**`stale`** — a compaction or a model switch came after the last reading.
1. If the host measures itself (Claude Code, Codex): do nothing; the next request brings
   a fresh reading.
2. If the last reading was fed by you: feed a new one.

With nothing to feed at all, record exactly that: `strain-level.sh UNMEASURED`.

## When a record command is refused

Read the first line of the error, then follow the matching steps.

**"no session key"**
1. Copy the record command from the LATEST strain tick (it carries
   `STRAIN_SESSION=<this session>`) and run that.
2. If there is no tick yet, pick your session from the list the error prints — the one
   your host names, or the one in your folder — and run the ready command under it.
3. Never copy a key from an older session.

**"the session sources disagree"**
1. Use the key your host names (the error lists it).
2. Run the command again with that key.

**"could not write state" — a permission problem** (sandboxed hosts, Codex for one)
1. Raise your host's own permission prompt to ask the user (if your host has no prompt,
   ask in chat): allow writing to strain's folder (the error names it) — say it is only
   strain's folder.
2. Wait for the user's answer.
3. If they allow it: run the same command again with that permission.
4. Check it worked: `strain-sign.sh --receipt` says "this shell can write".
5. If they refuse: say plainly that strain cannot record for this session; the hooks keep
   counting on their own.

Not allowed: approving the permission yourself, widening it beyond strain's folder, and
moving the folder for your shell alone.
Set `STRAIN_STATE_DIR` only if the host's hooks get it too — set in your shell alone,
your records and the hooks' counts end up in two different folders.

## At the wrap

1. Write your handoff (strain does not; see *Throughline* below).
2. Stamp the wrap: `strain-wrap.sh --label "<what was handed off>"` (add `--with-debt` if
   you leave known loose ends).
3. If you keep working after the stamp, run it again at the next handoff — the tick says
   "N calls since the wrap" until you do.

A stamp means **this session wrapped / handed off** — not "the work is right" (that is
your project's own check). It resets nothing: a new session starts at zero anyway.

## Before saying strain is missing

Look before saying strain is missing. Do these before you tell anyone strain is not
installed or not running:
1. Check for strain's state folder (`~/.local/state/strain`, or `STRAIN_STATE_DIR`) and a
   file for this session under `sessions/`.
2. Run `strain-sign.sh --receipt`. If it prints a receipt, strain is here.
3. Check your host's own plugin listing — the one YOUR host has (for example
   `claude plugin list` on Claude Code, or Codex's plugin folder). A command from another
   host proves nothing.
4. Remember a tick fires only every N tool calls; no tick yet is not proof.

## What to count

Two inputs, and they are not equally strong.

### Context occupancy — measured, when the host allows it

Some hosts keep a per-session log carrying token usage (Claude Code and Codex do; strain
reads both). Where that exists, the context reading is a real number, not an impression:

- **current** = the input side of the most recent request, in that host's own terms —
  cached tokens are still context the model is carrying (on Claude the cached parts are
  separate fields that add up; on Codex they are already inside the input count)
- **baseline** = the same sum on the first turn: what the boot alone cost before any work
  happened. System prompt, tool schemas, project instructions, skills. It is the floor the
  session can never get back under, and it is usually larger than people expect.

**Never quote a context number you did not measure.**

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

Soft signals are colour, not ladder. Hard signals are the same on any window size, but
only the ones that **escaped** move the tier. A repeat of the same class earns a *pattern
note* — say it to the user.

## The tiers

Two lines are scored separately and the higher one wins. The tick computes and PROPOSES
the tier; you confirm it or change it with what the counters cannot see.

- **Line A — capacity:** fill against caps **50 / 60 / 70 / 74%** → Mid / High / Warning /
  Danger (Danger is derived = throttle onset 80 − wrap budget 6, so a mandated wrap can
  finish before the model degrades). It **abstains** when the number cannot be trusted.
- **Line B — conduct:** escaped signals — 0–2 move nothing · 3 → Mid · 4 → High · 5+ →
  Warning. A burst usually shares one root cause (a capability gap), not exhaustion.
- **Combination:** fill already at Warning/Danger **and** 3+ escaped → Danger.
- **UNMEASURED:** Line A abstains and Line B says nothing. Never Healthy; see *When strain
  cannot measure*.

| Tier | Fill cap | Also reached by | What it means |
|---|---|---|---|
| **Healthy** | under 50% | — | carry on |
| **Mid** | 50–60% | 3 escaped signals | fine, but the end is in sight |
| **High** | 60–70% | 4 escaped signals | wrap after the current thread |
| **Warning** | 70–74% | 5+ escaped signals | wrap now; new work should start fresh |
| **Danger** | 74%+ | Warning-level fill **plus** 3+ escaped | stop and hand off |

**Raise the tier only on evidence, never on momentum.** Ticks piling up is not evidence; a
previous high reading is not evidence. Fill crossing a cap and fresh escaped signals are
the only ladders.

## How to report it

Match the shape to the tier, so the user can act without asking follow-ups.

- **Healthy** — one line, or nothing at all if the user did not ask.
- **Mid / High** — the counts, and a suggestion to wrap soon:
  > 🟡 High — context 136k/200k (68%), of which 70k was the boot. 1 main goal, 3 side
  > tasks. Suggest finishing the current thread and wrapping.
- **Warning / Danger** — the counts, **which hard signals fired and whether they
  escaped**, why it matters, and a recommendation to wrap now:
  > 🔴 Warning — context 158k/200k (79%), 2 compactions, 1 escaped regression. The fix
  > shipped broken and the window is nearly full. Recommend wrapping and starting
  > fresh; I will write the handoff first.

## Signing from a shell that cannot reach strain's folder

(A sandboxed or remote session, after the user refused or the host has no permission
prompt.)
1. Give the user ONE copy-paste line for a plain terminal on their machine, everything
   filled in: `STRAIN_SESSION=<this session> bash <plugin>/scripts/strain-sign.sh --agent
   <your name>` (plus `--ledger <path>` if the project keeps one). See "Signing from a bare
   terminal" in the README.
2. Put the command alone in its own code block; the steps go outside it.
3. Until the user pastes back the `Owner: … — signed` line, report yourself as
   measured-but-unsigned, never as signed.

Strain says *when* to hand off. It does not do the handing off. Its companion for that is
**[Throughline](../../../handoff-skill/throughline)**, whose task track is also the
cleanest source for the behavioural counts above.

## Honest limits

- **Hooks are per-host.** Where they exist, the check fires whether or not you remember.
  Where they do not: run the check yourself every ~10 tool calls or at each milestone,
  and say that it is manual.
- **Context auto-reading knows two hosts' logs** (Claude Code's and Codex's). On other
  hosts, feed the number yourself (*When strain cannot measure*), and record the window
  once for your product and model: `strain-calibrate.sh --product <p> --model <m>
  --window <n> --basis nominal|runtime --source "<where>"`. A fed reading is labelled
  agent-fed — never report it as something strain measured itself.
- **Record commands write outside the project** (`~/.local/state/strain`). A sandboxed host
  may refuse them — see *When a record command is refused*. The hooks are not affected.
- **Thresholds are guesses** until you retune them.
- **The soft signals are judgement calls.** A tier that is always Healthy is not a healthy
  session, it is a broken check.
