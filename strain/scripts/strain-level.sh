#!/usr/bin/env bash
# Shell wrapper for strain-level. The plugin registers the python directly; this wrapper is
# for manual use and for the test driver.
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$DIR/_strain_level.py" "$@"
