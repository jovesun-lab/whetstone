# strain

✅ Open source (MIT)  ·  ✅ Works as a plain prompt in any agent  ·  ✅ Fires on its own where hooks exist

**Tells you when a session has gone bad — before its answers do.**

A long agent session degrades quietly. The context window fills up, the same bug comes
back a third time, an answer from an hour ago turns out to be wrong, and the work carries
on regardless, because nothing in the loop is watching the loop. strain watches: it counts
how loaded *this one conversation* has become and makes the agent report it, on a schedule
it cannot quietly skip.

The failure it exists to prevent is not a crash. It is **silence** — an agent that never
mentions the session has gone bad, and lets you find out from the output.

## Quick start

1. **Install** the plugin.
2. Work as usual. Every 10 tool calls the agent is asked to run the check and report a
   tier — 🟢 Healthy, 🟡 Mid / High, 🔴 Warning / Danger.
3. When it says wrap, wrap — and stamp it:
   ```
   bash <strain>/scripts/strain-wrap.sh --label "what was handed off"
   ```
   `<strain>` is the plugin folder; every tick prints the commands with the real path
   and this session's key already filled in (a record without the key is refused — see
   *Which session a record lands in*). A stamp records that the session wrapped; it
   resets nothing — a new session starts at zero anyway.

Nothing to configure. Nothing leaves your machine.

## What a readout looks like

```
🟡 High — context 136k/200k (68%), of which 70k was the boot itself.
1 main goal, 3 side tasks. Suggest finishing the current thread and wrapping.
```

That number on the first line is measured, not estimated — see below.

## Two modes, and it always says which

| Mode | When | What you get |
|---|---|---|
| **measured** | the host publishes a per-session transcript with token usage (Claude Code does) | real context numbers: how full the window is, and what the boot alone cost before any work happened |
| **estimated** | a transcript exists but carries no token usage | fill estimated from transcript bytes (~4 bytes/token), labelled ESTIMATED in every readout |
| **inferred** | no transcript at all | behaviour counting: tool calls, compactions, and what the task list shows |

Since 0.8.0 the engine asks **host adapters** first — one small file per host that keeps
its log in its own shape. Codex is the first (see *Codex* below); a host with an adapter
is read in `measured` mode from its own numbers.

`inferred` is not a failure — it is the original design and it works. What *would* be a
failure is printing a confident number nobody measured, so the mode travels with every
readout.

The **baseline** is worth its own mention: the tokens your session spent before doing
anything at all — system prompt, tool schemas, project instructions, skills. It is the
floor the session can never get back under, and on a loaded setup it is routinely a third
of the window.

Measured mode also observes **which model is running** — from the same transcript line
that carries the usage, so a mid-session model switch is seen too. Two things depend on
it: the model log (one appended row per observed change, never per tick), and the
**denominator**. Every readout names where its window came from (0.8.0), in this order of
trust: `env override` (`STRAIN_CONTEXT_LIMIT`) · `host-reported` (the host states its
window live — Codex does) · `calibrated: <product> · <model>` (a record you made, see
below) · `model hint` (inferred from the model id: `fable`, `opus-5` and `[1m]` variants →
1M, and so on) · `default` (200k). So the bracket reads, for example,
`window 1M (model hint)` or `window 258k (host-reported · Codex)`. This matters more than it sounds: a hardcoded
200k denominator once reported a 1M-window session at 69% when it was actually 14% full —
a wrong number delivered with full confidence, which is exactly what this tool exists not
to do.

## When strain cannot read your host (0.6.0, reworked in 0.8.0)

The first cross-model field report made a gap plain: a session on a non-Claude host had
its numbers on screen — the host reported a 258,400-token runtime window and per-turn
usage — and strain still ran blind, because the transcript reader knew one host's shape.
"The host exposes nothing" and "the host exposes something strain cannot parse" used to
land in the same coarse mode. Two front doors fix that, and an adapter (0.8.0) closes it
for good for hosts that keep a durable log.

**When nothing is measured, strain says which kind of nothing (0.8.0).** The tick never
says Healthy for a reading it does not have; it proposes `UNMEASURED` and names one of
three kinds, each with its own next step:

