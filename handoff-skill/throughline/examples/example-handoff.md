# Handoff — add rate-limiting to the public API

## Machine fields

- session: 7f3a-example · 14 · agent: an agent · model: any · host: any
- started 2025-03-14T13:05Z · ended 2025-03-14T16:20Z
- verdict: Ship per-API-key rate limiting on the public REST API — PARTIAL

| file | md5 |
|---|---|
| `ratelimit/middleware.py` | 3c9e1f0a7b21 |
| `api/app.py` | 8d02aa41c6e5 |

## ⭐️ Goal

Test the rate limiter's Redis-down path

## Where this session stopped

The token-bucket middleware is built and unit-tested and wired in behind `rate_limit_enabled`, which is
**off** everywhere. Not verified yet: behaviour when Redis is down (it must fail open).

## Done

### MAIN: Ship per-API-key rate limiting on the public REST API — PARTIAL
Evidence: `make test ratelimit`, 14/14 green locally; the flag is still off and the PR unreviewed, so not shipped.
- 🔸 token-bucket middleware with unit tests · done
- 🔸 config flag through settings and the Helm values · done
- 🔸 Redis-down path fails open · carried → ROW-0314-01
- 🔸 load test at 2× peak · carried → ROW-0314-02
- 🔸 platform-team review of the PR · carried → ROW-0314-04

## Next actions

1. Test the rate limiter's Redis-down path · ROW-0314-01
2. Load-test at 2× expected peak before flipping the flag in staging · ROW-0314-02
3. Add the `Retry-After` header to 429 responses · ROW-0314-03
4. Get the PR reviewed by the platform team · ROW-0314-04

## Waiting on others

- The platform team: review of the draft PR · ROW-0314-04

## Project state

- Flag `rate_limit_enabled`: off in staging and prod (Helm values, 03-14).
- Draft PR open, no review yet.

## Rulings not yet home

- Default limit is 100 requests/min per API key; on a Redis outage the limiter fails open; rollout is staging first, prod only after the 2× load test (confirmed 03-12 to 03-14) · `docs/rfcs/2025-02-rate-limiting.md`

## Re-derive on pickup

- Re-run `make test ratelimit` — expect 14/14 green; the cache-pool refactor on `main` may have moved since.
- Compare the md5 of the two files above — expect them unchanged unless someone touched the limiter.
- Confirm `rate_limit_enabled` is still off in the prod values file before anything else.
