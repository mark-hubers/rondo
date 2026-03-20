# STD-113: Dispatch Audit Trail

*Every dispatch recorded. What was sent, what came back, what changed. Critical for overnight post-mortem.*

**Product:** Rondo
**Category:** STD
**Created:** 2026-03-20 | **Updated:** 2026-03-20 | **Status:** DESIGNED
**Classification:** open
**Version:** 1.0
**Owner:** Mark G. Hubers
**Reviewed:** not-yet
**Supersedes:** none
**Depends on:** REQ-100 (Core), STD-108 (Error Resilience), CORE-STD-010 (Error Resilience) | **Used by:** REQ-101 (Automation), IFS-102 (OB Integration), REQ-104 (Dispatch History)
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
- Trend analysis on audit data (REQ-106)
- OB-side audit trails (OB-REQ-114)
- Security/credential handling (CORE-STD-010 scrubbing rules apply)

---

## 3. Requirements

| # | Requirement | Priority | Verified By |
|---|------------|----------|-------------|
| 1 | Every dispatch produces an audit record BEFORE the subprocess launches (intent recorded) | MUST | Timing test |
| 2 | Audit record updated AFTER dispatch completes (outcome recorded) | MUST | Completion test |
| 3 | Audit record contains: dispatch_id (ULID), task_name, model, prompt_hash (SHA-256 of prompt), timestamp, duration_sec, cost_usd, status, exit_code | MUST | Schema test |
| 4 | Full prompt text stored in separate file: `audit/{dispatch_id}.prompt.txt` | MUST | Prompt test |
| 5 | Full result stored in separate file: `audit/{dispatch_id}.result.json` | MUST | Result test |
| 6 | Files modified (heuristic extraction from output) stored in audit record | SHOULD | Files test |
| 7 | Audit records stored in `rondo_audit.jsonl` (append-only, one JSON object per line) | MUST | Storage test |
| 8 | Audit files stored in `~/.rondo/audit/` or configured path | MUST | Path test |
| 9 | Credential scrubbing applied per CORE-STD-010 reqs 19-22 before writing audit files | MUST | Scrub test |
| 10 | Audit records are append-only. Never modify or delete existing records. | MUST | Immutability test |
| 11 | `rondo audit` CLI: query audit log by date range, task name, model, status | SHOULD | Query test |
| 12 | `rondo audit {dispatch_id}` CLI: show full audit record including prompt and result | SHOULD | Detail test |
| 13 | `rondo audit --cost` CLI: show total cost for date range | SHOULD | Cost test |
| 14 | Overnight runs: morning report references dispatch_ids for failed tasks so Mark can audit | MUST | Report test |
| 15 | Audit retention: keep forever by default. `audit_retention_days` config to auto-archive old files. | SHOULD | Retention test |
| 16 | When OB-connected: dispatch_ids included in OAResult for cross-product traceability | SHOULD | Integration test |

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

## 10. Rules & Constraints

1. **Record BEFORE dispatch.** Intent is captured even if the subprocess crashes. Violation ID: `STD113-PRE-RECORD`
2. **Append-only.** Never modify or delete audit records. They're evidence. Violation ID: `STD113-APPEND-ONLY`
3. **Scrub credentials.** CORE-STD-010 rules apply to all audit files. No API keys in prompts or results. Violation ID: `STD113-SCRUB`
4. **Prompt hash for quick comparison.** Same prompt_hash = same prompt = easy to find repeat dispatches. Violation ID: `STD113-HASH`
5. **Failed tasks reference dispatch_id in morning report.** Mark can audit any failure by ID. Violation ID: `STD113-MORNING-REF`

---

## 17. Success Criteria

| # | Criterion | How to Verify |
|---|-----------|---------------|
| 1 | Overnight run → every dispatch has an audit record | Count test |
| 2 | Failed task → morning report includes dispatch_id → `rondo audit {id}` shows full details | Post-mortem test |
| 3 | `rondo audit --cost --since yesterday` shows overnight spend | Cost test |
| 4 | No credentials in any audit file | Security scan |

---

## 35. Change History

| Version | Date | What Changed |
|---------|------|-------------|
| 1.0 | 2026-03-20 | Initial. Cross-pollinated from OB-REQ-114. 16 requirements. |