| Kind | What happened | Next step the tick gives |
|---|---|---|
| `no source` | no log strain can read on this host | look where hosts keep usage (a session log, a status or usage command, a usage API, the settings pane), then end with ONE record: a feed, or `--no-source --checked "<places looked>"`. The tick repeats until one exists, so skipping it is visible. |
| `unusable` | a source was read and gave no usable number (no usage lines, a window of 0, a log that names another session, or a fill at or past 100%) | read the host's own number and feed it with its provenance; a fill past 100% is strain's arithmetic going wrong, so the tick says the used count is a **lower bound**, lists what to check (model · effective window · double counting · compaction boundary) and offers a hand-sent bug report |
| `stale` | a compaction or a model switch happened after the last reading | a host that measures itself re-measures at its next request (nothing to do); a fed number needs a new feed |

`UNMEASURED` can also be **recorded** — `strain-level.sh UNMEASURED` — so an agent with no
number to give never has to invent a tier.

**Denominator** — record a window once, for one product and one model, sourced and typed:

```
bash <strain>/scripts/strain-calibrate.sh --product "Example Host" --model ex-model-1 \
     --window 258400 --basis runtime --source "host runtime log"
```

A record belongs to ONE `<product> · <model>` (0.8.0). Until 0.7.0 there was one record per
machine and every session on the machine divided by it: one host's 258,400-token window
became the window of every session on another host next to it, and a session 19% full was
told to wrap now. Now the model must match always; on a host strain recognises (Claude
Code, Cowork, cloud Cowork, Codex) the product must match too; on a host it does not
recognise, the model alone picks — among records made for unrecognised hosts, and only
when exactly one fits. A window the host reports live beats any record. The old
`calibration.json` is no longer written; strain reads it as one more record, and one that
names no model is never applied (the tick says so once). `strain-calibrate.sh --show`
lists every record and says which one rules this session, and why.

`--basis` is required and keeps the record honest: `nominal` is the published capacity,
`runtime` is what the host reports live (often smaller — e.g. a post-compaction window).
A runtime reading mistaken for the model's nominal size corrupts every percentage after
it. A record expires (default 30 days) and a stale one falls back loudly — it never
silently keeps ruling.

**Numerator** — when the host shows its usage, hand it over at recording time:

```
bash <strain>/scripts/strain-level.sh Mid --ctx-used 65749 --ctx-source "host status command" \
     --ctx-provenance host-reported
```

The readout then says `fill 25.4% — agent-fed: 65,749 of 258,400 tokens (window: …)`.
`agent-fed` is its own mode, printed every time: a fed number is honest input with a
named source — never dressed up as a measurement strain made itself. `--ctx-provenance`
says whether you read it from the host (`host-reported`) or estimated it yourself
(`agent-estimated`).

**A host whose log strain cannot read yet?** If the number lives in a durable log, write
an **adapter proposal** — where the log is, which fields carry the usage, one redacted
sample line — with `strain-report.sh --note "…"`, and send it to the maintainers. Do not
patch the installed plugin: the next update overwrites a local patch, and it helps
nobody else.

**No hooks on your host?** Then ticks will not fire on their own. Adopt the manual
cadence the skill describes: run the strain check by hand every ~10 tool calls or at
every milestone, and feed the reading if your host shows one. Name your session once
with `--session <name>` on every record command — strain does not guess one for you.
An instrument nobody polls is an instrument that stays quiet — on hook-less hosts the
polling is yours.

## Codex (0.8.0)

Codex writes one log per session — `~/.codex/sessions/YYYY/MM/DD/rollout-…-<session id>.jsonl`
(or under `$CODEX_HOME`) — and records, on every request, how many tokens went in and how
big the window is. strain reads that receipt directly: the newest
`last_token_usage.input_tokens` (the cached part is already inside it, so nothing is
counted twice) over the host-reported `model_context_window`. Nothing to configure, no
calibration record needed. Details:

- The log is found by the hook's own session id and must name that id on its first line —
  a log that belongs to another session is never read as this one.
