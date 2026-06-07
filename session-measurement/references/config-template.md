# config.json template

Copy this to `config.json` next to your `sessions.json` on first use. Fill it by either
(a) letting the agent inspect the project and propose values for you to confirm/supplement,
or (b) providing the values yourself.

```json
{
  "project": "<agent + project being benchmarked, e.g. 'CodeAssistant on repo X'>",
  "version_axis_label": "<what 'version' tracks: 'model' | 'frame' | 'build' | 'skill-set'>",
  "transcript_source": "<how to get a session transcript here: a session-reader tool name, or 'user pastes/exports the transcript'>",
  "critical_definition": "Default 3 (task forgetting; a fixed bug recurs 2+ times; a bug breaks a working feature / dead-loop) PLUS domain-specific severe defects, e.g. <add yours>",
  "grounding_source": "<an authoritative record to reconcile counts against: a work log or status log / task tracker / status doc path, or 'none'>",
  "exclusions": "<session types to skip and why, e.g. 'pure Q&A sessions; skill demos on unrelated content', or 'none'>"
}
```

## Field notes

- **version_axis_label** — pick the dimension you most want to track improvement against. If
  you swap models often, use `model`. If you iterate on the agent's operating frame /
  scaffolding, use `frame`. You can put the concrete value (e.g. `gpt-x`, `frame-v3`) in each
  session's `version` field.
- **transcript_source** — the only environment-specific adapter. If the host exposes a
  session-reader, name it. If not, the workflow still runs: the user exports or pastes the
  transcript and you score that.
- **critical_definition** — always keep the 3 defaults; append what "severe" means in your
  domain (a coding agent: a shipped crash; a research agent: a fabricated citation; a support
  agent: a wrong factual answer to a customer).
- **grounding_source** — if you have an authoritative record (a work log or status log, a ticket system),
  name it so counts get reconciled instead of trusted. If you have none, set `none` and lean
  harder on full reads.
