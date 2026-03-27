# Rondo-STD-113: Dispatch Audit Trail

*Every dispatch recorded. What was sent, what came back, what changed. Critical for overnight post-mortem.*

**Product:** Rondo
**Category:** STD
**Created:** 2026-03-20 | **Updated:** 2026-03-20 | **Status:** DESIGNED
**Classification:** open
**Version:** 1.0
**Owner:** Mark G. Hubers
**Reviewed:** not-yet
**Supersedes:** none
**Depends on:** Rondo-REQ-100 (Core), Rondo-STD-108 (Error Resilience), CORE-STD-010 (Error Resilience), Rondo-STD-114, CORE-STD-012, CORE-STD-021, CORE-STD-013, Rondo-STD-107 | **Used by:** Rondo-REQ-101 (Automation), Rondo-IFS-102 (OB Integration), Rondo-REQ-104 (Dispatch History)
**Cross-pollinated from:** OB-REQ-114 (Evidence & Audit Trail) — adapted from methodology audit to dispatch audit

---

## 1. Purpose & Scope

**What this spec does:** Every Rondo dispatch produces a permanent, tamper-evident record: what prompt was sent, what the AI returned, what files were modified, how much it cost, and how long it took. When overnight runs produce unexpected results, you can trace exactly what happened without guessing.

**IN scope:**
- Per-dispatch audit records
- Prompt preservation (what was sent to AI)
- Result preservation (what AI returned)
- File modification tracking
- Cost and timing records
- Audit log storage and retention
- Post-mortem querying

**OUT of scope:**
- Trend analysis on audit data (Rondo-REQ-106)
- OB-side audit trails (OB-REQ-114)
- Security/credential handling (CORE-STD-010 scrubbing rules apply)

**Users:** Mark (primary). Claude AI agents dispatching to other models. Future: teams needing multi-model AI orchestration, batch processing, cost optimization across AI providers.

---

<!-- convergence: allow(category_deep) reason: 3-AI consensus verified STD correct (Session 86) -->

## 2. The Problem

Overnight runs produce results but no explanation. A task failed — was the prompt wrong? Did Claude hallucinate? Was there a rate limit? Without an audit trail, debugging requires re-running the task and hoping the same failure occurs. The audit trail makes every dispatch reproducible and every failure explainable.

---

## 3. Requirements


*All requirements use MUST/SHOULD priority per CORE-STD-012.*

| ID | Requirement | Priority | Verified By |
|----|-------------|----------|-------------|
| 001 | Every dispatch produces an audit record BEFORE the subprocess launches (intent recorded) | MUST | Timing test |
| 002 | Audit record updated AFTER dispatch completes (outcome recorded) | MUST | Completion test |
| 003 | Audit record contains: dispatch_id (ULID), task_name, model, prompt_hash (SHA-256 of prompt), timestamp, duration_sec, cost_usd, status, exit_code | MUST | Schema test |
| 004 | Full prompt text stored in separate file: `audit/{dispatch_id}.prompt.txt` | MUST | Prompt test |
| 005 | Full result stored in separate file: `audit/{dispatch_id}.result.json` | MUST | Result test |
| 006 | Files modified (heuristic extraction from output) stored in audit record | SHOULD | Files test |
| 007 | Audit records stored in `rondo_audit.jsonl` (append-only, one JSON object per line) | MUST | Storage test |
| 008 | Audit files stored in `~/.rondo/audit/` or configured path | MUST | Path test |
| 009 | Credential scrubbing applied per CORE-STD-010 reqs 19-22 before writing audit files | MUST | Scrub test |
| 010 | Audit records are append-only. Never modify or delete existing records. | MUST | Immutability test |
| 011 | `rondo audit` CLI: query audit log by date range, task name, model, status | SHOULD | Query test |
| 012 | `rondo audit {dispatch_id}` CLI: show full audit record including prompt and result | SHOULD | Detail test |
| 013 | `rondo audit --cost` CLI: show total cost for date range | SHOULD | Cost test |
| 014 | Overnight runs: morning report references dispatch_ids for failed tasks so Mark can audit | MUST | Report test |
| 015 | Audit retention: keep forever by default. `audit_retention_days` config to auto-archive old files. | SHOULD | Retention test |
| 016 | When OB-connected: dispatch_ids included in OAResult for cross-product traceability | SHOULD | Integration test |