- A compaction or a model switch after the newest receipt makes the reading `stale` until
  the next request writes a new one (the zero receipt Codex writes right after a
  compaction is skipped). There is no clock: an old receipt is not stale by age.
- Codex writes the receipt after the tool output, so a hook usually reads the previous
  request — one request behind, the same lag as the Claude reader.
- The agent's shell carries `CODEX_THREAD_ID`, which is the same id; record commands use
  it as their session key.

## One session, one reading

Strain measures **a single conversation**, keyed by its session id. Two agents on the same
project in two windows are two sessions, and their counts never add up:

```
~/.local/state/strain/sessions/<session-id>.json
```

This is not a detail. An earlier internal build kept one global state file with a single
session slot, so a second session simply overwrote the first and both counters became
meaningless. The session id is also how the host names the transcript — so *whose strain
is this* and *can I read this session's real context size* are the same question.

## Which session a record lands in (0.8.0)

The hooks always know their session — the host puts the id in every payload. The agent's
shell does not, and until 0.7.0 a record command without a key fell back to "the session
last seen in this folder", then "the most recent session on the machine". With two agents
working at once, a tier, an escaped error or a wrap could land in whichever session fired
a hook last, while the right session's number never moved.

Now a record (`strain-level.sh`, `strain-signal.sh`, `strain-sign.sh`, `strain-wrap.sh`,
`strain-report.sh`) needs a key, from one of these, in order of trust:

1. `--session <id>`, typed.
2. `STRAIN_SESSION` — every tick prints it into the ready-made command; on Claude Code the
   SessionStart hook also exports it into the agent's shell (through the host's
   `CLAUDE_ENV_FILE` hand-over), so plain commands land in the right session.
3. The host's own shell variable — Codex sets `CODEX_THREAD_ID`.

Claude Code shells also carry `CLAUDE_CODE_SESSION_ID`; it is not documented, so strain
uses it only as a cross-check: when sources disagree, the record is refused and both are
named. With no key at all, the record is **refused** (exit 2) with up to three candidate
sessions and a ready command for each — it never picks one. Reads (`--get`, `--show`,
`--list`, `--status`, `--receipt`) may still guess, and say "guessed" when they do.

**What you see, and what your agent sees.** The first sign of a session tells you one
plain sentence, and `strain-sign.sh --receipt` repeats it any time:

```
Strain is on. This conversation is 10% full — strain will tell you when it's time to wrap up and start fresh.
```

The agent gets the details on the side — host, session, where the reading comes from,
where the window came from, whether the hooks are saving, whether its own shell can write
(0.8.1; 0.8.0 showed users the agent's version, which was correct and unreadable):

```
Strain receipt — host Claude Code · session 0a8e0001 · reading Claude transcript at 09-30 18:15 · measured · window 1M (model hint) · hooks saving (last 09-30 18:15) · this shell can write · no ledger
```

On Claude Code the hook shows you the sentence itself, once per session (the host's
`systemMessage`). In the desktop app it sits folded into that step's title as
**"received a notice"** — open the step to read it. Two other plain sentences use the
same channel, because they must not depend on the agent passing them on: when strain
can't tell how full the conversation is, and when it can't save on this computer.
`STRAIN_USER_MESSAGES=off` turns all three off. On other hosts, the skill asks the agent
to relay the sentence as it is.

## Where strain writes

Everything strain keeps is in one folder **outside your project**:
`~/.local/state/strain` (or `$XDG_STATE_HOME/strain`, or wherever `STRAIN_STATE_DIR`
points). Inside it, every file is either one session's own (`sessions/<id>.json`, a draft
under `reports/`) or keyed per entry — by session (`index.json`, `model-log.jsonl`), by
agent (`ledgers.json`) or by product · model (`models.json`). A selftest check walks a full
scenario and fails if a file appears that no reader could attribute.

- **Sandboxed hosts** (Codex, for one) may block writes outside the project and ask for
  permission when a record command runs. The hooks are not affected — the host runs them
  and they keep saving; only the agent's own record commands are refused. Ask the user to
  allow writing to strain's folder rather than escalating on your own. Moving the folder
  with `STRAIN_STATE_DIR` works only if the host's hooks get it too: set in the agent's
  shell alone, the records land in one folder and the hooks keep reading another.
