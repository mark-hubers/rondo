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

## 3. Fix 348 — outbound pacing (PLANNED, this sprint)

Prevent the burst rather than only recovering from it: a per-provider
concurrency/rate gate so requests to one provider don't all fire at once.
Design constraints:
- Must NOT change the stable surface (no new required config; sane default).
- Must NOT serialize across providers (gemini + grok still run in parallel).
- Lives at the dispatch seam, not in each adapter (one place, all providers).
- TDD: a test that simulates N concurrent same-provider calls and asserts
  they don't exceed the gate; cross-provider stays concurrent.

## 4. Non-goals

- No token-bucket per-RPM modelling (provider limits vary, undocumented) —
  a simple concurrency cap + Retry-After backpressure is the right size.
- No retry of non-transient 4xx (auth/bad-request stay immediate failures).

## 5. Change history

| Version | Date | Change |
|---------|------|--------|
| 0.1 | 2026-06-07 | 347 Retry-After honoring shipped; 348 outbound pacing specced. |
