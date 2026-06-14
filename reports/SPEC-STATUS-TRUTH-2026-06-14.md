# Spec Status Truth Map — 2026-06-14 (RONDO-429)

**Why:** the spec `Status:` fields are stale — many say `DESIGNED` while the code,
CLI command, and tests exist. That made it look like ~45 specs were unfinished.
This map is the GROUND TRUTH (verified against modules / CLI subcommands / tests),
not the status field. Method = same spec→code→test check as the RONDO-421→427
self-audit. Evidence column = run it yourself.

Legend: ✅ BUILT · ◑ PARTIAL · ❌ NOT BUILT · 📏 STANDARD/PROCESS (rules, not a
feature to code) · ☠️ DEAD (archived/superseded/proposal).

## Feature specs (REQ / IFS)

| Spec | True status | Evidence |
|------|-------------|----------|
| REQ-100 core dispatch | ✅ BUILT | `dispatch.py`, `engine.py`, `rondo run`; 2798 tests |
| REQ-101 automation | ✅ BUILT | `schedule.py`, `overnight.py`, `rondo schedule/overnight` |
| REQ-103 dispatch-preflight | ✅ BUILT | `preflight.py`, `rondo preflight` |
| REQ-104 dispatch-history | ✅ BUILT | `history.py`, `rondo history` |
| REQ-105 dispatch-notifications | ✅ BUILT | `notify.py` |
| REQ-106 trend-alerting | ✅ BUILT | `nightly.run_nightly_check(notify_alerts=)`, `metrics._compute_trend` |
| REQ-107 task-flakiness | ✅ BUILT | `flaky.py`, `rondo flaky` |
| REQ-108 template-promotion | ◑ PARTIAL | `rondo_templates()` lists templates; AUTO-promotion of a winning round not evident |
| REQ-109 provider-adapters | ✅ BUILT | `providers.py`, `provider_base.py`, `rondo providers` |
| REQ-110 multi-account | ❌ NOT BUILT | no `multi_account` / accounts code |
| REQ-111 smart-dispatch | ✅ BUILT | `dispatch_routing.py`, `scoring.py`, `rondo learn` |
| REQ-112 error-envelope | ✅ BUILT | `envelope.py`; 70 tests (audited RONDO-427) |
| REQ-113 experiment-matrix | ✅ BUILT | `matrix.py`, `rondo matrix` |
| REQ-114 prompt-pipelines | ✅ BUILT | `pipeline.py`, `rondo pipeline`; mutation 149/160 (audited) |
| REQ-114 structured-input | ◑ PARTIAL | `json_schema=` exists for claude path; HTTP path partial (audited RONDO-418) |
| REQ-115 verified-execution | ✅ BUILT | `verify.py`; req-002 tamper test added (audited RONDO-421) |
| REQ-116 scope-guard | ✅ BUILT | `scope.py`; req-013 test added (audited RONDO-424) |
| REQ-117 signed-receipts | ❌ NOT BUILT | DRAFT for hostile review; honestly labeled |
| IFS-100 claude-cli | ✅ BUILT | `dispatch.py` claude subprocess path |
| IFS-101 caliber-integration | ✅ BUILT | Caliber hooks active (PreToolUse/PostToolUse fire this session) |
| IFS-102 ob-integration | ❌ NOT BUILT | no `oaresult`/ob-connect in standalone; cross-product, arguably out of scope |
| IFS-103 token-signing | ☠️ SUPERSEDED | → REQ-117 |
| IFS-104 mcp-server | ✅ BUILT | `mcp_server.py`, 26 MCP tools (STUB status stale) |

## Honesty machinery (STD) — audited

| Spec | True status | Evidence |
|------|-------------|----------|
| STD-113 dispatch-audit-trail | ✅ BUILT | `audit.py`; 112 tests; req-011 marked PARTIAL (audited RONDO-423) |
| STD-114 output-sanitization | ✅ BUILT (013-015 ❌) | `sanitize.py`; 85 tests; allow-CLI not built, marked (audited RONDO-422) |
| STD-115 result-quarantine | ❌ NOT BUILT | trust-lifecycle absent; NOT-BUILT banner added (RONDO-427) |
| STD-110 concurrency-safety | ✅ BUILT | flock in `audit.py`/`spool.py`; reconcile tests |
| STD-108 error-resilience | ✅ BUILT | `retry.py`, `retry_queue.py`, `runner.py` |
| STD-109 configuration | ✅ BUILT | `config.py` |
| STD-101 observability | ✅ BUILT | `structured_log.py` |
| STD-116 oscillation-detection | ❌ NOT BUILT | no `oscillat*` code — candidate to build (thesis-aligned) |
| STD-117 prompt-protection | ❌ NOT BUILT | "injection" in code = prompt CONSTRUCTION, not injection DEFENSE |

## Standards / process docs (📏 — rules, not features)

STD-100 data, STD-103 quality, STD-104 infra, STD-105 ai-ops, STD-106 spec-quality,
STD-107 security, STD-111 code-quality, STD-112 golden-numbers, STD-100 data —
these are RULES. Many are ENFORCED already: STD-103/111 by the conventions locks +
`bin/build`; STD-107 partly by sanitize/audit/perms; STD-112 by the golden-numbers
lock. SOP-100..106 (onboarding/build/release/incident/migration/public-release/
road-to-8.5) + VER-100 (verification map) are PROCESS docs, not code. STD-102 ☠️ ARCHIVED.

## The honest tally

- **✅ BUILT:** ~22 feature/honesty specs (code + CLI + tests) — status field was just stale.
- **◑ PARTIAL:** ~3 (REQ-108 templates, REQ-114 structured-input).
- **❌ NOT BUILT:** ~6 (REQ-110 multi-account, REQ-117 receipts, IFS-102 ob, STD-115
  quarantine, STD-116 oscillation, STD-117 prompt-protection).
- **📏 STANDARD/PROCESS:** ~18 (rules/SOPs, mostly enforced).
- **☠️ DEAD:** ~3.

**Bottom line:** there were never ~45 unfinished features. Most "DESIGNED" specs are
built; the rest are standards or honestly-not-built. The genuinely-unbuilt set is
~6, and only 1-2 (oscillation-detection, maybe prompt-protection) are thesis-aligned
enough to be worth building. The "unfinished" cloud was a status-field lie, now mapped.
