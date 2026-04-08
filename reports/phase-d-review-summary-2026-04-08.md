# RONDO-210 Phase D — External AI Review Summary

**Date:** 2026-04-08
**Sprint:** RONDO-210 (validation pass)
**Providers:** gemini-2.5-pro (7031 chars, 39.9s), grok-3 (8942 chars, 68.3s)
**Cost:** ~$0.15 (estimate)

## Meta-finding before the review itself

The first run of Phase D via `rondo_multi_review` returned both provider
outputs **truncated at exactly 2000 characters**, mid-sentence. Investigation
revealed `mcp_dispatch.py:933` has a hardcoded `tr.raw_output[:2000]` slice
that truncates the output before `_multi_review_dispatch_one` reads it.

**Finding #258 logged** — partial closure of RONDO-209 #247. The provider-side
`max_tokens` was bumped to 8K but the Rondo-side cap was missed. Full reviews
were then captured by calling the adapters directly, bypassing the truncation.

## Consolidated risk list from both AI reviews

### HIGH severity — concurrency & state

1. **AuditTrail(auto_reconcile=True) false-positives under load** —
   Already logged as #257. **Both Gemini and Grok independently rated this HIGH.**
   Gemini extrapolated: a valid in-flight GPT-4 request incorrectly marked
   "stuck" gets re-dispatched by another worker → duplicate cost, confusing
   results. Grok noted: stress tests at >20 concurrent dispatches are missing.

2. **Systemic reconciliation race model** —
   Gemini framed #257 as a symptom of a fragile state-machine design. The
   INTENT → IN-FLIGHT → DONE transitions are not atomic across processes.
   Potential follow-ups: atomic reconcile primitives (distributed lock or
   fcntl-held "active dispatch" lockfile), timestamp-based conflict resolution.

3. **Multi-review output truncation** —
   Already logged as #258. **Both reviewers flagged it as HIGH** (Grok ranked
   it equal with #257).

### MEDIUM severity — risks pending verification

4. **Cyclic import initialization hazard** —
   Already captured in the initial #254 entry (before ID collision). 11 MCP
   family cycles remain from RONDO-209's partial fix. Under multi-process
   spawn, partial module initialization could cause non-deterministic failures.

5. **No correlation ID in audit trail** —
   **Logged as #259.** Structured logs carry request_id via bind_request_id(),
   but AuditRecord dataclass does not. Cross-retry tracing needs timestamp join.

6. **Resource saturation blindness** —
   No per-worker FD/CPU/memory monitoring. A runaway worker would degrade all
   sessions silently. Speculative — not logged pending verification.

7. **Poison pill request payloads** —
   Gemini concern: malformed payload causes crash → reconcile marks it stuck →
   next worker processes same payload → crash loop. This is a compound failure
   linking #254 (broad-except narrowing) with #257 (reconcile false-positives).
   Not separately logged; tracked via #257.

### Claims that did NOT survive verification

**CLAIM — "Thundering herd on retry (HIGH)"** (Gemini)
*Verification:* `_multi_review_serial_retry` does ONE retry per failed provider,
not infinite. The chat_completions adapter's `retry_http` has HTTP-level
backoff. Concern is MILD not HIGH. **Not logged.**

**CLAIM — "Insecure credential storage (HIGH)"** (Gemini)
*Verification:* `auth.py` has `KeychainBackend` (macOS Keychain),
`OnePasswordBackend`, `EnvBackend`. `_KEY_CACHE` is in-memory only. Mark's
system uses secure backends. **Not a vulnerability. Not logged.**

**CLAIM — "Cross-session state leakage (MEDIUM)"** (Grok)
*Verification:* Python multiprocessing uses `spawn` on macOS by default
(separate memory). No evidence of shared globals. Speculative. **Not logged.**

## Findings logged during Phase D

| # | Severity | Category | Description |
|---|---|---|---|
| #258 | medium | observability | `mcp_dispatch.py:933` hardcoded `[:2000]` truncates multi_review (partial closure of #247) |
| #259 | low | observability | AuditRecord missing request_id — cross-retry tracing requires log join |

## Findings validated but already logged

| # | Severity | Category | Status |
|---|---|---|---|
| #257 | high | reliability | AuditTrail auto_reconcile race — confirmed HIGH by both reviewers |
| #254 | low | code_quality | 11 MCP cyclic imports — still present |
| #255 | medium | test_quality | `test_review_real_gemini` wrong key assertion |
| #256 | medium | observability | CLI returns `status=done` when all providers failed |

## Full review outputs

- `rondo/reports/phase-d-review-full-2026-04-08.json` — raw JSON with both provider outputs
- `rondo/reports/phase-d-review-2026-04-08.json` — original truncated call (kept as evidence for #258)

## Phase D verdict

External validation **passed**: the AI review surfaced 1 new medium finding
(#258), 1 new low finding (#259), and independently validated #257 as HIGH.
No SEVERE gaps were identified that weren't already on the backlog. The
Rondo hardening work in RONDO-204..209 is mostly solid, with #257 being the
primary remaining reliability concern.
