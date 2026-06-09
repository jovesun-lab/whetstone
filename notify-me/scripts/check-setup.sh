#!/usr/bin/env bash
# On session start, if notify-me isn't configured yet, nudge the agent to offer setup.
CONFIG="$HOME/.notify-me/config"
if [ ! -f "$CONFIG" ]; then
  cat <<'JSON'
{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"The notify-me plugin is installed but not yet configured (~/.notify-me/config is missing). At a natural moment, briefly offer to run the notify-me-setup skill so the user can pick a phone topic and an alert sound. Mention it once; do not nag."}}
JSON
fi
exit 0
