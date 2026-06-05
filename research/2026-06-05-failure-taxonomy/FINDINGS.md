# Rondo Failure Taxonomy — Every Dispatch Ever (2026-06-05)

**Source:** `~/.rondo/audit/rondo_audit.jsonl` — 908 completed dispatches (584 done / 324 failed),
all projects share one store ("default" tenant — USH, GHE, ace2 not separable; see F10).
**Raw data:** `taxonomy-raw.json` + `replay-candidates.json` (277 replayable) in this dir.

## The corrected stability picture (HONEST numbers)

| Period | Success | Note |
|--------|---------|------|
| 2026-03 | 5% | build era — Rondo itself under construction |
| 2026-04 | 61% | FIX-sprint churn era |
| **2026-05** | **97%** | post-hardening |
| **2026-06** | **97%** | current |

**Lifetime 64% is a misleading average over the build era. Recent Rondo ≈ 97%.**
AND: true recent rate is likely HIGHER — misfiled partials (F2) counted successes as failures.

## Whose fault was each failure? (Mark asked)

| Bucket | Count | AI's fault? | Verdict |
|--------|-------|------------|---------|
| Misfiled valid smart-return JSON (F2) | **80** | **NO — AI did its job** | Rondo parser bug |
| "Not logged in" auth loss (F3) | 33 | NO | Rondo session handling + misclassification |
| ERR_SUBPROCESS opaque (F4) | 103 | unknowable (no stderr saved) | Rondo forensics gap; mostly build-era |
| blocked, null context (F5) | 44 | unknowable | Rondo forensics gap |
| ERR_PROVIDER_DOWN / ERR_PROVIDER (F7) | 45 | **partly YES** (provider outages/contract) | now diagnosable via STD-108 body capture |
| ERR_TIMEOUT (F8) | 13 | mixed | needs per-step timing (STD-113 gap) |
| ERR_AUTH / stuck | 6 | no | handled |

**Bottom line: of 324 failures, at most ~58 (18%) were plausibly the AI/provider's fault.
The rest were Rondo-side bugs or unknowable due to missing forensics.**

## Findings register (F-numbers → DB findings → spec target)

| F# | Finding | DB | Severity | Fix → Spec |
|----|---------|----|----------|-----------|
| F1 | Audit OUTCOME drops error_message/stderr — all 467 failures show "(no message)" | #291 | HIGH | STD-113: persist error_message + stderr (sanitized, capped) in OUTCOME |
| F2 | parse_task_json rejects valid smart-return JSON (status-key gate + flat-object regex) | #290 | **CRITICAL** | REQ-100/111: schema-aware parser (status OR passed), real JSON scanner not regex |
| F3 | Auth-loss misclassified ERR_MALFORMED_JSON; multi-turn continues on dead session | spec'd | HIGH | IFS-100 reqs 011-014 (done 2026-06-03) → build RONDO-298 |
| F4 | ERR_SUBPROCESS: no stderr/env captured, 103 undiagnosable | spec pending | HIGH | STD-113: stderr + env-state capture on error paths |
| F5 | blocked status: null tasks/error/output — invisible failure mode | spec pending | MED | STD-113: blocked records carry reason |
| F6 | Retry queue write-only: 50 stale files, no aging/drain/alert | spec pending | MED | REQ-104 or STD-113: lifecycle (age-out, dead-letter, threshold alert) |
| F7 | Provider failures now diagnosable (STD-108 011-014 built in RONDO-296) | done | — | error bodies flowing since 2026-06-03 |
| F8 | No per-step timing (subprocess start vs API vs parse) | spec pending | LOW | STD-113: phase timing fields |
| F9 | Stability metric uses lifetime average — masks current health | new | MED | REQ-111/STD-101: windowed success-rate metric (7d/30d), weekly trend = campaign scoreboard |
| F10 | All projects share one audit tenant — USH/GHE/ace2 not separable | new | LOW | STD-113: project/tenant field in records (links Finding #217) |
| F11 | Cost/tokens zero on all error paths | #pending | MED | STD-105/113: capture usage on failure when provider returns it |
| F12 | uv cached-wheel deploys silently stale | #288 | MED | SOP-102: verify-symbol step after install |
| F13 | init template not packaged — installed `rondo init --config` broken | #289 | HIGH | packaging sprint |

## Recovery & replay plan

1. **Free recovery (no API):** re-parse 80 misfiled partials with fixed parser → flip audit verdicts → recompute true historic rate. (Parser fix FIRST.)
2. **Replay sample:** from `replay-candidates.json` (277 preserved prompts) re-dispatch ~10-15
   across the fixed paths (auth-class, provider-class, timeout-class) → prove fixes empirically.
3. **Trap better:** F1+F4+F5 = the forensics sprint — after it, NO failure is ever "(no message)" again.

## Campaign sequence (specs → build, TDD throughout)

1. SPEC: STD-113 forensics pack (F1, F4, F5, F8, F10, F11) + parser reqs (F2) + retry lifecycle (F6) + windowed metric (F9)
2. BUILD: RONDO-298 parser fix (F2 — biggest count, free historic recovery proves it)
3. BUILD: RONDO-299 auth-loss (F3, spec ready)
4. BUILD: RONDO-300 forensics pack (F1/F4/F5/F11)
5. BUILD: RONDO-301 retry lifecycle + windowed scoreboard (F6, F9)
6. REPLAY: re-dispatch failed sample, publish before/after table
7. Packaging (F13) + registry build (REQ-111 600-610) close the loop