- **After updating the plugin, restart the host** before you keep working. Some hosts
  delete the old version's files on update while the running session still points at
  them, and every tool call then reports a failing hook until the restart.
- **A save that fails is said**, never swallowed: the tick says so once (and on Claude
  Code shows it to the user), the boot says so, and the next saved reading notes the gap.
- The project **ledger** (`Log.strain`, when you sign with one) is the only file strain
  writes inside a project, and only where you point it.

## Cloud Cowork (0.7.0)

- **Works:** during a conversation, strain watches how full the context is and tells your
  agent when it's time to wrap up — same as on your own computer.
- **Not yet:** strain can't carry anything from one cloud conversation to the next by
  itself. Each new conversation starts fresh (strain's files live with the cloud task, and
  the task cannot write a ledger into a connected folder).

**Tip — let your agent carry it over.** Put a handoff file (for example `HANDOFF.md`) in a
folder connected to the task, and add these two rules to your agent's instructions:

1. "When you wrap up, run `strain-level.sh --show` and write one line into HANDOFF.md: the
   date, tool calls, compactions, errors that reached me, and the final strain level."
2. "At the start of every conversation, read that line in HANDOFF.md and tell me how the
   last session went."

Keep the desktop app open while the agent writes the file, and check that it arrived — we
have seen a cloud write land an older copy.

- **Several agents, in the cloud and on your computer, sharing one history:** not supported
  yet; planned for a later version. Need it sooner, or something else? Open an
  [issue](https://github.com/jovesun-lab/whetstone/issues).

*This release has not been tried in a cloud task yet. The cloud behaviour above comes from
testing an earlier build, and the tip has not been tested end to end.*

## Signed wraps and the project ledger

The path cannot tell agents apart (two windows on one project look identical to the
hooks), so identity is **declared**, not derived:

```
bash <strain>/scripts/strain-sign.sh --agent ana --ledger ./Log.strain
```

Signing names this session's agent. With a ledger, the **first** sign of a session also
prints a **previous-session report** (0.7.0): the newest earlier session of the same
agent in that book — its tool calls, compactions, errors escaped and caught, whether it
wrapped (and when), and whether it kept working after the wrap. It only reads; nothing
is carried over.

**Until 0.6.0 a wrap was a shared marker that reset counters** at the next session start
— which reset another live session of the same signature, and reset a session that kept
working in the same full context after its own wrap. Since 0.7.0 a wrap resets nothing:
it records `wrappedAt` / `wrapTick` in the session's own state and books one `wrap` row.
An old `wrap-marker.json` in your state dir is ignored and can be deleted.

The `--ledger` part is optional and adds a durable account book: an append-only JSONL
file (suggest `Log.strain` at the project root, gitignored) that receives one
`boot-sign` row when a session signs and one `wrap` row (verdict, label, tier, tick)
when it wraps. It records the project's chain of sessions — who worked, when, wrapped
how — and it never inherits counters across sessions: one session, one reading,
unchanged. Appends are flock-guarded, so concurrent signers cannot tear a row.
The path needs saying only **once** (0.5.1): it is remembered per agent
(`ledgers.json` in the state dir), so later sessions sign with `--agent` alone.

### Signing from a bare terminal

The sign does not have to come from inside the agent's own shell. Some sessions
cannot reach the state home from where they run — a sandboxed agent, a remote
shell — and there the honest move is delivery by hand: the agent hands over a
filled-in command, and the person at the machine runs it in any plain terminal:

```
STRAIN_SESSION=<session-id> bash <plugin>/scripts/strain-sign.sh --agent ana --ledger /path/to/project/Log.strain
```

`<plugin>` is wherever the installed copy lives (for Claude Code,
`~/.claude/plugins/cache/whetstone/strain/<version>`). The key is required
(0.8.0): without it the sign is refused and lists the candidate sessions with a
ready command for each — it no longer picks "the session this folder saw last".
The stdout lines — `Strain · Owner: ana — signed (…)` and the plain `Strain is on …`
sentence — are the proof: paste them back to the agent and the session is signed.
Until then the session simply stays unsigned: measured, but part of no chain.

## What it counts

**Context occupancy**, when measurable. Plus behaviour, always:

- **soft** — distinct subjects touched, a side task that balloons past the main one, a
  problem that came back, open critical tasks, a second goal appearing
- **hard** — a factual error, a regression, a revert of your own work, **a context
  compaction** — recorded with `strain-signal.sh <kind> --caught|--escaped`

Hard signals are absolute (capacity never dilutes accountability), but only the ones
that **escaped** — reached the user or shipped work — move the tier. An error caught
and fixed before delivery is a working immune system, not exhaustion: it is recorded,
and a repeat of the same class earns a pattern note, without driving the tier.

Since v0.3 the tier is a **two-line model** — capacity and conduct scored separately;
since v0.4 their **combination** can also raise the alarm (see below):

- **Line A — capacity**: fill vs a cap ladder (defaults **50/60/70%** → Mid/High/Warning,
  and **Danger is derived** = throttle onset − wrap budget, default 80 − 6 = **74%** —
  so a mandated wrap can finish *before* the model enters its degraded zone). Line A
  **abstains loudly** when the number can't be trusted (no measurement, or an impossible
  percentage) — a missing measurement is never "Healthy (fill 0%)". A misconfigured
  ladder (e.g. a raised wrap budget sliding Danger below Warning) is shouted and the
  built-in defaults stay in force — over-report beats under.
