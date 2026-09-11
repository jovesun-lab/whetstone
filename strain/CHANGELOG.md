# Changelog

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
