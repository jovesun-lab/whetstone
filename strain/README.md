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
3. When it says wrap, wrap — and mark it:
   ```
   bash "$CLAUDE_PLUGIN_ROOT/scripts/strain-wrap.sh" --label "what was finished"
   ```
   That is the only thing that resets the counters.

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

Since v0.3 the tier is a **two-line model** — capacity and conduct scored separately,
then max-joined, never multiplied:

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
- Compactions floor as before (1 → High, ≥2 → Warning, plus a recovery directive).

The final tier is the **max** of the three — no cross-weighting. Errors inside the
throttle zone (≥80%) are *annotated* as likely capacity-induced, never auto-escalated:
the two lines answer different questions, and multiplying them manufactures verdicts
neither line stated. The proposal is still allowed to DECAY when the load does, and
nothing escalates on tick count — the old "continuing past a Warning ⇒ Danger" rule
pinned Danger at a measured 33% fill, three sessions running, and stays deleted.

A compaction is not a fresh start. It is the clearest evidence available that the session
has run long, so it raises the floor and does not come back down.

## Commands

All of these live in the plugin folder, so the agent runs them as
`bash "$CLAUDE_PLUGIN_ROOT/scripts/<name>"`:

| Command | What it does |
|---|---|
| `strain-level.sh <tier>` | record the tier for this session |
| `strain-level.sh --get` | print the current tier |
| `strain-level.sh --show` | the whole state, including the context reading and which file it came from |
| `strain-signal.sh <kind> --caught\|--escaped` | record a hard signal; escaped ones floor the tier, caught ones feed the pattern note |
| `strain-signal.sh --list` | print this session's signal ledger |
| `strain-wrap.sh --label "…"` | mark the work wrapped; resets the counters once, at the next session start |
| `strain-wrap.sh --status` | show the current wrap marker |

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
3. **The wrap budget.** `6` is an unmeasured estimate (5–8% bracket). Measure your own:
   note the fill % right before and right after one real session wrap, and pin the
   difference. Until you do, treat the derived Danger cap as approximate.

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

63 checks, host-independent: counting, per-session isolation, the tick firing on schedule
and only then, the writer and reader agreeing on one location, wrap-marker reset semantics
(including that one wrap buys exactly one reset), compaction escalation, all three context
modes, model observation (logged on change, a mid-session switch gets its own row, no
empty rows), the denominator following the observed model, fill-band math on two
capacities, escaped-vs-caught signal weighting, the boot calibration line, and malformed
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
