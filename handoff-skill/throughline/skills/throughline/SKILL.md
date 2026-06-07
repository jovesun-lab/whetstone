---
name: throughline
description: "Throughline keeps the thread of work intact on work that's big enough to drift or that outlives one sitting. Two linked habits: (1) TASK TRACK — an emoji-tagged task list with exactly one ⭐️ MAIN goal anchor, so you can see at a glance whether you're still solving the main thing or have drifted; (2) HANDOFF — compact a session into a plain-markdown handoff doc the next agent (any agent) can pick up cleanly. Reach for it when: a long or many-step task is at real risk of losing the thread, you catch yourself drifting off the original goal, you're wrapping up or running low on context, you're switching agents or sessions, or you're explicitly asked to 'hand this off' / 'write a handoff' / 'summarize for the next session' / 'compact this' / 'pick up where we left off' / 'resume'. Do NOT reach for it on short, self-contained tasks that finish in one pass — the full protocol is overhead there. Capability-agnostic and cross-platform — works as a skill or a plain paste-in prompt."
license: MIT
---

# Throughline

*Keep the thread — Task Track within a session, Handoff across them.*

> **For any AI agent reading this file.** The frontmatter uses Claude's skill format; the
> body is plain markdown. It works the same for Claude, OpenAI, Gemini, Cursor, Cline, Aider,
> or a local model — paste the body in as a prompt if your platform has no skill system.
> Assume **nothing** about your host's capabilities; everything here degrades gracefully
> (see "Capability-agnostic by design" below).

## What this is

Long or multi-agent work fails in two predictable ways, and this skill is two habits that
each kill one of them:

- **Within a session, reasoning drifts off the goal.** You solve a small problem, which
  surfaces another, which pulls you somewhere adjacent to what you started on. Every step is
  locally reasonable; together they bend the trajectory. **Task Track** makes that drift
  *visible* by keeping one ⭐️ MAIN goal anchor in front of you.
- **Across sessions, the thread is dropped.** A fresh run (or a different agent) starts cold,
  re-derives what was already known, or trusts a stale summary. **Handoff** carries the thread
  forward as a plain-text artifact any agent can pick up.

**The correlation — the load-bearing point.** The **⭐️ MAIN tag is the shared goal anchor.**
Task Track holds it *within* a run; Handoff carries it (plus state) *across* runs. One sentence:
**don't lose the thread — within a session or between them.** The same anti-drift purpose runs
through both, which is why they ship together.

## When to use