---

## 4. Architecture / Design

Two-phase audit recording: phase 1 records intent BEFORE dispatch (task name, model, prompt hash, timestamp), phase 2 updates the record AFTER dispatch completes (status, cost, duration, result reference). If the subprocess crashes, phase 1 still exists — intent is never lost. Audit records in JSONL, prompt/result files alongside.

---

## 5. Data Model

### Audit Record (JSONL)

```json
{
  "dispatch_id": "dsp_01HRJ3...",
  "task_name": "review_forward",
  "round_name": "spec_review_round",
  "model": "claude-sonnet-4-6",
  "prompt_hash": "sha256:a3f8b2c1...",
  "prompt_file": "audit/dsp_01HRJ3.prompt.txt",
  "result_file": "audit/dsp_01HRJ3.result.json",
  "status": "done",
  "exit_code": 0,
  "error_code": null,
  "cost_usd": 0.042,
  "input_tokens": 12500,
  "output_tokens": 3200,
  "duration_sec": 34.2,
  "files_modified": ["src/main.py", "tests/test_main.py"],
  "dispatched_at": "2026-03-20T03:14:00Z",
  "completed_at": "2026-03-20T03:14:34Z"
}
```

---

## 6. Data Boundary

Audit data stays local. The JSONL log and prompt/result files are in `~/.rondo/audit/` (or configured path). OB reads dispatch_ids from OAResult to cross-reference its own audit trail. The boundary is the dispatch_id — a shared identifier that links Rondo's audit to OB's records.

---

## 7. MCP / API Interface

No MCP interface for audit trail. `rondo audit` CLI is the query interface. CORE-STD-021 MCP tools in OB may reference dispatch_ids but do not query Rondo's audit files directly. Future: `rondo_query_batch_status` (Rondo-IFS-104) could include audit record references.

---

## 8. States & Modes

Audit records have two states: `INTENT` (phase 1 written, dispatch in progress) and `COMPLETE` (phase 2 written, dispatch finished). An `INTENT` record with no corresponding `COMPLETE` indicates a crash or timeout during dispatch. This is detectable and useful for post-mortem.

---

## 9. Configuration

```toml
[audit]
enabled = true
audit_dir = "~/.rondo/audit"
audit_retention_days = 0          # 0 = keep forever
prompt_storage = true             # Store full prompt text
result_storage = true             # Store full result JSON
```

---

## 10. Rules
**Audit field completeness (CRIT fix):** STD-113 MUST include ALL fields that consumer specs require: `prompt_hash` (for REQ-107 flakiness), `provider_id` (for REQ-110 multi-account), `model_used` (for cost tracking), `duration_ms` (for performance). Producer (STD-113) defines the schema — consumers reference it. Any new consumer field requirement MUST be added to STD-113 first. & Constraints

1. **Record BEFORE dispatch.** Intent is captured even if the subprocess crashes. Violation ID: `STD113-PRE-RECORD`
2. **Append-only.** Never modify or delete audit records. They're evidence. Violation ID: `STD113-APPEND-ONLY`
3. **Scrub credentials.** CORE-STD-010 rules apply to all audit files. No API keys in prompts or results. Violation ID: `STD113-SCRUB`
4. **Prompt hash for quick comparison.** Same prompt_hash = same prompt = easy to find repeat dispatches. Violation ID: `STD113-HASH`
5. **Failed tasks reference dispatch_id in morning report.** Mark can audit any failure by ID. Violation ID: `STD113-MORNING-REF`

---

## 11. Quality Attributes

- **Completeness:** Every dispatch has an audit record — no exceptions.
- **Immutability:** Append-only. Audit records are evidence, not mutable state.
- **Reproducibility:** Full prompt stored — any dispatch can be re-run from its audit record.