- **Line B — conduct**: the escaped-signal ladder (0–2 move nothing · 3 → Mid · 4 →
  High · ≥5 → Warning). A burst of escapes usually shares one root cause — a capability
  gap, not exhaustion — which is why small counts don't tier.
- Compactions are **stated, never a floor** (0.7.0): every tick after one says
  "compaction #N", and a one-time recovery directive asks the agent to re-read its goal.
- **UNMEASURED** (0.7.0): when Line A abstains and Line B says nothing, the proposal is
  `UNMEASURED` — never "Healthy" — with the command to feed the host's own reading.

The final tier is the **max** of the two lines, plus one **combination alarm** (v0.4): when
Line A is already at Warning/Danger **and** the escaped count has reached 3, the
composite tops the proposal out at **Danger**, with a loud basis line naming both
conditions. It is not a weight or a multiplier — it names the one compound state
(*running on a full window AND repeatedly shipping errors*) that is more dangerous
than either line says alone, and it fires only when BOTH preconditions hold: high fill
with ≤2 escapes stays a capacity story, and a burst of escapes on a half-empty window
stays a conduct story, each on its own ladder. Errors inside the throttle zone (≥80%)
are still *annotated* as likely capacity-induced, never auto-escalated: the two lines
answer different questions. The proposal is still allowed to DECAY when the load does, and
nothing escalates on tick count — the old "continuing past a Warning ⇒ Danger" rule
pinned Danger at a measured 33% fill, three sessions running, and stays deleted.

A compaction cuts the context; it is not a load reading. Until 0.6.0 it floored the tier
(1 → High, 2+ → Warning), which read a session that had just been compacted to a small
context as heavily loaded. The fill after it is the measure.

## Commands

