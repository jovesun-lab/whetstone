---
name: start
description: >-
  Use at the START of every session, before your first reply — short sessions too — and
  again at the wrap or handoff. Checks that strain (the session-strain meter) has signed
  this session in, signs it in if not, asks the user for permission the right way, and
  offers once to add this step to the agent's instruction file. Also use whenever strain
  says a session is not signed. Triggers on: session start, new session, first reply,
  sign in, strain not signed, strain start, wrap up, handoff, end of session.
---

# Strain — start and wrap

Strain counts how loaded a session has become, but only a **signed** session joins the
chain: the next session of the same agent can then report how this one went. Signing is
one command. These steps make sure it happens at the start, and that the user is asked
properly when the host needs their approval.

Every command below is printed, filled in, in strain's start line (it begins "STRAIN
START") and in every strain tick. Copy it from there — it carries this session's key, the
state folder and the plugin's path.

## At the start

1. **Check.** If strain's start line says "this session is not signed in yet", go on.
   Without a start line, run `strain-sign.sh --receipt`: it says "not signed" or
   "signed as <name>". Signed → you are done; go to step 6.
2. **Sign.** Run the sign command from the start line. Keep the default name it shows
   (`<host> · <project folder>`, the same every session, so sessions link up); add
   `--agent '<name>'` only if the user gave you a name.
3. **Describe it for the user.** When you run it, describe the command in the user's
   language, in plain words, saying what it does for them — for example "Turn on strain:
   track how full this conversation is". Your host shows that sentence when it asks the
   user to approve the command; it is all they see.
4. **If your host asks the user to approve it,** keep the prompt open until they answer —
   do not end your turn. If your host has no prompt, ask in chat, then end your turn and
   wait for the reply.
5. **Allowed:** tell the user the one sentence the sign prints (and, with a ledger, the
   line about the previous session). **Refused:** do not sign. Tell the user strain will
   only count this session, and carry on with the work. Do not ask again before the wrap.
   If the sign fails with "could not write state", follow the numbered steps it prints.
6. **Offer the instruction file — once.** If the start line has a step about the
   instruction file:
   1. Ask the user whether to add strain's start step to their instruction file, so every
      new session signs in by itself. Offer the **global** file first (every project, this
      computer only); this project's own file is the alternative.
   2. Run `strain-sign.sh --instructions`: it prints the block and says where the files
      are and whether the block is already there.
   3. Show the user the block. Add it to the file they chose only if they agree.
   4. If they say no, record it: `strain-sign.sh --decline-instructions`. Strain will not
      ask again on this host.

## At the wrap

1. Write your handoff (strain does not).
2. **Check again:** `strain-sign.sh --receipt`. If it says "this shell cannot write" or
   "not signed", ask the user for permission as in steps 3–4 above — keep the prompt open
   until they answer, do not end your turn.
3. **Allowed:** sign if the session is not signed yet, then stamp the wrap:
   `strain-wrap.sh --label "<what was handed off>"` (add `--with-debt` for known loose
   ends). Tell the user the line it prints.
4. **Still refused:** no sign, no stamp. Report the counts only (the tier, the tool calls,
   the errors that reached the user).
5. The next session starts again from *At the start*, step 1.

## Limits the host controls

- **When a prompt closes is the host's decision.** Strain can only tell you, in steps and
  every time, to keep it open. If it closed before the user answered, ask again in chat.
- **Some hosts ask for approval per command.** The user may approve each strain command,
  or approve it once for the session where the host offers that.
- **A session that never wraps** keeps its counts but leaves no wrap stamp; the next
  session's report says "not wrapped".
