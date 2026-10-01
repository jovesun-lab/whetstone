#!/usr/bin/env bash
# Shell wrapper for strain-report (0.8.0): draft a bug report about strain itself, for the
# user to read and send by hand. Nothing is sent. See _strain_report.py for what the draft
# carries and what it never carries.
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$DIR/_strain_report.py" "$@"
