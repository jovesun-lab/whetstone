# Handoff — add rate-limiting to the public API

_Written 2025-03-14 16:20 · for: finishing and shipping the rate-limiter behind a flag_

## ⭐️ Goal

Ship per-API-key rate limiting on the public REST API, default 100 req/min, behind the
`rate_limit_enabled` flag (off in prod until load-tested). This is the one thing to finish.

## State

- Middleware `ratelimit/middleware.py` written and unit-tested (token-bucket, Redis-backed).
- Wired into the app in `api/app.py` behind `rate_limit_enabled` — currently **off** everywhere.
- Redis connection reuses the existing cache pool; no new infra.
- **Unverified:** behaviour under Redis outage — there's a TODO to fail *open*, not yet tested.

## Done

- Token-bucket implementation + 14 unit tests (all green locally).
- Config flag plumbed through `settings.py` and the Helm values file.
- Draft PR opened (see References) — not reviewed.

## Open / Next

1. Test the Redis-down path (must fail open, not block all traffic).
2. Load-test at 2× expected peak before flipping the flag in staging.
3. Add the `Retry-After` header to 429 responses — spec'd, not implemented.
4. Get the PR reviewed by the platform team.

## Re-derive on pickup

- Re-run the test suite (`make test ratelimit`) — confirm still green; the cache pool refactor
  on `main` may have moved since this was written.
- Re-read the draft PR and the linked design doc for any review comments added after 03-14.
- Confirm `rate_limit_enabled` is still **off** in the prod values file before doing anything else.

## Suggested next steps / tools / skills

- Start with the Redis-outage test — it's the riskiest unknown and blocks the staging rollout.
- Reach for: a load-testing tool (k6 or locust), the test runner, and whatever your platform uses
  to read/modify the PR and CI status.

## References

- Draft PR: `https://example.internal/pull/482`
- Design doc: `docs/rfcs/2025-02-rate-limiting.md`
- Failing-open requirement: `docs/rfcs/2025-02-rate-limiting.md#failure-mode`
- Relevant commits: `git log --oneline ratelimit/`
