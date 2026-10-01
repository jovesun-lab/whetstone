# Changelog

## 0.8.1 — 2026-09-30

**What the user reads is one plain sentence; the details are the agent's.** Found the same
night 0.8.0 shipped, by its first users on Claude Code and Codex.

- **The user gets one plain sentence.** 0.8.0 showed users the agent's receipt — host ·
  session · reading source · window and where it came from · state file · ledger — correct,
  and unreadable unless you are debugging strain. The user now reads one of three
  sentences: "Strain is on. This conversation is N% full — strain will tell you when it's
  time to wrap up and start fresh." · "Strain can't tell how full this conversation is
  right now, so it's only counting the agent's work and mistakes." · "Strain can't save on
  this computer, so it isn't keeping track of this conversation. Your agent has the
  details." The first sign prints the sentence on stdout (relay it as is) and the details
  on stderr; on Claude Code the hook shows the same sentences itself.
- **"Can this shell write" is not "is strain saving".** On a sandboxed host the hooks — run
  by the host — kept saving while the agent's own shell could not write, and the 0.8.0
  receipt reported that as "state write FAILED", which sent the agent chasing a fault that
  was not there. The agent's receipt now says both: "hooks saving (last HH:MM)" and
  "this shell can write" / "this shell cannot write here -- ask the user for permission".
  A record refused for permission says the same.
- **Corrected advice: one folder for hooks and records.** 0.8.0's README and skill said a
  sandboxed host could set `STRAIN_STATE_DIR` to a folder inside the project. Set in the
  agent's shell alone, that splits the data: the records land in the new folder and the
  hooks keep reading the old one. Now: ask the user to allow writing to strain's folder;
  move it only if the host's hooks get the same setting.
- **Docs.** In the Claude Code desktop app the sentence sits folded into the step's title
  as "received a notice". After updating the plugin, restart the host: some hosts delete
  the old version's files while the running session still points at them, and every tool
  call then reports a failing hook until the restart.

Selftest 186 → 191: 5 new checks, 5 rewritten (named "0.8.1 (was …)").


## 0.8.0 — 2026-09-30

**Codex as a known host, readings that say what they are, and records that never land in
the wrong place.** Five fixes, one new host, one behaviour change you may notice in
scripts, and five smaller improvements.

Fixes:
- **A calibration record rules only its own product and model.** Until now there was one
  `calibration.json` per machine, and any valid record became the window of EVERY session
  on that machine. One host recorded its 258,400-token window; from the next tool call on,
  every session of another host on the same machine divided by it — a session 19% full was
  told "Danger, wrap now". The record named its product and model; nothing compared them.
  Records now live in `models.json`, one entry per `<product> · <model>`. The model must
  match always; on a host strain recognises (Claude Code, Cowork, cloud Cowork, Codex) the
  product must match too; on an unrecognised host the model alone picks, among records made
  for unrecognised hosts, and only when exactly one fits. `strain-calibrate.sh` requires
  `--model`, writes under a lock, and `--show` lists every record and which one rules this
  session. The old `calibration.json` is never written again; it is read as one more
  record, and one that names no model is never applied (the tick says so once).
- **UNMEASURED can be recorded.** 0.7.0 proposed `UNMEASURED` but the recorder refused it,
  so an agent with no number to feed had to invent a tier or keep the default Healthy —
  the very value 0.7.0 banned. `strain-level.sh UNMEASURED` is accepted and carried.
- **The hooks description is current.** It still said a compaction was "carried as
  escalation", which 0.7.0 removed; it now says a compaction is stated, never a tier floor.
- **A save that fails is said.** The tick ignored the result of saving the state file, so
  an unwritable folder froze every count in silence. Now: one line on stderr, one notice
  to the agent (once, not on every call), the boot says it too, and the next saved
  reading notes the gap.
- **Signing takes the session lock.** 0.7.0 locked every read-modify-write of a session
  file except the sign's; a sign racing parallel tool calls could drop counts.

