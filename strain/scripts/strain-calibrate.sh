#!/usr/bin/env bash
# Shell wrapper for strain-calibrate (0.6.0): record this environment's context window
# -- sourced, dated, typed (nominal|runtime). The record becomes the fill denominator
# until it expires; see _strain_calibrate.py for the why of each required field.
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$DIR/_strain_calibrate.py" "$@"
