# Changelog

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
