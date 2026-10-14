# Changelog

## Since 0.1.1 — untagged

- **A selftest** — `bash notify-me/tools/selftest.sh` runs the plugin's scripts against a throwaway home folder and a capture
  server on 127.0.0.1: the push (topic, title, priority, body), the opt-in "finished" ping, the agent's note used once, the hook's
  message, the older `TOPIC=` name, no token, a server that is down, and the setup offer. Nothing leaves the machine, no sound
  plays, your own config is never read. 31 checks.
- **2026-08-20 — attribution.** The plugin's author field and the LICENSE copyright now read `arcgram.io`. No change to
  behaviour, config or hooks.

## 0.1.1 — 2026-06-09

**First public release** (the tag `notify-me-v0.1.1` marks this published state).

- **Phone push when an agent is blocked** — a `Notification` hook sends one high-priority `curl` to your private
  [ntfy](https://ntfy.sh) topic; the ntfy app on your phone shows it. The token you subscribe to *is* the password on the
  public ntfy.sh server — keep it private, or self-host ntfy and set `SERVER`.
- **A sound on this computer** — `SOUND` on/off, `SOUND_FILE` a file path or `@system` for your OS alert sound.
- **"Agent finished" pings** — the `Stop` hook, off by default (it fires every turn); opt in with `NOTIFY_ON_STOP`.
- **Setup in plain chat** — say "set up notify-me": pick a sound from the ones found on your computer (preview first), turn
  the chime on or off, choose a private phone token or have one generated, and a test ping confirms both ends.
- **One config file**, `~/.notify-me/config` (`config.example` in this folder); best-effort only — a failed ping never
  disrupts the agent.
