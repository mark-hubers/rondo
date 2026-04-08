# Rondo Finding Traceability Audit

**Generated:** 2026-04-08 16:28 UTC
**Range:** #200..#260
**Run tests:** yes
**Findings audited:** 54

## Summary

| Verdict | Count |
|---|---|
| PASS | 6 |
| SKIP_LEGACY | 25 |
| SKIP_OPEN | 5 |

## Per-Finding Results

### #201 — SKIP_LEGACY — medium

**Sprint:** RONDO-prior

**Description:** PAT found: sanitize_task_result does not redact sk-prefixed API key patterns (sk-1234567890abcdef...

**Notes:**
- fix_sprint='RONDO-prior' — predates per-sprint tracking

### #202 — SKIP_LEGACY — medium

**Sprint:** RONDO-prior

**Description:** PAT found: Grok API dispatch returns error. Cloud test test_grok_responds fails. Either API key expi

**Notes:**
- fix_sprint='RONDO-prior' — predates per-sprint tracking

### #203 — SKIP_LEGACY — critical

**Sprint:** RONDO-prior

**Description:** P0: Always-on pipeline bypassed. _dispatch_via_provider_or_claude has 3 branches that skip _finalize

**Notes:**
- fix_sprint='RONDO-prior' — predates per-sprint tracking

### #204 — SKIP_LEGACY — critical

**Sprint:** RONDO-prior

**Description:** P0: Secret leakage via audit ordering. dispatch._finalize_dispatch calls audit_trail.record_outcome(

**Notes:**
- fix_sprint='RONDO-prior' — predates per-sprint tracking

### #205 — SKIP_LEGACY — critical

**Sprint:** RONDO-prior

**Description:** P0: Budget cap (max_budget_usd) only enforced on subprocess path via --max-budget-usd flag. HTTP ada

**Notes:**
- fix_sprint='RONDO-prior' — predates per-sprint tracking

### #206 — WARN_TEST_MOVED — high

**Sprint:** RONDO-205

**Description:** P1: Subprocess remains a footgun. In-session subprocess deadness documented but path still exists as

**Commits:**
- `a9486c0b` — RONDO-206: P3 final cluster + OB CLI finding-update bugfix + backfill
- `1e03255d` — RONDO-143: Sanitize patterns (#208) + subprocess footgun guard (#206)

**Test files modified:**
- `rondo/tests/pat/test_real_dispatch.py`
- `rondo/tests/test_real_dispatch.py`
- `rondo/tests/unit/test_dispatch.py`
- `rondo/tests/unit/test_mcp.py`

**Test run results:**
- [FAIL] `rondo/tests/pat/test_real_dispatch.py` — SKIP (missing): file no longer at this path and basename lookup missing
- [FAIL] `rondo/tests/test_real_dispatch.py` — SKIP (missing): file no longer at this path and basename lookup missing
- [PASS] `rondo/tests/unit/test_dispatch.py` — 203 passed in 4.32s
- [FAIL] `rondo/tests/unit/test_mcp.py` — SKIP (missing): file no longer at this path and basename lookup missing

**Notes:**
- Test file(s) missing — moved or deleted since commit; tests that could run all passed

### #207 — SKIP_LEGACY — high

**Sprint:** RONDO-prior

**Description:** P1: Plan schema not forward-safe. Plans return engine/kind/status/prompt/done_when/model/project/rea

**Notes:**
- fix_sprint='RONDO-prior' — predates per-sprint tracking

### #208 — SKIP_LEGACY — high

**Sprint:** RONDO-prior

**Description:** P1: Sanitize patterns materially incomplete. Missing: GitHub (ghp_/gho_/ghs_/ghu_/github_pat_), Slac

**Notes:**
- fix_sprint='RONDO-prior' — predates per-sprint tracking

### #209 — SKIP_LEGACY — critical

**Sprint:** RONDO-prior

**Description:** P0: _KEY_CACHE in adapters/auth.py has cross-request credential bleed. Cache keyed only by provider,

**Notes:**
- fix_sprint='RONDO-prior' — predates per-sprint tracking

### #210 — SKIP_LEGACY — high

**Sprint:** RONDO-prior

**Description:** Atomic writes missing for audit/spool. JSONL writes use direct write_text without temp+rename patter

**Notes:**
- fix_sprint='RONDO-prior' — predates per-sprint tracking

### #211 — SKIP_LEGACY — high

**Sprint:** RONDO-prior

**Description:** No HTTP retry/backoff/circuit breaker. chat_completions.py, gemini.py, anthropic_api.py, ollama.py h

**Notes:**
- fix_sprint='RONDO-prior' — predates per-sprint tracking

### #212 — SKIP_LEGACY — high

**Sprint:** RONDO-prior

**Description:** No audit log rotation. ~/.rondo/audit/rondo_audit.jsonl grows forever. No retention/rotation/disk mo

**Notes:**
- fix_sprint='RONDO-prior' — predates per-sprint tracking

### #213 — SKIP_LEGACY — high

**Sprint:** RONDO-prior

**Description:** Recovery semantics missing. Crash mid-dispatch leaves: (1) orphaned spool files, (2) stuck INTENT re

**Notes:**
- fix_sprint='RONDO-prior' — predates per-sprint tracking

### #214 — SKIP_LEGACY — high

**Sprint:** RONDO-prior

**Description:** No idempotency keys. Retries (rondo_retry or accidental) cause duplicate LLM API calls = duplicate c

**Notes:**
- fix_sprint='RONDO-prior' — predates per-sprint tracking

### #215 — SKIP_LEGACY — high

**Sprint:** RONDO-prior

**Description:** No structured logging with request_id / correlation_id. Cannot trace a single dispatch through mcp_d

**Notes:**
- fix_sprint='RONDO-prior' — predates per-sprint tracking

### #216 — WARN_TEST_MOVED — medium

**Sprint:** RONDO-206

**Description:** 1M context era unprepared. Static byte caps not tied to per-model context limits. 700K+ token prompt

**Commits:**
- `a9486c0b` — RONDO-206: P3 final cluster + OB CLI finding-update bugfix + backfill
- `bbb4fad1` — RONDO-200: Final P1/P2 cluster — multi-tenant + 1M context + config reload + multi-hop fallback

**Test files modified:**
- `rondo/tests/pat/test_real_dispatch.py`
- `rondo/tests/test_real_dispatch.py`
- `rondo/tests/unit/test_dispatch.py`
- `rondo/tests/unit/test_mcp.py`

**Test run results:**
- [FAIL] `rondo/tests/pat/test_real_dispatch.py` — SKIP (missing): file no longer at this path and basename lookup missing
- [FAIL] `rondo/tests/test_real_dispatch.py` — SKIP (missing): file no longer at this path and basename lookup missing
- [PASS] `rondo/tests/unit/test_dispatch.py` — 203 passed in 3.49s
- [FAIL] `rondo/tests/unit/test_mcp.py` — SKIP (missing): file no longer at this path and basename lookup missing

**Notes:**
- Test file(s) missing — moved or deleted since commit; tests that could run all passed

### #217 — SKIP_LEGACY — high

**Sprint:** RONDO-prior

**Description:** Multi-tenant safety: ~/.rondo/ shared paths leak across tenants. audit/spool/keys all in shared dirs

**Notes:**
- fix_sprint='RONDO-prior' — predates per-sprint tracking

### #218 — SKIP_LEGACY — medium

**Sprint:** RONDO-prior

**Description:** Config drift: RondoConfig frozen at startup. Mid-session config.toml changes have no effect. No hot 

**Notes:**
- fix_sprint='RONDO-prior' — predates per-sprint tracking

### #219 — SKIP_LEGACY — medium

**Sprint:** RONDO-prior

**Description:** Provider fallback chain is single-hop only. get_provider_with_fallback: primary down -> single fallb

**Notes:**
- fix_sprint='RONDO-prior' — predates per-sprint tracking

### #220 — WARN_TEST_MOVED — medium

**Sprint:** RONDO-206

**Description:** resolve_dispatch_engine routing combinations under-tested: :new precedence vs provider-prefixed (gem

**Commits:**
- `a9486c0b` — RONDO-206: P3 final cluster + OB CLI finding-update bugfix + backfill
- `361545ff` — RONDO-146: Plan schema versioning (#207) + routing test gaps (#220)

**Test files modified:**
- `rondo/tests/pat/test_real_dispatch.py`
- `rondo/tests/test_real_dispatch.py`
- `rondo/tests/unit/test_dispatch.py`
- `rondo/tests/unit/test_mcp.py`

**Test run results:**
- [FAIL] `rondo/tests/pat/test_real_dispatch.py` — SKIP (missing): file no longer at this path and basename lookup missing
- [FAIL] `rondo/tests/test_real_dispatch.py` — SKIP (missing): file no longer at this path and basename lookup missing
- [PASS] `rondo/tests/unit/test_dispatch.py` — 203 passed in 4.08s
- [FAIL] `rondo/tests/unit/test_mcp.py` — SKIP (missing): file no longer at this path and basename lookup missing

**Notes:**
- Test file(s) missing — moved or deleted since commit; tests that could run all passed

### #221 — SKIP_LEGACY — critical

**Sprint:** RONDO-prior

**Description:** P0: Budget cap is NO-OP in real HTTP dispatch. ChatCompletionsAdapter returns cost_usd=0.0 on succes

**Notes:**
- fix_sprint='RONDO-prior' — predates per-sprint tracking

### #222 — SKIP_LEGACY — critical

**Sprint:** RONDO-prior

**Description:** P0: INTENT sanitize gap. record_intent writes prompt_file to disk via sanitize_text BUT new finalize

**Notes:**
- fix_sprint='RONDO-prior' — predates per-sprint tracking

### #223 — WARN_TEST_MOVED — high

**Sprint:** RONDO-204

**Description:** P0: _run_pipeline defensive return leaks unsanitized tr. When finalize raises, we return the pre-san

**Commits:**
- `6d292544` — RONDO-202: Fix all 8 P0 findings + master integration tests

**Test files modified:**
- `rondo/tests/test_conventions.py`
- `rondo/tests/test_integration_flow.py`
- `rondo/tests/test_real_dispatch.py`

**Test run results:**
- [PASS] `rondo/tests/test_conventions.py -> rondo/tests/conventions/test_conventions.py` — 31 passed in 0.66s
- [PASS] `rondo/tests/test_integration_flow.py -> rondo/tests/integration/test_integration_flow.py` — 11 passed in 0.11s
- [FAIL] `rondo/tests/test_real_dispatch.py` — SKIP (missing): file no longer at this path and basename lookup missing

**Notes:**
- Test file(s) missing — moved or deleted since commit; tests that could run all passed

### #224 — SKIP_LEGACY — critical

**Sprint:** RONDO-prior

**Description:** P0: Spool dir NOT tenant-isolated. Finding #217 only fixed audit dir. Spool files (intermediate resu

**Notes:**
- fix_sprint='RONDO-prior' — predates per-sprint tracking

### #225 — SKIP_LEGACY — critical

**Sprint:** RONDO-prior

**Description:** P0: Config hot reload has no lock. Mid-flight dispatches see partial/inconsistent config during relo

**Notes:**
- fix_sprint='RONDO-prior' — predates per-sprint tracking

### #226 — SKIP_LEGACY — critical

**Sprint:** RONDO-prior

**Description:** P0: Budget cap is reactive not predictive, not thread-safe, not tenant-scoped. (1) Check is running_

**Notes:**
- fix_sprint='RONDO-prior' — predates per-sprint tracking

### #227 — SKIP_LEGACY — critical

**Sprint:** RONDO-prior

**Description:** P0: Three modules built but NOT wired (dead code). check_context_limit, idempotency, structured_log 

**Notes:**
- fix_sprint='RONDO-prior' — predates per-sprint tracking

### #228 — SKIP_LEGACY — critical

**Sprint:** RONDO-prior

**Description:** P0: NO integration tests. Every fix has isolated unit tests. Nothing tests all fixes together in one

**Notes:**
- fix_sprint='RONDO-prior' — predates per-sprint tracking

### #229 — WARN_TEST_MOVED — high

**Sprint:** RONDO-204

**Description:** P1: Archive directory grows forever. rotate() archives to archive/YYYY-MM.jsonl with no retention po

**Commits:**
- `00bf38dd` — RONDO-204: P1 reliability cluster + retry.py architecture promotion

**Test files modified:**
- `rondo/tests/conventions/test_conventions.py`
- `rondo/tests/pat/test_real_dispatch.py`

**Test run results:**
- [PASS] `rondo/tests/conventions/test_conventions.py` — 31 passed in 0.69s
- [FAIL] `rondo/tests/pat/test_real_dispatch.py` — SKIP (missing): file no longer at this path and basename lookup missing

**Notes:**
- Test file(s) missing — moved or deleted since commit; tests that could run all passed

### #230 — WARN_TEST_MOVED — high

**Sprint:** RONDO-204

**Description:** P1: Audit archives NOT tenant-isolated. archive/YYYY-MM.jsonl is global, mixes tenants' historical l

**Commits:**
- `00bf38dd` — RONDO-204: P1 reliability cluster + retry.py architecture promotion

**Test files modified:**
- `rondo/tests/conventions/test_conventions.py`
- `rondo/tests/pat/test_real_dispatch.py`

**Test run results:**
- [PASS] `rondo/tests/conventions/test_conventions.py` — 31 passed in 0.66s
- [FAIL] `rondo/tests/pat/test_real_dispatch.py` — SKIP (missing): file no longer at this path and basename lookup missing

**Notes:**
- Test file(s) missing — moved or deleted since commit; tests that could run all passed

### #231 — WARN_TEST_MOVED — high

**Sprint:** RONDO-204

**Description:** P1: Audit log rotation not locked. Two threads could call rotate() simultaneously — lost or corrupte

**Commits:**
- `00bf38dd` — RONDO-204: P1 reliability cluster + retry.py architecture promotion

**Test files modified:**
- `rondo/tests/conventions/test_conventions.py`
- `rondo/tests/pat/test_real_dispatch.py`

**Test run results:**
- [PASS] `rondo/tests/conventions/test_conventions.py` — 31 passed in 0.66s
- [FAIL] `rondo/tests/pat/test_real_dispatch.py` — SKIP (missing): file no longer at this path and basename lookup missing

**Notes:**
- Test file(s) missing — moved or deleted since commit; tests that could run all passed

### #232 — WARN_TEST_MOVED — high

**Sprint:** RONDO-204

**Description:** P1: reconcile_stuck_intents manual-only. In production, stuck records accumulate without automatic r

**Commits:**
- `00bf38dd` — RONDO-204: P1 reliability cluster + retry.py architecture promotion

**Test files modified:**
- `rondo/tests/conventions/test_conventions.py`
- `rondo/tests/pat/test_real_dispatch.py`

**Test run results:**
- [PASS] `rondo/tests/conventions/test_conventions.py` — 31 passed in 0.64s
- [FAIL] `rondo/tests/pat/test_real_dispatch.py` — SKIP (missing): file no longer at this path and basename lookup missing

**Notes:**
- Test file(s) missing — moved or deleted since commit; tests that could run all passed

### #233 — WARN_TEST_MOVED — high

**Sprint:** RONDO-204

**Description:** P1: Key invalidation not global. invalidate_key only clears caller's tenant. Revoked key stays in OT

**Commits:**
- `00bf38dd` — RONDO-204: P1 reliability cluster + retry.py architecture promotion

**Test files modified:**
- `rondo/tests/conventions/test_conventions.py`
- `rondo/tests/pat/test_real_dispatch.py`

**Test run results:**
- [PASS] `rondo/tests/conventions/test_conventions.py` — 31 passed in 0.64s
- [FAIL] `rondo/tests/pat/test_real_dispatch.py` — SKIP (missing): file no longer at this path and basename lookup missing

**Notes:**
- Test file(s) missing — moved or deleted since commit; tests that could run all passed

### #234 — WARN_TEST_MOVED — high

**Sprint:** RONDO-204

**Description:** P1: HTTP retry/breaker only wired into ChatCompletionsAdapter. Gemini + Anthropic adapters have no r

**Commits:**
- `00bf38dd` — RONDO-204: P1 reliability cluster + retry.py architecture promotion

**Test files modified:**
- `rondo/tests/conventions/test_conventions.py`
- `rondo/tests/pat/test_real_dispatch.py`

**Test run results:**
- [PASS] `rondo/tests/conventions/test_conventions.py` — 31 passed in 0.63s
- [FAIL] `rondo/tests/pat/test_real_dispatch.py` — SKIP (missing): file no longer at this path and basename lookup missing

**Notes:**
- Test file(s) missing — moved or deleted since commit; tests that could run all passed

### #235 — WARN_TEST_MOVED — high

**Sprint:** RONDO-204

**Description:** P1: Claude path parity — dispatch_task uses own audit_trail/tenant/config path, not the same as MCP 

**Commits:**
- `00bf38dd` — RONDO-204: P1 reliability cluster + retry.py architecture promotion

**Test files modified:**
- `rondo/tests/conventions/test_conventions.py`
- `rondo/tests/pat/test_real_dispatch.py`

**Test run results:**
- [PASS] `rondo/tests/conventions/test_conventions.py` — 31 passed in 0.64s
- [FAIL] `rondo/tests/pat/test_real_dispatch.py` — SKIP (missing): file no longer at this path and basename lookup missing

**Notes:**
- Test file(s) missing — moved or deleted since commit; tests that could run all passed

### #236 — WARN_TEST_MOVED — medium

**Sprint:** RONDO-205

**Description:** P2: Circuit breaker state in-memory only. Lost on restart. Multi-process deployments each have own s

**Commits:**
- `51f2b375` — RONDO-205: P2 reliability cluster + STD-107 stateless compliance

**Test files modified:**
- `rondo/tests/conventions/test_conventions.py`
- `rondo/tests/pat/test_real_dispatch.py`
- `rondo/tests/unit/test_health.py`
- `rondo/tests/unit/test_sanitize.py`

**Test run results:**
- [PASS] `rondo/tests/conventions/test_conventions.py` — 31 passed in 0.68s
- [FAIL] `rondo/tests/pat/test_real_dispatch.py` — SKIP (missing): file no longer at this path and basename lookup missing
- [PASS] `rondo/tests/unit/test_health.py` — 24 passed in 0.08s
- [PASS] `rondo/tests/unit/test_sanitize.py` — 46 passed in 0.09s

**Notes:**
- Test file(s) missing — moved or deleted since commit; tests that could run all passed

### #237 — WARN_TEST_MOVED — medium

**Sprint:** RONDO-205

**Description:** P2: Footgun guard too narrow. Only blocks auth=max + Claude + CLAUDECODE. auth=api + in-session subp

**Commits:**
- `a9486c0b` — RONDO-206: P3 final cluster + OB CLI finding-update bugfix + backfill
- `51f2b375` — RONDO-205: P2 reliability cluster + STD-107 stateless compliance

**Test files modified:**
- `rondo/tests/conventions/test_conventions.py`
- `rondo/tests/pat/test_real_dispatch.py`
- `rondo/tests/unit/test_dispatch.py`
- `rondo/tests/unit/test_health.py`
- `rondo/tests/unit/test_mcp.py`
- `rondo/tests/unit/test_sanitize.py`

**Test run results:**
- [PASS] `rondo/tests/conventions/test_conventions.py` — 31 passed in 0.64s
- [FAIL] `rondo/tests/pat/test_real_dispatch.py` — SKIP (missing): file no longer at this path and basename lookup missing
- [PASS] `rondo/tests/unit/test_dispatch.py` — 203 passed in 3.90s
- [PASS] `rondo/tests/unit/test_health.py` — 24 passed in 0.08s
- [FAIL] `rondo/tests/unit/test_mcp.py` — SKIP (missing): file no longer at this path and basename lookup missing
- [PASS] `rondo/tests/unit/test_sanitize.py` — 46 passed in 0.09s

**Notes:**
- Test file(s) missing — moved or deleted since commit; tests that could run all passed

### #238 — WARN_TEST_MOVED — medium

**Sprint:** RONDO-205

**Description:** P2: Token estimate wrong for non-English. estimate_token_count = chars/4 (English ratio). Japanese/C

**Commits:**
- `51f2b375` — RONDO-205: P2 reliability cluster + STD-107 stateless compliance

**Test files modified:**
- `rondo/tests/conventions/test_conventions.py`
- `rondo/tests/pat/test_real_dispatch.py`
- `rondo/tests/unit/test_health.py`
- `rondo/tests/unit/test_sanitize.py`

**Test run results:**
- [PASS] `rondo/tests/conventions/test_conventions.py` — 31 passed in 0.67s
- [FAIL] `rondo/tests/pat/test_real_dispatch.py` — SKIP (missing): file no longer at this path and basename lookup missing
- [PASS] `rondo/tests/unit/test_health.py` — 24 passed in 0.08s
- [PASS] `rondo/tests/unit/test_sanitize.py` — 46 passed in 0.09s

**Notes:**
- Test file(s) missing — moved or deleted since commit; tests that could run all passed

### #239 — WARN_TEST_MOVED — medium

**Sprint:** RONDO-205

**Description:** P2: Sanitize patterns have no false-positive tests. Legit base64 output or sk-prefixed non-secrets c

**Commits:**
- `51f2b375` — RONDO-205: P2 reliability cluster + STD-107 stateless compliance

**Test files modified:**
- `rondo/tests/conventions/test_conventions.py`
- `rondo/tests/pat/test_real_dispatch.py`
- `rondo/tests/unit/test_health.py`
- `rondo/tests/unit/test_sanitize.py`

**Test run results:**
- [PASS] `rondo/tests/conventions/test_conventions.py` — 31 passed in 0.69s
- [FAIL] `rondo/tests/pat/test_real_dispatch.py` — SKIP (missing): file no longer at this path and basename lookup missing
- [PASS] `rondo/tests/unit/test_health.py` — 24 passed in 0.09s
- [PASS] `rondo/tests/unit/test_sanitize.py` — 46 passed in 0.10s

**Notes:**
- Test file(s) missing — moved or deleted since commit; tests that could run all passed

### #240 — WARN_TEST_MOVED — medium

**Sprint:** RONDO-205

**Description:** P2: Multi-hop fallback does full health check per hop. Chain of 3 providers with slow health checks 

**Commits:**
- `51f2b375` — RONDO-205: P2 reliability cluster + STD-107 stateless compliance

**Test files modified:**
- `rondo/tests/conventions/test_conventions.py`
- `rondo/tests/pat/test_real_dispatch.py`
- `rondo/tests/unit/test_health.py`
- `rondo/tests/unit/test_sanitize.py`

**Test run results:**
- [PASS] `rondo/tests/conventions/test_conventions.py` — 31 passed in 0.70s
- [FAIL] `rondo/tests/pat/test_real_dispatch.py` — SKIP (missing): file no longer at this path and basename lookup missing
- [PASS] `rondo/tests/unit/test_health.py` — 24 passed in 0.08s
- [PASS] `rondo/tests/unit/test_sanitize.py` — 46 passed in 0.09s

**Notes:**
- Test file(s) missing — moved or deleted since commit; tests that could run all passed

### #241 — WARN_TEST_MOVED — medium

**Sprint:** RONDO-205

**Description:** P2: Idempotency cache in-process only. Multi-process or distributed deployments still dispatch dupli

**Commits:**
- `51f2b375` — RONDO-205: P2 reliability cluster + STD-107 stateless compliance

**Test files modified:**
- `rondo/tests/conventions/test_conventions.py`
- `rondo/tests/pat/test_real_dispatch.py`
- `rondo/tests/unit/test_health.py`
- `rondo/tests/unit/test_sanitize.py`

**Test run results:**
- [PASS] `rondo/tests/conventions/test_conventions.py` — 31 passed in 0.65s
- [FAIL] `rondo/tests/pat/test_real_dispatch.py` — SKIP (missing): file no longer at this path and basename lookup missing
- [PASS] `rondo/tests/unit/test_health.py` — 24 passed in 0.08s
- [PASS] `rondo/tests/unit/test_sanitize.py` — 46 passed in 0.08s

**Notes:**
- Test file(s) missing — moved or deleted since commit; tests that could run all passed

### #242 — WARN_TEST_MOVED — medium

**Sprint:** RONDO-205

**Description:** P2: Structured logging not wired into existing components. New module sits unused while existing cod

**Commits:**
- `51f2b375` — RONDO-205: P2 reliability cluster + STD-107 stateless compliance

**Test files modified:**
- `rondo/tests/conventions/test_conventions.py`
- `rondo/tests/pat/test_real_dispatch.py`
- `rondo/tests/unit/test_health.py`
- `rondo/tests/unit/test_sanitize.py`

**Test run results:**
- [PASS] `rondo/tests/conventions/test_conventions.py` — 31 passed in 0.69s
- [FAIL] `rondo/tests/pat/test_real_dispatch.py` — SKIP (missing): file no longer at this path and basename lookup missing
- [PASS] `rondo/tests/unit/test_health.py` — 24 passed in 0.08s
- [PASS] `rondo/tests/unit/test_sanitize.py` — 46 passed in 0.10s

**Notes:**
- Test file(s) missing — moved or deleted since commit; tests that could run all passed

### #243 — SKIP_LEGACY — high

**Sprint:** RONDO-prior

**Description:** P1: Test folder is flat — no layered structure. 32+ files in rondo/tests/ mixing unit/integration/e2

**Notes:**
- fix_sprint='RONDO-prior' — predates per-sprint tracking

### #244 — SKIP_OPEN — medium

**Sprint:** —

**Description:** P3: #216 follow-up — sanitize.py regex performance bottleneck for 1M+ token outputs, audit/spool I/O

**Notes:**
- Finding still open — nothing to verify

### #245 — SKIP_OPEN — medium

**Sprint:** —

**Description:** P2: ace-build pylint runs on wrong directory. Line 250 of ~/bin/ace-build runs 'pylint src/ace2/' re

**Notes:**
- Finding still open — nothing to verify

### #246 — PASS — high

**Sprint:** RONDO-209

**Description:** P2: JSON file persistence has cross-process race condition. Both idempotency.py::cache_result and re

**Commits:**
- `aa1d08ed` — RONDO-209: fix #246 (JSON race) + #247 (truncation) + multi-process tests

**Test files modified:**
- `rondo/tests/integration/test_integration_multiprocess.py`
- `rondo/tests/pat/test_pipeline_observability.py`

**Test run results:**
- [PASS] `rondo/tests/integration/test_integration_multiprocess.py` — 9 passed in 0.68s
- [PASS] `rondo/tests/pat/test_pipeline_observability.py` — 30 passed in 0.13s

**Notes:**
- All 2 test file(s) still passing

### #247 — PASS — medium

**Sprint:** RONDO-209

**Description:** P3: rondo_multi_review truncates deep-review responses mid-sentence. Max_tokens default too small fo

**Commits:**
- `aa1d08ed` — RONDO-209: fix #246 (JSON race) + #247 (truncation) + multi-process tests

**Test files modified:**
- `rondo/tests/integration/test_integration_multiprocess.py`
- `rondo/tests/pat/test_pipeline_observability.py`

**Test run results:**
- [PASS] `rondo/tests/integration/test_integration_multiprocess.py` — 9 passed in 0.69s
- [PASS] `rondo/tests/pat/test_pipeline_observability.py` — 30 passed in 0.13s

**Notes:**
- All 2 test file(s) still passing

### #248 — PASS — medium

**Sprint:** RONDO-209

**Description:** P3: anthropic:sonnet adapter returns partial/empty in rondo_multi_review. Duration 0.46s suggests re

**Commits:**
- `fb0aaff9` — RONDO-209: fix #248/#250 multi_review observability + serial retry

**Test files modified:**
- `rondo/tests/unit/test_mcp_parallel_multi.py`

**Test run results:**
- [PASS] `rondo/tests/unit/test_mcp_parallel_multi.py` — 27 passed in 0.49s

**Notes:**
- All 1 test file(s) still passing

### #249 — SKIP_OPEN — low

**Sprint:** —

**Description:** P4: sanitize.py has no Unicode NFKC normalization — homoglyph bypass theoretically possible. Cyrilli

**Notes:**
- Finding still open — nothing to verify

### #250 — PASS — medium

**Sprint:** RONDO-209

**Description:** P3: rondo_multi_review has intermittent provider failures. Second review call in same session had Ge

**Commits:**
- `fb0aaff9` — RONDO-209: fix #248/#250 multi_review observability + serial retry

**Test files modified:**
- `rondo/tests/unit/test_mcp_parallel_multi.py`

**Test run results:**
- [PASS] `rondo/tests/unit/test_mcp_parallel_multi.py` — 27 passed in 0.58s

**Notes:**
- All 1 test file(s) still passing

### #251 — PASS — high

**Sprint:** RONDO-209

**Description:** P2: audit.py::rotate() cross-process race. The _rotate_lock is threading.Lock (thread-scoped only). 

**Commits:**
- `5601d70e` — RONDO-209: fix #251 audit rotation cross-process race + multi-process rotation test

**Test files modified:**
- `rondo/tests/integration/test_integration_multiprocess.py`

**Test run results:**
- [PASS] `rondo/tests/integration/test_integration_multiprocess.py` — 9 passed in 0.69s

**Notes:**
- All 1 test file(s) still passing

### #252 — PASS — medium

**Sprint:** RONDO-209

**Description:** P3: No multi-process crash recovery tests. reconcile_stuck_intents() handles orphan INTENTs but no i

**Commits:**
- `d462621f` — RONDO-209: fix #252 — multi-process crash recovery test

**Test files modified:**
- `rondo/tests/integration/test_integration_multiprocess.py`

**Test run results:**
- [PASS] `rondo/tests/integration/test_integration_multiprocess.py` — 9 passed in 0.66s

**Notes:**
- All 1 test file(s) still passing

### #253 — SKIP_OPEN — low

**Sprint:** —

**Description:** P4: MCP server caches Rondo code at startup — code changes require Claude Code restart to take effec

**Notes:**
- Finding still open — nothing to verify

### #254 — SKIP_OPEN — low

**Sprint:** —

**Description:** RONDO-209 commit 69b7ae79 claimed 'break mcp family cyclic imports' but 11 cycles remain in rondo/sr

**Notes:**
- Finding still open — nothing to verify