All of these live in the plugin folder: `bash <strain>/scripts/<name>`. **The tick prints
each one ready to run** — this session's key, the state folder and the plugin's absolute
path filled in — so the agent copies it from there. (Until 0.6.0 the tick printed
`"$CLAUDE_PLUGIN_ROOT/scripts/…"`; that variable exists only inside the hook process, so
the command failed in the agent's own shell.)

| Command | What it does |
|---|---|
| `strain-level.sh <tier>` | record the tier for this session (`UNMEASURED` is recordable too) |
| `strain-level.sh <tier> --ctx-used <n> --ctx-source "<where>" [--ctx-provenance host-reported\|agent-estimated]` | record a tier AND feed the host's own usage reading (agent-fed fill, source named) |
| `strain-level.sh UNMEASURED --no-source --checked "<places>"` | record that this host shows no usage anywhere you looked — ends the tick's "no source" checklist |
| `strain-calibrate.sh --product <p> --model <m> --window <n> --basis nominal\|runtime --source "<where>"` | record the window of one product · model — sourced, typed, expiring |
| `strain-calibrate.sh --show` | list every record, whether each is valid, and which one rules this session |
| `strain-report.sh [--note "…"] [--title "…"]` | draft a bug report (or an adapter proposal) about strain for the user to send by hand; nothing is sent |
| `strain-level.sh --get` | print the current tier |
| `strain-level.sh --show` | the whole state, including the context reading and which file it came from |
| `strain-signal.sh <kind> --caught\|--escaped` | record a hard signal; escaped ones floor the tier, caught ones feed the pattern note |
| `strain-signal.sh --list` | print this session's signal ledger |
| `strain-wrap.sh --label "…" [--with-debt]` | stamp this session wrapped / handed off; resets nothing; books a `wrap` row when signed with a ledger |
| `strain-wrap.sh --status` | show this session's wrap state |
| `strain-sign.sh --agent <name> [--ledger <path>]` | declare who works this session; with a ledger, book boot-sign/wrap rows and report the previous session of the same agent; the first sign prints the receipt |
| `strain-sign.sh --receipt` | repeat the user's sentence (stdout) and the agent's details (stderr) |

Every record command needs this session's key (see *Which session a record lands in*);
the printed commands carry it.

`strain-level.sh` prints which session it resolved and where it wrote. That is deliberate:
in an earlier build the writer defaulted to a different file from the one the hooks read,
so recording a tier changed nothing anyone could see — and from the outside that looks
exactly like a check that is working fine and always says Healthy.

## Settings

| Variable | Meaning | Default |
|---|---|---|
| `STRAIN_N` | tool calls between ticks | `10` |
| `STRAIN_STATE_DIR` | where state lives | `~/.local/state/strain` (or `$XDG_STATE_HOME/strain`) |
| `STRAIN_CONTEXT_LIMIT` | context window size, tokens; overrides every other source | host-reported > calibrated record > model hint > 200k |
| `STRAIN_CAP_MID` / `_HIGH` / `_WARN` | fill % that enters Mid / High / Warning | `50` / `60` / `70` |
| `STRAIN_THROTTLE_ONSET` | fill % where your platform's model visibly degrades | `80` |
| `STRAIN_WRAP_BUDGET` | context cost of a full session wrap, in fill % | `6` |
| *(derived)* Danger cap | `THROTTLE_ONSET − WRAP_BUDGET` — never set directly | `74` |
| `STRAIN_SUBSTRATE` | name the shell explicitly for the calibration line | detected from the transcript path |
| `STRAIN_DRIFT_GLANCE` | `off` drops the tick's goal-drift glance (a non-flooring ask to check your task track for a side task outgrowing the marked MAIN goal — pairs with throughline's convention; drift is a note, never a tier input) | `on` |
| `STRAIN_NO_MODEL_LOG` | stop recording which model ran which session | unset |
| `STRAIN_SESSION` | this session's key for record commands | printed in every tick; exported into the shell on Claude Code; records refuse without a key |
| `STRAIN_USER_MESSAGES` | `off` stops strain showing its plain sentences to the user directly (Claude Code) | `on` |
| `CODEX_HOME` | where Codex keeps its logs, if not `~/.codex` | `~/.codex` |

**Three numbers are yours to fill in — the defaults are honest starting points, not
facts about your setup:**

1. **The window** (`STRAIN_CONTEXT_LIMIT`, or better: verify the inferred one). The
   denominator of every percentage. Get it from your platform's official numbers, not
   from memory — a wrong window makes every reading confidently wrong.
2. **The throttle onset.** `80` is an observed value on one platform (2026-09): the
   point where replies get shorter, reasoning goes quiet, narration stops. Watch for
   where it happens on *yours*, set it, and re-verify when the platform or model
   changes — it is a physical constant of your environment, not a preference.