New host — **Codex** (strain now reads Codex's own log):
- The engine asks **host adapters** first — one small file per host (`_strain_host_codex.py`)
  answering where the session's log is and how it is shaped — then the Claude transcript
  reader, then the byte estimate. How a vendor's usage turns into "tokens in context" is a
  separate layer (`context_tokens`): Anthropic's cached parts are separate fields that add
  up; OpenAI's input count already includes the cache.
- Codex's reading = the newest `last_token_usage.input_tokens` over the host-reported
  `model_context_window`. The log must name this session on its first line; a compaction
  or a model switch after the newest receipt makes the reading stale until the next
  request; the zero receipt written right after a compaction is skipped; there is no clock
  (an old receipt is not stale by age). A window the host reports live beats any
  calibration record.
- This reader started from a local adapter written and field-tested by a Codex agent; it
  was rewritten here in the plugin's shape, with its own fixtures.

Behaviour change — **a record needs a session key.** A record command without one used to
fall back to "the session last seen in this folder", then "the most recent session on the
machine"; with two agents working at once, a tier, an escaped error or a wrap could land
in the wrong session. Now `strain-level.sh`, `strain-signal.sh`, `strain-sign.sh`,
`strain-wrap.sh` and `strain-report.sh` take the key from `--session`, `STRAIN_SESSION`
(printed in every tick) or the host's own shell variable (`CODEX_THREAD_ID`); on Claude
Code the SessionStart hook exports `STRAIN_SESSION` into the agent's shell through the
host's `CLAUDE_ENV_FILE` hand-over. `CLAUDE_CODE_SESSION_ID` is undocumented, so it is
used only as a cross-check. Sources that disagree → refused, both named. No key → refused
(exit 2) with up to three candidate sessions and a ready command for each. Reads (`--get`,
`--show`, `--list`, `--status`, `--receipt`) may still guess and say "guessed". **Scripts
that recorded without a key will now exit 2** — the error prints the fixed command.

Improvements:
- **The window says where it came from**: `window 258k (host-reported · Codex)` ·
  `window 1M (calibrated: Claude Code · <model>)` · `window 1M (model hint)` ·
  `window 200k (default)` · `(env override)`.
- **UNMEASURED says which kind, and the next step ends in a record.** `no source` → a
  host-neutral checklist of where hosts keep usage, ended by a feed or by
  `strain-level.sh UNMEASURED --no-source --checked "<places>"` (the tick repeats until one
  exists); `unusable` → the source and the reason, then a feed with provenance
  (`--ctx-provenance host-reported|agent-estimated`) — and a fill past 100% now says the
  used count is a lower bound, lists what to check and offers a hand-sent bug report;
  `stale` → a host that measures itself re-measures at its next request, a fed number
  needs a new feed.
- **A receipt.** The first sign prints one line — host · session · reading source and
  time · mode · window and its source · state file · ledger — and `strain-sign.sh
  --receipt` reprints it. On Claude Code the hook shows it to the user itself (once per
  session), together with a failed save and a reading that has just become UNMEASURED
  (`STRAIN_USER_MESSAGES=off` turns this off).
- **`strain-report.sh`** drafts a bug report (or an adapter proposal) about strain for the
  user to send by hand: the facts strain holds, never a path, the session id or
  conversation content. Nothing is sent.
- **The byte estimate counts only what follows the last compaction marker** (Claude's
  `compact_boundary`, Codex's `compacted`), scanned incrementally. A whole-file estimate
  after a compaction counted everything the compaction removed.
- **Docs**: README gains *Codex*, *Which session a record lands in* and *Where strain
  writes* (including what to do when a sandboxed host asks for permission); the skill
  gains the UNMEASURED procedures and "look before saying strain is missing".

Selftest: 128 → 186. 58 new checks (52 fail on 0.7.0; the rest guard behaviour that
already held, including a shared-file guard: a full scenario, then every file strain
wrote must be one session's own or keyed per entry — by session, agent, or product ·
model — so the next unkeyed shared file fails here). New fixtures use uuid-shaped session
ids. Rewritten, not deleted:
- "level resolves a session without being told" → a keyless write refuses and names the
  candidate (the behaviour change above).
- The 0.6.0 calibrate checks gain `--model`, and their product becomes an unrecognised
  host ("Example Host"): Codex is now recognised, and a lone record applies only to
  unrecognised hosts.
- The 0.7.0 printed-command check fills whatever placeholder the tier slot shows (it now
  offers `UNMEASURED`).
- Every child run strips the host's session variables, so a check never depends on the
  shell the selftest runs in.

## 0.7.0 — 2026-09-30

**A record command that runs, and the proposal says what it knows.** Seven fixes and
four behaviour changes, ported from the internal edition after they held up there.

Fixes:
- **The record command works.** The tick printed `bash "$CLAUDE_PLUGIN_ROOT/scripts/strain-level.sh"`;
  that variable exists only inside the hook process, so in the agent's own shell the
  command resolved to `/scripts/strain-level.sh` and failed — no Claude Code session could
  record a tier or an escaped error. The tick now prints the plugin's absolute path, this
  session's key (`STRAIN_SESSION=…`, never a "most recent" guess) and the state folder,
  for `strain-level.sh` and `strain-signal.sh`. README and SKILL lose the variable form.
- **UNMEASURED, never Healthy.** When nothing was measured and nothing else speaks, the
  proposal is `UNMEASURED`, with the command to feed the host's own reading. (A session on
  another host read 140% of a wrong window and the proposal said Healthy.)
- **A fed reading counts, and stays.** `strain-level.sh --ctx-used` stored the host's
  reading, but the tier ignored it and the next tool call overwrote it. It is now scored,
  kept until a real measurement or a newer feed, grows only by transcript bytes appended
  after it (never the whole file), and a compaction or model switch after it voids it.
- **Parallel tool calls lose no count.** Parallel hooks read the same count and both wrote
  count+1. Every read-modify-write of a session file now takes a lock (the save was
  already atomic).
- **One ruler per session.** The boot line printed the legacy bands (40/60/75/85) while
  every tick used the caps (50/60/70/74); the boot line now prints the tick's.
- **Wording.** The tick header names the interval ("host-fired every 10 tool calls"), not
  a count; the calibration bracket reads "strain calibration:" (it may well say
  uncalibrated).
- **A failed ledger append says why** (missing folder, no permission, lock error).

Behaviour changes:
- **A compaction is stated, never a tier floor.** It used to floor the tier (1 → High,
  2+ → Warning), reading a freshly compacted, small context as heavily loaded. The tick now
  says "compaction #N"; the one-time recovery directive stays.
- **A wrap resets nothing.** The wrap marker used to reset counters at the next session
  start — including another live session of the same signature, and a session still
  working in the same full context after its own wrap. `strain-wrap.sh` now records
  `wrappedAt` / `wrapTick` in this session's state and books a `wrap` row (verdict
  `WRAPPED` / `WRAPPED-WITH-DEBT`, with tick, compactions, escaped, caught, tier); the tick
  says when the session wrapped and how many calls ran since. `--status` shows this
  session's wrap. An old `wrap-marker.json` is ignored.
