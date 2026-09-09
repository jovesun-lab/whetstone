# Changelog

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