---

## 12. Shared Patterns

- **Two-phase recording:** Intent before action, outcome after. Same pattern as OB's round state transitions.
- **ULID for dispatch_id:** Time-sortable unique IDs. Same pattern as OB's sprint IDs.
- **Append-only JSONL:** One record per line, no modifications. Standard log aggregation format.

---

## 13. Integration Points

| Integration | What Crosses | Standard Enforced |
|-------------|-------------|-------------------|
| Rondo audit → OB | dispatch_id in OAResult | Cross-product traceability |
| Rondo audit → Rondo-STD-114 | Credential scrubbing before audit write | CORE-STD-010 rules |
| Rondo audit → Morning report | Failed dispatch_ids listed | Rondo-STD-113 req 14 |
| Rondo audit → CORE-STD-013 | Audit events as TrackerData | Append-only pattern |

---

## 14. Standards Applied

| Standard | How It Applies |
|----------|---------------|
| CORE-STD-010 | Error resilience — credential scrubbing for audit files |
| CORE-STD-012 | Requirement readiness — audit completeness is a quality signal |
| CORE-STD-013 | TrackerData — audit events feed cross-product tracking |
| CORE-STD-021 | MCP standard — audit queries not exposed via MCP (local CLI only) |

---

## 15. Self-Correction

Audit trails enable self-correction in consumers. OB can analyze patterns in audit records (e.g., "this prompt template fails 80% of the time") and adjust. Rondo itself does not act on audit data — it records faithfully for consumers to learn from (CORE-STD-011 pattern).

---

## 16. Assumptions

1. ULID generation produces unique IDs across concurrent dispatches.
2. Filesystem supports atomic append to JSONL file (single-writer assumption).
3. Audit directory has sufficient disk space for long-term storage.
4. Consumers query audit records by dispatch_id, not by sequential scan.

---

## 17. Success Criteria

| # | Criterion | How to Verify |
|---|-----------|---------------|
| 1 | Overnight run → every dispatch has an audit record | Count test |
| 2 | Failed task → morning report includes dispatch_id → `rondo audit {id}` shows full details | Post-mortem test |
| 3 | `rondo audit --cost --since yesterday` shows overnight spend | Cost test |
| 4 | No credentials in any audit file | Security scan |

---

## 18. Build Notes / Estimate

JSONL writer with atomic append: 2 hours. Prompt/result file storage: 2 hours. Credential scrubbing integration (Rondo-STD-114): 1 hour. CLI (`rondo audit` with query flags): 3 hours. Two-phase recording: 2 hours. Total: ~10 hours.

---

## 19. Test Categories

| Category | What It Tests |
|----------|--------------|
| Phase 1 tests | Intent record written before dispatch |
| Phase 2 tests | Outcome record written after dispatch |
| Crash tests | INTENT record exists without COMPLETE after simulated crash |
| Scrubbing tests | No credentials in audit files |
| CLI tests | Query by date, task, model, status, dispatch_id |

---

## 20. Failure Modes

| Failure | Impact | Mitigation |
|---------|--------|------------|
| Audit write fails | Dispatch proceeds but audit record lost | Log WARNING, do not block dispatch |
| Disk full | Audit files cannot be written | Pre-check disk space at startup |
| ULID collision | Duplicate dispatch_ids | Statistically negligible; detect and log if found |

---

## 21. Dependencies + Used By

| Direction | Spec | Relationship |
|-----------|------|-------------|
| Depends on | Rondo-REQ-100 | Core dispatch produces the events being audited |
| Depends on | Rondo-STD-108 | Error resilience — scrubbing rules for audit content |
| Depends on | CORE-STD-010 | Credential scrubbing for stored prompts/results |
| Depends on | CORE-STD-012 | Readiness tracking — audit health is a quality signal |
| Used by | Rondo-REQ-101 | Overnight automation references audit in morning report |
| Used by | Rondo-IFS-102 | OB integration receives dispatch_ids |
| Used by | Rondo-REQ-104 | Dispatch history queries the audit trail |

