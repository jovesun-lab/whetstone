# Changelog

## 0.2.1 — 2026-10-14

- **Your token stays yours** — setup now makes `~/.notify-me/config` readable by you only (`chmod 600`). The file holds the
  token, and the token is the password for your ntfy topic; before, other accounts on the same computer could read it. If you
  set notify-me up with an earlier version, run `chmod 600 ~/.notify-me/config` once (or ask your agent to). The selftest checks
  that the setup step is there: 32 checks.
- **Why 0.2.1 after 0.1.1** — a 0.2.0 build was shared outside the marketplace; this number stays above it, so an update never
  looks like a downgrade.
- Also in this release, from the untagged work below: the selftest and the attribution change.

## Untagged work after 0.1.1, released in 0.2.1

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
