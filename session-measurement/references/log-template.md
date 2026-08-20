# Log structure (the persistent record)

Keep one markdown log per project. It holds the trend table (the matrix) plus one short
paragraph per session, with the chart image embedded. This is what you append to every run.

## Layout

```markdown
# <Project> — agent performance log

![trend](trend-table.png)

| metric | S1 | S2 | ... |
|---|---|---|---|
| change/note | tag1 | tag2 | ... |
| version | v0.1 | v0.2 | ... |
| MAIN landed (L/P/N) | L | P | ... |
| strain at wrap (optional) | Healthy | High | ... |
| Redefinitions absorbed | 3 | 2 | ... |
| Clarifying gates raised | 2 | 2 | ... |
| Errors self-caught | 2 | 1 | ... |
| Misses human caught | 1 | 3 | ... |
| Critical bugs - agent caught | 0 | 0 | ... |
| Critical bugs - human caught | 0 | 1 | ... |

*(notes: which sessions are full reads vs estimates; what "critical" means here;
exclusions; any cell grounded/corrected against the authoritative record.)*

## Per-session entries

**S1 - <date> - <topic>** (version v0.1) - 3 / 2 / 2 / 1 - crit 0/0 - MAIN: L.
One short paragraph: what landed, the notable catch (strength), the honest miss.
![[measurement-S1.png]]

**S2 - ...**
```

## Why this shape
- The **trend table** is the at-a-glance matrix — read across a row to see a metric move
  over versions, read down a column to see one session's profile.
- The **per-session paragraph** carries the story a number can't: *why* a miss happened,
  whether a `P` was a reframe or a regression, whether a catch was the agent's or yours.
- Embedding the **chart** keeps the visual next to the prose so a reader doesn't have to
  reconstruct it.

Markdown image embeds: use `![[measurement-S1.png]]` for Obsidian, or
`![](measurement-S1.png)` for plain markdown — match your reader.