- **The previous-session report.** The first sign of a session with a ledger prints one
  plain line about the newest earlier session of the same agent. Read only.
- **The engine names two more shells:** `CLAUDE_CODE_ENTRYPOINT=remote_cowork` →
  `cowork-cloud` (a cloud task's transcript path looked like Claude Code), and the
  `…/claude-hostloop-plugins/<id>/projects/session/` transcript shape → `cowork`.
  Labels only; counting was already right. README: what does not survive a cloud session.

Selftest 104 → 128: 24 new checks (each failed on 0.6.0 except six guards), and 16
existing checks rewritten to the new behaviour — the wrap-reset and signed-marker checks
(0.5.0) now assert that a wrap resets nothing and touches no other session; the two
compaction-floor checks assert "stated, no floor"; v3-D / v3-I expect `UNMEASURED`; the
boot-line check expects the caps; the wrap output reads "wrapped", its ledger verdict
`WRAPPED`. SKILL's tier table, which still showed the pre-v3 bands, now shows the caps and
the escaped ladder the code has used since 0.4.

## 0.6.0 — 2026-09-22

**The feed door: strain on hosts it cannot parse.**

Prompted by the first cross-model field report (a Codex-family session): the host
showed a 258,400-token runtime window and per-turn usage on screen, and strain still
ran blind — the transcript reader knows one host's shape, and "exposes nothing" vs
"exposes something unparseable" landed in the same coarse mode.

- **`strain-calibrate.sh`** (new): record the environment's window — `--source`
  required (an unsourced capacity is a stale ruler waiting to happen), `--basis
  nominal|runtime` required (a runtime reading mistaken for nominal capacity corrupts
  every percentage after it), dated and expiring (default 30 days, falls back loudly).
  A valid record becomes the fill denominator for ticks and fed readings;
  `STRAIN_CONTEXT_LIMIT` still wins.
- **`strain-level.sh --ctx-used <n> --ctx-source "<where>"`**: feed the host's own
  usage at recording time. The readout and the stored state carry mode `agent-fed`
  and the named source — honest input, never dressed up as a measurement strain made.
- README: "When strain cannot read your host" section + manual cadence for hook-less
  hosts; SKILL: honest-limits amendment making the agent the adapter, with wording
  that forbids reporting fed numbers as measured.
- Selftest 95 → 104 (record write/read-back, unsourced/untyped refusals, denominator
  precedence env > calibration > hint, fed fill arithmetic, source-required refusal,
  feed+tier in one call).
- Riding this version to installed users: the 2026-09-20 docs commit (signing from a
  bare terminal — README section + the skill's hand-delivery discipline), which was
  pushed untagged and reaches plugin installs only with a version bump.

## docs — 2026-09-20

**Signing from a bare terminal (delivery by hand).**

- README: new "Signing from a bare terminal" section — a session that cannot
  reach the state home from its own shell (sandboxed or remote) gets signed by
  the person at the machine, from any plain terminal; the pasted
  `Owner: … — signed` line is the receipt.
- SKILL: the agent-side counterpart — when the sign fails for reachability,
  hand the user one filled-in copy-paste line instead of silently staying
  unsigned, and report measured-but-unsigned until the receipt arrives.
- Docs only; no behaviour change, no version bump.

## 0.5.1 — 2026-09-18

**The book is remembered, and the chat has two registers.**

- **Per-agent ledger registry** (`<state-dir>/ledgers.json`): signing with
  `--ledger` once is enough — a later session of the same agent signs with no
  path at all (resolution: explicit > session state > registry). The registry is
  a convenience pointer, never identity, never lends across agents, and refuses
  to rewrite itself when unreadable (same discipline as the index guard).
- **Two chat registers** for `strain-sign.sh` / `strain-wrap.sh`: stdout is
  USER-SURFACE — `Strain · Owner: <agent> — signed / wrap marked (…)`, plain
  words, no flags, no paths (selftest-asserted); stderr is AGENT-DIRECTED detail
  (paths, resolution basis) for the agent to relay in plain words. Rationale:
  not every user reads code; command lines belong to agents and docs, not chat.
- Selftest 95/95 (3 new: registry recall, user-surface purity, no cross-agent
  lending).

## 0.5.0 — 2026-09-18

**Signed wraps and the project ledger.** The wrap marker is one file per state dir,
and that bit the moment a second agent shared a machine: agent A marking its wrap
reset agent B's LIVE session at B's next session start — real strain, wiped by someone
else's finish line. The path cannot tell agents apart, so identity is declared:

- **`strain-sign.sh --agent <name>`** names this session's agent. A wrap marked by a
  signed session carries that signature (or pass `--agent` to `strain-wrap.sh`), and a
  signed marker resets **only sessions with the same signature** — others keep their
  counters and get one line, once per marker, saying whose it is (with a sign-to-join
  hint for unsigned sessions). An **unsigned marker behaves exactly as before**:
  signing is opt-in.
- **`--ledger <path>`** (optional) adds an append-only JSONL account book — suggest
  `Log.strain` at the project root, gitignored — receiving one `boot-sign` row at
  signing and one `wrap` row (verdict, label, tier, tick) at wrap. It records the
  project's chain of sessions without ever inheriting counters across them (one
  session, one reading, unchanged). Appends are flock-guarded; rows land whole under
  concurrent writers.
- **Index guard**: an existing but unreadable `index.json` now REFUSES the rewrite —
  a bad read fed straight into a save used to replace the whole registry with one
  fresh row. Same discipline as the append-only book: rows must not evaporate.
- Selftest 92/92 (12 new: sign/ledger rows, signature-scoped consume both ways, the
  once-per-marker line, unsigned-marker compatibility, 20-thread flock append, the
  index refusal).

## 0.4.1 — 2026-09-13

**The drift glance.** The tick now also asks the agent to glance whatever task track
it keeps (a list with one marked MAIN goal — throughline's convention, or your own):
a side task ballooning past the MAIN is goal drift, surfaced as a note in the reply.
Deliberately NON-FLOORING — drift is self-reported evidence and never a tier input —
and conditional: `STRAIN_DRIFT_GLANCE=off` drops the sentence. Selftest 80/80.

## 0.4.0 — 2026-09-13

**The combination alarm.** The two lines still score separately, but their combination
can now raise the alarm the way the model's owner originally designed it:

- **Composite**: fill already inside the Warning/Danger caps **and** escaped ≥ 3 →
  **Danger**, as a fourth `max()` term with a loud basis line naming both conditions.
  Not a weight, not a multiplier — it names the one compound state (*running on a
  full window and repeatedly shipping errors*) that is more dangerous than either
  line reports alone, and it needs BOTH preconditions: high fill with ≤2 escapes
  stays a capacity story; a burst of escapes on a half-empty window stays a conduct
  story. Review found 0.3.0's composite deletion had shipped without the owner's
  ratification; the cruder v2 composite (no capacity precondition) stays deleted.
- Throttle-zone errors still annotate, never auto-escalate; decay and the tick-count
  non-rule are unchanged.
- Selftest 78/78, including a loud-fire row and a precondition-unmet row.

## 0.3.0 — 2026-09-11

**The two-line tier model.** Capacity and conduct are now scored on separate lines and
max-joined — never multiplied:

- **Line A (capacity)**: fill vs a cap ladder (`50/60/70` → Mid/High/Warning), with
  **Danger derived** = `STRAIN_THROTTLE_ONSET − STRAIN_WRAP_BUDGET` (default 80 − 6 =
  74) so a mandated wrap completes *before* the model's degraded zone. Line A abstains
  loudly on untrustworthy numbers (no measurement / impossible %) instead of reading
  them as "Healthy (fill 0%)"; an inverted ladder (misconfigured env) is shouted and
  the built-in defaults stay in force.
- **Line B (conduct)**: the escaped-signal ladder is re-banded to `0–2 none · 3 Mid ·
  4 High · ≥5 Warning` — a small burst of escapes usually shares one root cause (a
  capability gap), which is not exhaustion. The ladder is a code constant on purpose:
  team policy changes by edit + review, not by env fiddling.
- The v2 composite ("escaped signal past the Warning band ⇒ Danger") is **deleted** —
  no cross-weighting; throttle-zone errors are annotated, never auto-escalated.
- New env knobs: `STRAIN_CAP_MID/_HIGH/_WARN`, `STRAIN_THROTTLE_ONSET`,
  `STRAIN_WRAP_BUDGET` (replacing `STRAIN_FILL_*`). The readout prints the caps in
  force. MANDATORY-wrap / prepare-to-wrap / recovery directives ride with the tick;
  the recovery directive prints once per compaction event.
- README gains a "three numbers are yours to fill in" section — window, throttle
  onset, wrap budget — the calibration work an adopting team owes its own setup.
- Selftest: 76 checks, including the v3 acceptance rows (abstention, config-invalid
  fallback, no-cross-weighting, throttle-zone annotation gating).
- Design provenance: architecture designed and ruled by Rae Sun (arcgram.io);
  drafted and adversarially hardened in multi-model AI collaboration (see README).

## 0.2.1 — 2026-09-09

Denominator table refresh (sourced from the official help-center context-window
page, checked 2026-09-09): `opus-5` / `opus-4-8` / `opus-4-7` / `mythos` → 1M;
`sonnet-5` → 500K (its Cowork auto-compaction ceiling — the conservative choice on
other surfaces). Fixes a field incident where a 1M-window session divided by the
200K default read 102% and was used as Danger evidence. The numerator was audited
in the same incident and left untouched: the three usage buckets partition the
prompt on API-semantics hosts (audit note now in `_usage_of`). Selftest 63 → 65.

## 0.2.0 — 2026-09-04

Strain v2: fill-primary, auto-calibrating, de-ratcheted.

- **Fill bands are the primary signal** — 40/60/75/85% of the *detected* window enter
  Mid/High/Warning/Danger. A 200k and a 1M session get different absolute budgets from
  the same bands, with zero config edits (`STRAIN_FILL_*` to retune).
- **The tick computes and proposes the tier itself** and prints the basis. Ticks
  accumulating never escalate; a lower proposal is offered as decay. The
  "continuing past a Warning ⇒ Danger" rule is deleted — it pinned Danger at a
  measured 33% fill in three separate real sessions (2026-08-09/12/15).
- **Hard signals are escaped-weighted** — new `strain-signal.sh <kind>
  --caught|--escaped` ledger. Escaped signals floor the tier absolutely (1 → High,
  2+ → Warning; Warning-band fill + escaped → Danger). Caught-and-fixed errors move
  nothing and feed a repeat-class pattern note instead.
- **Calibration is observable** — SessionStart and every tick print substrate ·
  window · bands · signal mode. Substrate detected from the transcript path
  (`STRAIN_SUBSTRATE` overrides).
- **Estimated mode** — a transcript without token usage now yields a byte-derived
  fill estimate (~4 bytes/token), labelled ESTIMATED, instead of falling back to
  action counting.
- **Selftest 47 → 63 checks**, including the negative fixture: the v1
  Danger-at-33%-fill bug reproduced (19 of the new checks fail against the v1
  scripts) and passing on v2. A wrap reset now also clears the signal ledger.

## 0.1.0 — 2026-08-18

First public release: per-session counters, measured/inferred context modes,
model-following denominator, wrap-marker reset semantics, 47-check selftest.
