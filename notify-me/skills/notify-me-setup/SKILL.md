---
name: notify-me-setup
description: Set up or change notify-me — the plugin that pings the user's phone (via ntfy) and/or plays a sound when an agent is blocked or finished. Use when the user says "set up notify-me", "set up notifications", "notify me when you're blocked", "call me back when you need me", "change the alert sound", "turn the chime on/off", "change my ntfy topic", or when a SessionStart note reports notify-me is installed but not configured.
---

# notify-me setup

This skill configures the `notify-me` plugin by writing `~/.notify-me/config`, which the
notification hook reads. Run the whole flow in plain chat. Do NOT use a popup/AskUserQuestion —
present every choice as lettered text options in the message and wait for a typed reply.

## Config file format

Write `~/.notify-me/config` as sourceable shell `KEY="value"` lines:

```
TOKEN="user-chosen-secret"   # this IS the ntfy "topic" you subscribe to on your phone
SOUND="on"
SOUND_FILE="/System/Library/Sounds/Glass.aiff"
NOTIFY_ON_STOP="off"
SERVER="https://ntfy.sh"
```

Field meaning:
- `TOKEN` — the private secret the phone subscribes to. In the ntfy app this value is called the "topic". Acts as a password, so it must be random/unguessable.
- `SOUND` — `on`/`off`. Whether to play a local sound on this computer.
- `SOUND_FILE` — absolute path to a sound file, OR the literal `@system` to play the OS's currently-selected alert sound (macOS "beep" / Windows beep). A real file path is more reliable than `@system`, because `@system` follows the separate OS "alert volume" which is easy to leave at zero.
- `NOTIFY_ON_STOP` — `on`/`off`. If `on`, also alert when the agent finishes a turn (fires often — default `off`).
- `SERVER` — ntfy server base URL. Leave as `https://ntfy.sh` unless the user self-hosts.

## First-run / setup flow

If `~/.notify-me/config` already exists, read it and show current settings first, then ask which field to change. Otherwise run full onboarding:

### Step 1 — pick the alert sound list (from THIS machine)
Run the bundled scanner to list sounds actually present on the user's computer:
```
bash "${CLAUDE_PLUGIN_ROOT}/scripts/list-sounds.sh"
```
Present the returned files as a lettered list (label by filename, e.g. "A) Glass  B) Ping  C) Submarine ..."). Offer to preview any sound before choosing — on macOS preview with `afplay "<path>"`. Let the user pick one, or pick a sensible default (Glass on macOS) if they don't care — prefer a real file over `@system` for reliability. Always offer `@system` as one option for users who'd rather have the alert follow whatever sound they pick in their OS sound settings (warn that it depends on the OS "alert volume"). If the scanner returns nothing (e.g. Windows, or an unusual setup), offer `@system`, ask for an absolute path to a sound file, or set `SOUND="off"` (phone push still works).

### Step 2 — sound on or off by default
Ask whether the local computer sound should be `on` or `off`. (Phone push still works either way.)

### Step 3 — phone token (ntfy "topic")
Ask the user to either supply a token or let you generate one. If generating, make it random and unguessable, e.g.:
```
echo "notify-$(LC_ALL=C tr -dc 'a-z0-9' < /dev/urandom | head -c 10)"
```
Explain plainly: this token IS the password — anyone who knows it can read or send to it on the public ntfy.sh server, so it must stay private. Note that the ntfy phone app calls this same value a "topic".

### Step 4 — write the config
Create the directory and write the file:
```
mkdir -p "$HOME/.notify-me"
```
Write the five fields with the chosen values. Always append the inline comment `# this IS the ntfy "topic" you subscribe to on your phone` to the TOKEN line so the user can recognize it later. Set `NOTIFY_ON_STOP="off"` unless the user asks to also be pinged on every turn end.

### Step 5 — phone app guidance
Tell the user, in plain language, to finish the phone side:
1. Install the **ntfy** app (iOS App Store / Android Play Store).
2. Add a subscription using the exact TOKEN value from the config (the app labels this field "topic").
3. The sound the phone plays is controlled inside the ntfy app's per-topic settings — set it there (this plugin can't set the phone's sound from the computer).

### Step 6 — test
Offer to send a test ping so the user can confirm both the local sound and the phone push:
```
echo '{"message":"notify-me test — you should hear a sound and get a phone push."}' | bash "${CLAUDE_PLUGIN_ROOT}/scripts/notify.sh" blocked
```
Tell them to check their phone. If nothing arrives, re-check that the phone subscribed to the same topic and that the device has network.

## Sending a task-aware ping (for the agent, during work)
The automatic push shows a generic line. To make it say, in plain language, *what* you need, leave a
one-line note right before you pause for a decision — write it in the user's language, plain words, no jargon:
```
bash "${CLAUDE_PLUGIN_ROOT}/scripts/note.sh" "Editing your config — confirm whether to overwrite the old file?"
```
The next push uses that note as its body, then clears it. Use this whenever you stop and genuinely
need the user, so the phone tells them why, not just that.

## Changing settings later
Re-read `~/.notify-me/config`, show current values, edit only the field the user names, rewrite the file.

## Uninstalling
To remove user settings: `bash "${CLAUDE_PLUGIN_ROOT}/scripts/uninstall.sh"` (deletes `~/.notify-me`). To remove the hook + scripts entirely, the user disables or uninstalls the `notify-me` plugin in their app.
