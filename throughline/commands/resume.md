---
name: resume
description: Pick up work from a prior handoff document — orient, re-derive against ground truth, then continue.
argument-hint: "Path to the handoff doc (or paste it in)"
---

Resume work from a handoff document written by a previous session or a different agent. The point
of this flow is to pick up the thread **without inheriting stale state** — a handoff is a
point-in-time snapshot, and trusting it blindly is exactly how drift creeps in.

1. **Load and orient.** Read the handoff (from the given path, or from what the user pasted).
   Restate the ⭐️ Goal back to the user in one line so they can see you've oriented correctly.

2. **Re-derive before trusting.** Work through the handoff's "Re-derive on pickup" section. For
   each named item, reconcile the snapshot against ground truth using whatever access you have:
   - re-read the named artifacts (files, docs, plans);
   - re-run any named check or build;
   - re-confirm that cited facts/numbers are still current.
   If you lack live access, re-derive from the artifacts you were handed and **explicitly flag
   what you could not verify** — don't paper over the gap.

3. **Set up Task Track.** Create a task list with the carried-forward ⭐️ MAIN as the goal anchor
   (exactly one), and tag the open threads from the handoff by origin (🌶️ / 🍏 / 🍋). See
   `references/task-track.md`.

4. **Confirm, then execute.** Before doing load-bearing work, confirm the plan and the ⭐️ MAIN
   with the user — the top-of-queue item in the handoff may not still be the right next move.

If anything in the handoff contradicts ground truth when you re-derive, trust ground truth and
say so — the handoff was written before the world moved.