---

## 22. Decisions

| Decision | Rationale | Date |
|----------|-----------|------|
| D1: JSONL over SQLite | Append-only matches Rondo's stateless design. No DB dependency. | 2026-03-20 |
| D2: Full prompt storage | Reproducibility requires the exact prompt. Hash alone is insufficient. | 2026-03-20 |
| D3: Two-phase recording | Intent survives crashes. Phase 1 is the safety net. | 2026-03-20 |

---

## 23. Open Questions

1. Should audit files be HMAC-signed (extending Rondo-STD-107 rule 8 to audit)?
2. Should `rondo audit` support exporting to CSV for spreadsheet analysis?

---

## 24. Glossary

| Term | Definition |
|------|-----------|
| **ULID** | Universally Unique Lexicographically Sortable Identifier — time-sortable unique ID |
| **JSONL** | JSON Lines — one JSON object per line, append-friendly |
| **Two-phase recording** | Write intent before action, update outcome after — crash-safe |
| **Prompt hash** | SHA-256 of the prompt text — fast comparison without full-text read |

---

## 25. Risk / Criticality

**HIGH.** Without audit trails, overnight failures are unexplainable. The audit trail is the difference between "something failed" and "here is exactly what happened, what was sent, and what came back." Critical for trust in automated dispatch.

---

## 26. External Scan

Append-only audit logs are standard in financial systems and compliance frameworks. JSONL is used by Elasticsearch, Datadog, and similar tools. ULID is a documented standard (github.com/ulid/spec). No novel approaches — proven patterns for audit trails.

---

## 27. Security Considerations

Audit files contain prompts and AI responses — potentially sensitive content. Credential scrubbing (Rondo-STD-114) runs before writing. File permissions: 0600 (owner-only). Audit directory: 0700. HMAC signing (Rondo-STD-107 rule 8) may extend to audit files for tamper evidence.

---

## 28. Performance / Resource

JSONL append: ~1ms per record. Prompt file write: ~5ms (includes fsync). Disk usage: ~10KB per dispatch (audit record + prompt + result). 1000 dispatches/month = ~10MB. Storage cost is negligible for years of history.

---

## 29. Approval Record

| Reviewer | Role | Date | Verdict |
|----------|------|------|---------|
| Mark Hubers | Owner | 2026-03-22 | Approved (Session 84) |

---

## 30. AI Review

Reviewed by Cold Witness panel. Results in `reports/ai-reviews/`. Fix-review-fix cycle applied.

---

## 31. AI Went Wrong

No implementation yet — tracks AI-generated code deviations during build.

---

## 32. AI Assumptions

During spec design, AI assumed: Postgres target DB, YAML schemas as source of truth, MCP as query interface.

---

## 33. AI Cost

Spec review cost tracked in `reports/ai-reviews/`. ~$0.10/review/body.

---

## 34. Notes

CORE-STD-012 (Requirement Readiness) uses audit completeness as a quality signal — if dispatches are missing audit records, something is wrong. CORE-STD-013 (TrackerData) aligns with the append-only JSONL pattern. CORE-STD-021 MCP tools may reference dispatch_ids from OB's side but do not query Rondo's audit files directly.

---

### Feature Maturity

| Feature | Maturity | Evidence | Retest |
|---------|----------|----------|--------|
| Dispatch audit logging | THEORY | Specced for recording every dispatch with metadata | Phase 1 build |
| Audit trail integrity | THEORY | Specced for tamper-evident logging | Phase 2 build |
| Audit queries | THEORY | Specced for searching dispatch history | Phase 1 build |


## 35. Change History

| Version | Date | What Changed |
|---------|------|-------------|
| 1.0 | 2026-03-20 | Initial. Cross-pollinated from OB-REQ-114. 16 requirements. |
| 1.1 | 2026-03-22 | Filled to 35 sections. Added CORE-STD-012, CORE-STD-013, CORE-STD-021 refs. Approval record (Mark, Session 84). |
