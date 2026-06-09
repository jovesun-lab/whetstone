#!/usr/bin/env bash
# note.sh "plain-language reason"
# Leave a one-line, human description of what you need, in the user's language.
# The next notify-me push uses it as the body (and then clears it).
# Call this right before you pause for a decision.
MSG="$*"
[ -n "$MSG" ] || { echo "usage: note.sh \"why you need the user\""; exit 1; }
mkdir -p "$HOME/.notify-me"
printf '%s\n' "$MSG" > "$HOME/.notify-me/note"
echo "note set: $MSG"
