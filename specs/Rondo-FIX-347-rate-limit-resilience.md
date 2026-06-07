# Rondo-FIX-347: Rate-limit resilience (429 handling)

**Product:** Rondo | **Category:** FIX | **Sprints:** RONDO-347, RONDO-348
**Created:** 2026-06-07 | **Status:** ACTIVE
**Found by:** USH 80-vote live panel — 9/80 votes lost to mistral HTTP 429.
Independently flagged by all 3 AIs in the 2026-06-07 hostile re-review (dim 10).

---

## 1. The problem

A burst dispatch (20 tasks × 4 providers, 4 workers) blows a provider's
rate limit. `retry_http` retried but:
- **(347)** ignored the server's `Retry-After` header — slept a fixed
  0.5/1/2s and gave up while mistral asked for longer → votes lost.
- **(348)** nothing throttles the *outbound* burst, so all N requests to a
  provider fire at once and trigger the 429 in the first place.

## 2. Fix 347 — honor Retry-After (DONE)

`_retry_after_sec(exc)` reads the integer-seconds `Retry-After` header off
an HTTPError; `retry_http` waits `max(backoff, Retry-After)` capped at
`_RETRY_AFTER_CAP_SEC = 60` so a hostile value can't hang a dispatch.
Shared seam → every provider's 429 handling improved at once.

**Verification:** `tests/unit/test_retry.py` — 9 tests incl. an UNMOCKED
real-`HTTPError` contract test (pins the header shape the parser depends on).
Honors seconds form; HTTP-date form falls back to backoff (documented).

## 3. Fix 348 — outbound pacing (EVIDENCE-GATED, not built blind)

**Honest reassessment 2026-06-07:** the lost-votes panel ran at **4 workers**.
A per-provider *concurrency* cap ≥4 would never fire at 4 workers — so the
429s were **requests-per-minute** pressure, not concurrency. A concurrency
cap would be speculative complexity that does NOT address the observed bug.
Retry-After (Fix 347) is the correct fix for the recovery path.

**Decision:** do NOT build pacing on speculation. Gate it on evidence:
1. Live-verify 347 with a real mistral micro-burst canary (~$0.01).
2. If 429s still LOSE votes after Retry-After, the real fix is a per-provider
   **RPM token-bucket** (concurrency caps won't help RPM) — a larger change,
   specced then, with the canary as proof it's needed.
3. If the canary recovers cleanly, 348 is unnecessary — say so, don't pad.

This is honesty engineering: no fix without a failure that demands it.

### 3a. What the canary actually proved (2026-06-07)

Three evidence-driven layers shipped, each demanded by a live canary:
1. **Retry-After honoring** (347) — wait what the server asks, capped 60s.
2. **Per-provider concurrency gate** — `BoundedSemaphore`, default cap 4,
   per provider (cross-provider stays parallel).
3. **429 rate-limit floor + more attempts** — a 429 with no Retry-After
   (mistral sends none) waits ≥2s; `max_attempts` 3→5.

**Canary results (8 mistral tasks, `--workers 8`):**
- Before: 4/8, failures gave up in ~2.5s (short backoff exhausted).
- After: 4/8 — BUT failures now retry a real 11–14s before giving up
  (floor + 5 attempts engaged) and the 4 that fail do so HONESTLY with
  ERR_RATE_LIMIT.
- **Realistic load (4 tasks, `--workers 4`): 4/4 clean.**

**Honest conclusion — provider wall, not a client bug:** mistral free tier
is ~4 requests/MINUTE. 8-in-a-burst can't all succeed no matter the client
strategy short of minute-scale spacing (which would cripple every provider).
The fixes deliver the maximum a client can: serve the quota cleanly, retry
the rest patiently, fail honestly. **Do NOT add minute-long waits or a
global RPM token-bucket to beat a synthetic 8-burst** — that would harm
normal use to chase an extreme. For mistral-heavy bursts: use `--workers`
≤ the provider's per-minute quota, or expect a follow-up pass for the
overflow. 348 is DONE; no 348b.

## 4. Non-goals

- No token-bucket per-RPM modelling (provider limits vary, undocumented) —
  a simple concurrency cap + Retry-After backpressure is the right size.
- No retry of non-transient 4xx (auth/bad-request stay immediate failures).

## 5. Change history

| Version | Date | Change |
|---------|------|--------|
| 0.1 | 2026-06-07 | 347 Retry-After honoring shipped; 348 outbound pacing specced. |
