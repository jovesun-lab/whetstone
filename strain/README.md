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
   and this session's key already filled in. A stamp records that the session wrapped;
   it resets nothing — a new session starts at zero anyway.

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
**denominator**. The host does not publish the window size anywhere, so strain infers it
from the model id (`fable` and `[1m]` variants → 1M; anything else → 200k) and
`STRAIN_CONTEXT_LIMIT` overrides the guess. This matters more than it sounds: a hardcoded
200k denominator once reported a 1M-window session at 69% when it was actually 14% full —
a wrong number delivered with full confidence, which is exactly what this tool exists not
to do.

## When strain cannot read your host (0.6.0)

The first cross-model field report made a gap plain: a session on a non-Claude host had
its numbers on screen — the host reported a 258,400-token runtime window and per-turn
usage — and strain still ran in `inferred` mode, because the transcript reader knows one
host's shape. "The host exposes nothing" and "the host exposes something strain cannot
parse" used to land in the same coarse mode. The fix is a front door, not a pile of
per-host parsers:

**Denominator** — record your environment's window once, sourced and typed:

```
bash <strain>/scripts/strain-calibrate.sh --product "Codex CLI" \
     --window 258400 --basis runtime --source "host runtime log"
```

`--basis` is required and is the field that keeps the record honest: `nominal` is the
published capacity, `runtime` is what the host reports live (often smaller — e.g. a
post-compaction window). A runtime reading mistaken for the model's nominal size
corrupts every percentage after it. The record expires (default 30 days) and a stale
one falls back loudly — it never silently keeps ruling.

**Numerator** — when the host shows its usage, hand it over at recording time:

```
bash <strain>/scripts/strain-level.sh Mid --ctx-used 65749 --ctx-source "host runtime log"
```

The readout then says `fill 25.4% — agent-fed: 65,749 of 258,400 tokens (calibrated …)`.
`agent-fed` is its own mode, printed every time: a fed number is honest input with a
named source — it is never dressed up as a measurement strain made itself.

**No hooks on your host?** Then ticks will not fire on their own. Adopt the manual
cadence the skill describes: run the strain check by hand every ~10 tool calls or at
every milestone, and feed the reading if your host shows one. An instrument nobody
polls is an instrument that stays quiet — on hook-less hosts the polling is yours.

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
`~/.claude/plugins/cache/whetstone/strain/<version>`). Run from the project
folder you can drop `STRAIN_SESSION` — the sign picks the session the index
knows for that folder, newest first, and the stderr line names which basis it
used. The one stdout line — `Strain · Owner: ana — signed (…)` — is the
receipt: paste it back to the agent and the session is signed. Until then the
session simply stays unsigned: measured, but part of no chain.

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
| `strain-level.sh <tier>` | record the tier for this session |
| `strain-level.sh <tier> --ctx-used <n> --ctx-source "<where>"` | record a tier AND feed the host's own usage reading (agent-fed fill, source named) |
| `strain-calibrate.sh --product <p> --window <n> --basis nominal\|runtime --source "<where>"` | record this environment's window — sourced, typed, expiring; becomes the fill denominator |
| `strain-calibrate.sh --show` | print the calibration record and whether it is still valid |
| `strain-level.sh --get` | print the current tier |
| `strain-level.sh --show` | the whole state, including the context reading and which file it came from |
| `strain-signal.sh <kind> --caught\|--escaped` | record a hard signal; escaped ones floor the tier, caught ones feed the pattern note |
| `strain-signal.sh --list` | print this session's signal ledger |
| `strain-wrap.sh --label "…" [--with-debt]` | stamp this session wrapped / handed off; resets nothing; books a `wrap` row when signed with a ledger |
| `strain-wrap.sh --status` | show this session's wrap state |
| `strain-sign.sh --agent <name> [--ledger <path>]` | declare who works this session; with a ledger, book boot-sign/wrap rows and report the previous session of the same agent |

`strain-level.sh` prints which session it resolved and where it wrote. That is deliberate:
in an earlier build the writer defaulted to a different file from the one the hooks read,
so recording a tier changed nothing anyone could see — and from the outside that looks
exactly like a check that is working fine and always says Healthy.

## Settings

| Variable | Meaning | Default |
|---|---|---|
| `STRAIN_N` | tool calls between ticks | `10` |
| `STRAIN_STATE_DIR` | where state lives | `~/.local/state/strain` (or `$XDG_STATE_HOME/strain`) |
| `STRAIN_CONTEXT_LIMIT` | context window size, tokens; overrides the model-based guess | inferred from the observed model (`fable` / `[1m]` → 1M, else 200k) |
| `STRAIN_CAP_MID` / `_HIGH` / `_WARN` | fill % that enters Mid / High / Warning | `50` / `60` / `70` |
| `STRAIN_THROTTLE_ONSET` | fill % where your platform's model visibly degrades | `80` |
| `STRAIN_WRAP_BUDGET` | context cost of a full session wrap, in fill % | `6` |
| *(derived)* Danger cap | `THROTTLE_ONSET − WRAP_BUDGET` — never set directly | `74` |
| `STRAIN_SUBSTRATE` | name the shell explicitly for the calibration line | detected from the transcript path |
| `STRAIN_DRIFT_GLANCE` | `off` drops the tick's goal-drift glance (a non-flooring ask to check your task track for a side task outgrowing the marked MAIN goal — pairs with throughline's convention; drift is a note, never a tier input) | `on` |
| `STRAIN_NO_MODEL_LOG` | stop recording which model ran which session | unset |
| `STRAIN_SESSION` | name the session explicitly for CLI commands | resolved from the working directory |

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

128 checks, host-independent: counting, per-session isolation, the tick firing on schedule
and only then, the writer and reader agreeing on one location, wraps that reset nothing
(and touch no other session), compactions stated but never floored, all three context
modes plus a fed reading that is scored and kept, model observation (logged on change, a
mid-session switch gets its own row, no empty rows), the denominator following the observed
model, fill-band math on two capacities, escaped-vs-caught signal weighting, the boot line
printing the same caps as the tick, a printed record command that runs from a plain shell,
parallel ticks losing no count, the previous-session report, and malformed
payloads never failing a tool call — plus the **negative fixture**: the v1 bug (Danger
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
