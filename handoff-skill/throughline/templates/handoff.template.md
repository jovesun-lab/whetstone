<!--
  HANDOFF TEMPLATE — the single source of truth for a handoff's structure.
  Both the prompt (SKILL.md / commands) and the optional validator (tools/handoff.py)
  point at THIS file for "what sections a handoff must have", so the two can never drift
  apart. If you change the section headings here, the validator follows automatically.

  Fill every "## " section below. Delete these HTML comments in the final doc.
  Keep it short: a handoff is a pointer-map, not a copy of the work.
-->

# Handoff — <one-line title of the work>

_Written <date/time> · by session <session name / id> · for: <what the NEXT session will focus on>_

<!-- Name the writing session: a short session name (set when the task crystallized, not
     invented now) plus the machine id if your host exposes one. One boot = one session = one
     id — if this session wrapped once already and kept working, this is still the SAME
     session; don't mint a second id. The name lets the next reader trace any claim here
     back to the session that made it. -->

## ⭐️ Goal

The ONE main thing the next session is for — the goal anchor. Exactly one.
Write it as a sentence the next agent can re-read and check itself against:
"Am I still solving this, or something it slid into?"

<!-- The anchor marker lives at the START of this heading/line. Use whichever renders best
     in your tools: ⭐️  or  the plain-text [MAIN]  or  a `main_goal: true` frontmatter line.
     Keep exactly one anchored marker in the whole doc — a ⭐ that appears mid-sentence in
     prose is not an anchor and does not count. -->

<!-- The goal's TITLE is frozen the moment it is confirmed. If this session's goal was
     redirected, the handoff carries BOTH: the original goal under its original name with an
     honest verdict (in Done), and the new goal as its own entry. A goal is never quietly
     renamed into whatever actually happened. -->


## State

Where things actually stand right now — the current, load-bearing facts only.
Mark anything unverified or in-flight as such. This is a point-in-time snapshot, not gospel.

## Done

What was completed this session (briefly). Link to the real artifacts; don't paste them.

Close the session's goal(s) with an explicit verdict, **under the frozen title from when each
was confirmed**: `LANDED` (with the evidence — the check that proves it), `PARTIAL` (what
landed, what didn't), or `NOT-LANDED` (where it's carried — it must reappear in Open / Next).
Silence is not a verdict, and a goal that "became something else" is a redirect with its own
honest NOT-LANDED — not a rename.

## Decisions

Decisions the human confirmed this session, one numbered row each (D1, D2, …), including
corrections ("D3 was wrong, corrected: …"). **Append-only:** a changed decision gets a new
row; the old row stays, struck through with a dated reason. This is what stops the next
session from re-litigating settled questions or archaeologizing chat logs. If none: "none".

## Open / Next

The open threads and the recommended next move(s), in priority order.
Name what's blocked and on what. If there's an obvious first step, say so.

## Re-derive on pickup

Before trusting anything above, the next agent should reconcile this snapshot against
ground truth — re-read the named artifacts / re-run the named check / re-check that cited
facts are still current. List exactly what to re-derive and against what, **with the
expected result written next to the check** ("run X, expect Y") — a named check with no
expected value can't tell the next agent whether the world moved. A handoff trusted
blindly is how stale snapshots cause drift.

## Suggested next steps / tools / skills

Concrete next actions, and any tools, skills, or commands the next agent should reach for.
Capability-neutral — name the capability, not one platform's button.

## References

Point to everything already captured elsewhere — plans, specs, issues, commits, diffs, docs —
by path or URL. Do NOT duplicate their content here; reference is single-source, copy drifts.

<!-- Secrets check: no API keys, tokens, passwords, or personal data anywhere above. -->
