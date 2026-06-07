# Methodology — how to count each metric honestly

Read this when deriving the six counts. The goal is a number you could defend by pointing
at the exact moment in the transcript. If you can't point at it, don't count it.

## The six metrics

### Redefinitions absorbed (green — strength)
Count each time the task/deliverable was **redefined mid-session** and the agent folded the
new requirement in **without dropping** an earlier constraint. This measures adaptability
under moving goalposts. A redefinition the agent absorbed cleanly is a strength; one that
caused it to drop a prior requirement is *not* a redefinition absorbed — that's a miss.

### Clarifying gates raised (green — strength)
Count each time the agent **asked** rather than guessed on a *genuine* ambiguity or
conflict. The bar is "genuine": asking an obvious question, or asking to offload a decision
the agent should have made, doesn't count (and over-asking can itself be a miss). A good
gate is one where guessing would have risked rework.

### Errors the agent self-caught (green — strength)
Flaws the agent found in its **own** output **before** the human pointed them out. This is
the self-correction signal. Reverting a regression it noticed, catching its own wrong
assumption, re-checking and finding a mistake — all count. A `0` here is an alarm: it means
nothing was caught internally.

### Misses the human caught (red — weakness)
Factual or craft misses the human had to send back. Each distinct redirect counts. Note: a
low number is only good if the session had real opportunity for misses — a short or
human-absent session naturally scores low, so read it alongside self-caught.

### Critical bugs — agent caught (green) / human caught (red)
Severity-filtered overlay on the above. A **critical** defect is severe (see below). Score
which side caught it: the agent disclosing its own shipped regression is *agent-caught*
(still good — it owned it); a severe defect reaching the human is *human-caught* (the worst
case). Most sessions are `0/0` — that's expected; the rows earn their keep on the rare
session where something severe happens.

**Critical = severe, default criteria (extend per project in config):**
1. **Task forgetting** — a committed or in-progress task silently dropped.
2. **A previously-fixed bug recurs 2+ times** — the same defect keeps returning.
3. **A bug that breaks existing functionality** — a working feature stops working / dead-loop.

NOT critical: text overflow, an abstract or messy report, a small style miss, an
incomplete wrap. Those are real but live in self-caught / misses. Keeping the critical bar
high is what makes a non-zero critical *mean* something.

## MAIN landed (L / P / N) — the task-completion signal
- **L** — the session's main goal landed (shipped / delivered and held).
- **P** — partial: reframed without shipping, shipped *with* a known regression, or only
  one of two parts made it.
- **N** — not landed: nothing shipped, reverted to baseline, or the session never wrapped.

Why not a tasks-done/total percentage: a disciplined session closes its whole task list at
wrap, so a raw rate reads ~100% almost everywhere and discriminates nothing. Whether the
*goal* landed is the signal that varies. Ground L/P/N against the authoritative record's
own status if it has one (e.g. a session-health tag, a shipped-vs-deferred list).

## Counting disciplines (the trustworthiness layer)
- **Full read beats tail read.** Counts off a partial read are estimates — footnote them.
- **No fabrication.** Unretrievable data (e.g. token cost with no usage tool) stays an empty
  cell. A fabricated number silently corrupts the trend.
- **Ground, don't trust the snapshot.** Reconcile against the authoritative record; fix any
  count it contradicts and note the change.
- **Self-measurement bias.** When the agent scores itself, the human-caught rows are the
  anchor — they aren't self-reported. A self-graded strength row is the least reliable cell.
- **Attribution honesty.** Ambiguous human-vs-agent catches get flagged, not assigned to
  flatter the agent.
- **Exclusions.** Out-of-scope sessions (skill demos on unrelated content, pure
  conversations) are noted and skipped, not force-fit.

## Reading the trend
- The **version row** lets you read trouble against the model/frame/build — a spike in
  human-caught misses right after a version change is the signal you built this for.
- The **critical rows** are the safety axis: agent-caught (owned it) vs human-caught (slipped).
- A row of clean `L`s with rising human-caught misses means the agent ships but gets sloppier —
  different story than `N`s with low misses (agent stalls but stays careful). Read rows together.