- A **long or many-step task at real risk of losing the thread** → set up Task Track. (For a
  short, self-contained task that finishes in one pass, skip it — the overhead isn't worth it.)
- You notice the work has wandered → re-read the ⭐️ MAIN and decide if you've drifted.
- Wrapping up, running low on context, or switching agents → write a Handoff.
- Beginning a session that has a prior handoff → run the Resume flow.

---

## Part 1 — Task Track (the within-session half)

Keep a task list where **exactly one task is the ⭐️ MAIN** — the goal anchor — and every other
task carries a leading emoji marking *where it came from*, so drift reads at a glance:

| Tag | Meaning |
|---|---|
| **⭐️ MAIN** | The session's primary task / goal anchor. **Exactly one at a time.** Re-read it before any load-bearing step: *"am I still solving the MAIN, or something it slid into?"* |
| **🌶️ Critical** | A critical bug or big-impact task in service of the MAIN. |
| **🍏 Temp this session** | Surfaced mid-session, not in any plan. A transient. If it balloons past the MAIN's scope → **stop and re-confirm** with the human, don't let it silently become the main line. |
| **🍋 Logged + recurred / pulled-in** | A previously-logged task that came back, OR a logged task not planned for this session but worth doing now. |

Put the emoji **in the task's title** (the always-visible spot), not just in a description field —
if your task UI renders badges, use those too, but the title is the reliable channel.

**The discipline, not the decoration:** the value isn't the emoji, it's that the trajectory
becomes legible. At any moment you can scan the list and see whether the work is still on the
main line or chasing transients. When a 🍏 keeps growing, that's the signal to stop and check it
against the ⭐️ MAIN.

Full rationale, examples, and how it pairs with Handoff: `references/task-track.md`.

---

## Part 2 — Handoff (the across-session half)

When wrapping up, write a **plain-markdown handoff** the next agent can pick up cold. The doc —
not a file, not a tool, not your platform — is the universal interface: any agent and any human
can read plain markdown.

**Writing a handoff** (the `handoff` operation — see `commands/handoff.md`):

1. **Fill the shared template** `templates/handoff.template.md`. It is the single source of truth
   for a handoff's structure; do not invent your own sections. The core sections:
   - **⭐️ Goal** — the one thing the next session is for (carry the MAIN forward).
   - **State** — where things stand now; mark anything unverified.
   - **Done** — what got completed (briefly).
   - **Open / Next** — open threads + recommended next move, in priority order.
   - **Re-derive on pickup** — what the next agent must reconcile against ground truth before
     trusting this doc.
   - **Suggested next steps / tools / skills** — concrete next actions and capabilities to reach for.
   - **References** — point to plans, specs, issues, commits, diffs, docs by path/URL.
2. **Reference, don't duplicate.** If a fact already lives in a plan, issue, commit, or diff,
   link it — don't copy it. Copies go stale; references stay single-source.
3. **Redact secrets.** No API keys, tokens, passwords, or personal data. Sweep before saving.
4. **Keep it bounded.** A handoff is the *latest* state plus pointers — not a running log of
   every session. If the project keeps a longer history, link to it; don't grow the handoff
   into a second log.
5. **Save it where the next agent will look** — if you can write files, the OS temp dir or an
   agreed handoff path; if you can't, just emit the doc inline in your reply.

**Resuming from a handoff** (the `resume` operation — see `commands/resume.md`):

1. Read the handoff and restate the ⭐️ Goal back, so the human sees you've oriented.
2. **Re-derive before trusting.** Follow the doc's "Re-derive on pickup" section: re-read the
   named artifacts, re-run the named check, re-confirm cited facts are still current. A snapshot
   trusted blindly is exactly how stale state causes drift.
3. Set up Task Track with the carried-forward ⭐️ MAIN, then confirm the plan before executing.

Full protocol, the five anti-drift mechanisms, and why each exists:
`references/handoff.md`.

---

## Capability-agnostic by design

The next agent may be on any platform, so assume no specific function exists. Each capability
has a graceful fallback:

| If you have… | use it for… | If you don't… |
|---|---|---|
| File-system write | saving the handoff to a known path | emit the handoff **inline** in your reply — the doc is the deliverable, not the file |
| Live access (web, repo, tools) | re-deriving state against ground truth | re-derive from the **artifacts you were handed**; flag what you couldn't verify |
| Code execution | the optional `tools/handoff.py` validator | skip it — the prompt does the whole job without it |
| A skill / slash-command system | invoking `handoff` / `resume` as commands | paste the relevant section in as a plain prompt |

The two reasoning disciplines — the **⭐️ MAIN goal anchor** and **re-derive-don't-trust** — have
zero capability dependency, so they hold at the lowest common denominator.

## Optional helper (code-capable environments only)

`tools/handoff.py` is a single-file, zero-dependency (Python stdlib) helper that does only the
*mechanizable* half — it never summarizes:

```bash
python3 tools/handoff.py new                 # scaffold a blank handoff from the template
python3 tools/handoff.py check HANDOFF.md    # validate: sections present, one ⭐️ MAIN,
                                             # re-derive note present, secret-pattern sweep
```

It reads the required sections **from the shared template at runtime**, so the validator and the
prompt can never drift on structure. It's optional — if you can't run code, the skill is complete
without it.

## Files in this skill

| File | Purpose |
|---|---|
| `SKILL.md` | This file — the two habits and how they connect. |
| `commands/handoff.md` | The write operation (drop-in slash command + paste-in prompt). |
| `commands/resume.md` | The read / pick-up operation. |
| `templates/handoff.template.md` | Single source of truth for handoff structure. |
| `references/task-track.md` | The within-session discipline, in depth. |
| `references/handoff.md` | The across-session protocol (the five anti-drift mechanisms), in depth. |
| `examples/example-handoff.md` | A filled-in handoff to copy the shape from. |
| `tools/handoff.py` | Optional stdlib scaffold/validate helper. |
| `assets/logic-flow.svg` | Diagram of how the two halves connect. |

## License

MIT. Free to use, modify, embed, redistribute. Attribution appreciated.
