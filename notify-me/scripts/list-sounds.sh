#!/usr/bin/env bash
# Print the system sound files available on THIS machine, one path per line.
# Used by the setup skill to build the sound picker.
if [ -d /System/Library/Sounds ]; then
  ls /System/Library/Sounds/*.aiff 2>/dev/null
elif [ -d /usr/share/sounds/freedesktop/stereo ]; then
  ls /usr/share/sounds/freedesktop/stereo/*.oga 2>/dev/null
elif [ -d /usr/share/sounds ]; then
  find /usr/share/sounds -maxdepth 2 -type f \( -name '*.wav' -o -name '*.oga' -o -name '*.ogg' \) 2>/dev/null | head -30
fi