3. **The wrap budget.** `6` shipped as an estimate. The first field measurement on the
   design's home environment came in at **≈9.5%** (2026-09-11: wrap began at 49% fill,
   ended at 58.5%, including one failed-then-fixed check pass) — so treat `6` as
   optimistic. Measure your own: note the fill % right before and right after one real
   session wrap, and pin the difference. Until you do, treat the derived Danger cap as
   approximate — and err early, not late.

The Line-B ladder (3/4/≥5) is deliberately **not** an env knob — it is a team policy,
and a policy adjustable by environment fiddling can drift silently. Change it by
editing `signal_floor` in `scripts/_strain_common.py`, so the change is visible in
review. The readout always prints the caps it actually used.

**Design provenance.** Model architecture: designed and ruled by **Rae Sun
(arcgram.io)** — every load-bearing threshold (the throttle onset, the wrap budget,
the Line-B ladder) is a maintainer ruling, not a model output. Drafted and
adversarially hardened in multi-model AI collaboration; the acceptance rows in the
selftest are the design's contract.

## Good to know

- **Where hooks exist, the check fires whether or not the agent remembers.** Where they do
  not, strain is a discipline the agent keeps — real, but weaker. The skill says which
  situation it is in rather than implying enforcement it does not have.
- **A tier that never moves is a broken check, not a healthy session.** The counting is the
  work.
- **Nothing is sent anywhere.** State and the model log are local files you can open.
  `strain-report.sh` only writes a draft; sending it is yours to do, or not.
- **One honest limitation, partially closed:** whether a host *surfaces* the tick to the
  agent is a separate question from whether the hook ran. Loading is easy to verify (the
  state file appears and the count advances); surfacing is not. **Verified on Claude
  Code and on Cowork (2026-08-20, by observation — the injected text appeared in the
  agent's context and changed its behaviour): `hookSpecificOutput.additionalContext` on
  stdout IS surfaced; plain stderr/stdout prose is not.** On other hosts this remains
  unverified — if you never see a strain readout, check the channel first.

## Companion

Strain says *when* to hand off. It does not do the handing off — that is
**[Throughline](../handoff-skill/throughline)**, whose task track is also the cleanest
source for the behavioural counts here. The two are built to be used together, and neither
requires the other.

## Verify it works

```
python3 tools/selftest.py -v
```

191 checks, host-independent: counting, per-session isolation, the tick firing on schedule
and only then, the writer and reader agreeing on one location, wraps that reset nothing
(and touch no other session), compactions stated but never floored, all three context
modes plus a fed reading that is scored and kept, model observation (logged on change, a
mid-session switch gets its own row, no empty rows), the denominator following the observed
model, fill-band math on two capacities, escaped-vs-caught signal weighting, the boot line
printing the same caps as the tick, a printed record command that runs from a plain shell,
parallel ticks losing no count, the previous-session report, a calibration record ruling
only its own product · model, the Codex reader (receipts, compaction, model switch, a log
that names another session), records refusing without a session key, the three kinds of
UNMEASURED and their next steps, the plain sentence for the user and the agent's receipt, a failed save being said, every file strain
writes being one session's own or keyed per entry, and malformed payloads never failing a
tool call — plus the **negative fixture**: the v1 bug (Danger
pinned at a measured 33% fill by tick-count ratcheting) reproduced against the v1
scripts, where 19 of these checks fail, and passing here.

## Developing on it

`claude plugin install` **copies** the plugin into `~/.claude/plugins/cache/…` — editing
this folder changes nothing the hooks run until you refresh that copy:

```
claude plugin marketplace update whetstone
claude plugin uninstall --scope local strain@whetstone
claude plugin install strain@whetstone --scope local
```

Note the flag order on the uninstall: as of this writing, `claude plugin uninstall
<name> --scope local` (flag last) intermittently fails to resolve the scope, while
`--scope local` before the name works every time. Also: hooks are loaded at session
start, so an already-running session keeps executing the previous copy — a live check of
new hook behaviour needs a fresh session, or driving the installed scripts by hand with
a real payload on stdin.

## License

MIT — see [LICENSE](LICENSE).
