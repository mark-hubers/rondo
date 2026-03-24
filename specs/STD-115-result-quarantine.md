# STD-115: Result Quarantine

*AI results are staged, not trusted. Pending → Verified → Trusted. Never skip the gate.*

**Product:** Rondo
**Category:** STD
**Created:** 2026-03-20 | **Updated:** 2026-03-20 | **Status:** DESIGNED
**Classification:** open
**Version:** 1.0
**Owner:** Mark G. Hubers
**Reviewed:** not-yet
**Supersedes:** none
**Depends on:** REQ-100 (Core), STD-108 (Error Resilience), CORE-STD-011 (Self-Correction), CORE-STD-012, CORE-STD-021, ACE-STD-017, CORE-STD-013 | **Used by:** REQ-101 (Automation), IFS-102 (OB Integration)
**Cross-pollinated from:** ACE-STD-017 (Data Lifecycle — quarantine pattern) — adapted from knowledge quarantine to dispatch result quarantine

---

## 1. Purpose & Scope

**What this spec does:** AI-generated results (code, specs, reviews, fixes) should NOT be trusted blindly. This spec defines a 3-state quarantine system: results start as PENDING, pass verification to become VERIFIED, and get human approval (or high-confidence auto-approval) to become TRUSTED. Rejected results stay in quarantine as negative examples that teach the system.

**IN scope:**
- 3-state result lifecycle (PENDING → VERIFIED → TRUSTED or REJECTED)
- Verification criteria (what makes a result pass quarantine)
- Auto-approval thresholds (when high-confidence results can skip human review)
- Rejected results as learning data (negative examples)
- Overnight result staging (human reviews in morning)

**OUT of scope:**
- How results are produced (REQ-100 dispatch)
- How results are stored long-term (STD-113 audit trail)
- Caliber's verification of code quality (Caliber pipeline handles that separately)

**Users:** Mark (primary). Claude AI agents dispatching to other models. Future: teams needing multi-model AI orchestration, batch processing, cost optimization across AI providers.

---

<!-- convergence: allow(category_deep) reason: 3-AI consensus verified STD correct (Session 86) -->

## 2. The Problem

AI output looks correct but might not be. A code fix passes syntax checks but introduces a logic bug. A spec review finds no issues but misses a critical gap. Blindly trusting AI results is the fastest path to silent quality degradation. Quarantine forces verification before trust — every result earns its way to TRUSTED status.

---

## 3. Requirements

### 3-State Lifecycle


*All requirements use MUST/SHOULD priority per CORE-STD-012.*

| ID | Requirement | Priority | Verified By |
|----|-------------|----------|-------------|
| 001 | All AI-generated results start in `PENDING` state (quarantine) | MUST | Lifecycle test |
| 002 | Results that pass verification criteria move to `VERIFIED` | MUST | Verification test |
| 003 | `VERIFIED` results that get human approval (or auto-approval) move to `TRUSTED` | MUST | Approval test |
| 004 | Results that fail verification OR are rejected by human move to `REJECTED` | MUST | Rejection test |
| 005 | `REJECTED` results are KEPT (not deleted) — they are negative examples for CORE-STD-011 self-correction | MUST | Retention test |
| 006 | State transitions: PENDING→VERIFIED, PENDING→REJECTED, VERIFIED→TRUSTED, VERIFIED→REJECTED. No backward transitions. | MUST | Transition test |


### Verification Criteria

| ID | Requirement | Priority | Verified By |
|----|-------------|----------|-------------|
| 007 | Code results: must pass Caliber checks (Tier 1 minimum). Zero BLOCK findings = VERIFIED. | MUST | Code test |
| 008 | Spec/doc results: must have valid structure (per CORE-STD-000). Required sections present = VERIFIED. | SHOULD | Spec test |
| 009 | Review results: must have valid finding format (file, severity, message). Parseable = VERIFIED. | SHOULD | Review test |
| 010 | Fix results: original file + fix produces fewer findings than original alone. Improvement = VERIFIED. | SHOULD | Fix test |
| 011 | Any result with `status: error` stays PENDING (never auto-verifies) | MUST | Error test |


### Auto-Approval

| ID | Requirement | Priority | Verified By |
|----|-------------|----------|-------------|
| 012 | Start conservative: 0 auto-approvals until Mark has manually reviewed 100+ results | MUST | Bootstrap test |
| 013 | After 100+ manual reviews: high-confidence results (confidence >0.9) matching patterns Mark approved before can auto-promote to TRUSTED | SHOULD | Auto test |
| 014 | Auto-approval threshold configurable: `[quarantine] auto_approve_min_reviews = 100` | SHOULD | Config test |
| 015 | Auto-approved results still logged: "AUTO-APPROVED: matched pattern from review #{review_id}" | MUST | Audit test |


### Overnight Staging

| ID | Requirement | Priority | Verified By |
|----|-------------|----------|-------------|
| 016 | Overnight results: all stay in PENDING until morning. Human reviews in morning report. | MUST | Overnight test |
| 017 | Morning report sections: "N results PENDING review" with task names, confidence scores, and quick-approve links | SHOULD | Report test |
| 018 | Stale quarantine: results PENDING >7 days without review → alert "Results aging in quarantine" | SHOULD | Stale test |


### Learning from Rejection

| ID | Requirement | Priority | Verified By |
|----|-------------|----------|-------------|
| 019 | Rejected results feed CORE-STD-011: record_outcome(was_corrected=True, correction_source='review_rejected') | MUST | Learning test |
| 020 | Edited results (user modifies before approving) are MOST valuable — show what was close but wrong | MUST | Edit test |
| 021 | Track rejection reasons: `wrong_approach`, `incomplete`, `hallucinated`, `style_mismatch`, `other` | SHOULD | Reason test |


---

## 4. Architecture / Design

Quarantine is a state machine wrapper around dispatch results. The runner tags every TaskResult with `quarantine_state: "PENDING"`. Verification (Caliber checks, structure checks) promotes to `VERIFIED`. Human approval (or calibrated auto-approval) promotes to `TRUSTED`. Rejection at any stage marks `REJECTED` but preserves the result. The state machine is one-directional — no backward transitions.

---

## 5. Data Model

Quarantine record: `{dispatch_id, task_name, quarantine_state: "PENDING"|"VERIFIED"|"TRUSTED"|"REJECTED", verified_at, verified_by, approved_at, approved_by, rejection_reason, original_result, edited_result}`. Stored in quarantine JSONL alongside audit trail. Linked to DispatchUsage via dispatch_id.

---

## 6. Data Boundary

Quarantine state is managed by Rondo but consumed by OB. OB reads quarantine_state from OAResult to decide whether to apply results. The boundary is the quarantine_state field in the result object. Consumers MUST check quarantine_state before using results — PENDING results are not actionable.

---

## 7. MCP / API Interface

No MCP interface for quarantine management. Quarantine state transitions happen via `rondo review` CLI (approve/reject) or auto-approval logic. CORE-STD-021 MCP tools in OB may query quarantine state from ingested results but cannot modify it.

---

## 8. States & Modes

```
     ┌──────────┐
     │ PENDING  │ ← All results start here
     └────┬─────┘
          │
    ┌─────┴─────┐
    │ Verify    │ (Caliber check, structure check, etc.)
    ├───────────┤
    │ PASS?     │──── NO ──→ REJECTED (kept as negative example)
    └─────┬─────┘
          │ YES
    ┌─────┴─────┐
    │ VERIFIED  │
    └─────┬─────┘
          │
    ┌─────┴─────┐
    │ Approve   │ (human or auto if >100 reviews + confidence >0.9)
    ├───────────┤
    │ APPROVED? │──── NO ──→ REJECTED
    └─────┬─────┘
          │ YES
    ┌─────┴─────┐
    │ TRUSTED   │ ← Safe to use
    └───────────┘
```

**State Machine Type:** FORWARD-ONLY
**Rationale:** Results progress PENDING → VERIFIED → TRUSTED (or REJECTED at any verification/approval gate). No backward transitions — a rejected result stays rejected. A trusted result does not return to pending.
**Rollback:** Not applicable — rejected results are kept as negative examples. New results start fresh at PENDING.

---

## 9. Configuration

```toml
[quarantine]
enabled = true
auto_approve_min_reviews = 100       # Manual reviews before auto-approve unlocks
auto_approve_confidence = 0.9        # Min confidence for auto-approval
stale_days = 7                       # Alert if PENDING longer than this
overnight_mode = "stage_all"         # stage_all | auto_verify | auto_approve
```

---

## 10. Rules & Constraints

1. **AI output is NEVER directly trusted.** Always quarantine first. Violation ID: `STD115-ALWAYS-QUARANTINE`
2. **Rejected = kept.** Rejected results are negative examples. Deleting them = deleting learning data. Violation ID: `STD115-KEEP-REJECTED`
3. **Conservative start.** 0 auto-approvals until 100+ manual reviews. Don't trust the auto-approver until it's calibrated. Violation ID: `STD115-CONSERVATIVE`
4. **Edits are gold.** When a user edits a result before approving, both versions (original + edited) are preserved. The diff teaches the system what "close but wrong" looks like. Violation ID: `STD115-PRESERVE-EDITS`
5. **No backward transitions.** TRUSTED never goes back to VERIFIED. If a trusted result turns out wrong, create a NEW correction record (CORE-STD-011). Violation ID: `STD115-NO-BACKWARD`

---

## 11. Quality Attributes

- **Zero blind trust:** Every result quarantined by default. Trust is earned, not assumed.
- **Learning from rejection:** Rejected results are the most valuable training data.
- **Progressive automation:** Starts fully manual, earns auto-approval after 100+ reviews.

---

## 12. Shared Patterns

- **3-state lifecycle:** PENDING → VERIFIED → TRUSTED. Same pattern as ACE-STD-017 data lifecycle quarantine.
- **Confidence-based auto-approval:** Same pattern as STD-114 confidence scoring.
- **Negative examples preserved:** Rejected results kept — same philosophy as CORE-STD-011 self-correction.

---

## 13. Integration Points

| Integration | What Crosses | Standard Enforced |
|-------------|-------------|-------------------|
| STD-115 → Caliber | Caliber checks verify PENDING results | Code quality gates |
| STD-115 → OB | quarantine_state in OAResult | Consumer respects state |
| STD-115 → CORE-STD-011 | Rejected results feed self-correction | record_outcome pattern |
| STD-115 → CORE-STD-013 | Quarantine events as TrackerData | Append-only tracking |

---

## 14. Standards Applied

| Standard | How It Applies |
|----------|---------------|
| CORE-STD-011 | Self-correction — rejected results feed the learning loop |
| CORE-STD-012 | Requirement readiness — quarantine health is a quality signal |
| CORE-STD-013 | TrackerData — quarantine events (approve, reject) are trackable |
| CORE-STD-021 | MCP standard — quarantine state queryable from consumer MCP tools |

---

## 15. Self-Correction

Quarantine IS Rondo's self-correction mechanism for AI output quality. Rejected results with `correction_source='review_rejected'` feed CORE-STD-011. Edited results (original + modified) provide the highest-value training signal — they show exactly where the AI was close but wrong.

---

## 16. Assumptions

1. Human review is available within 7 days (stale quarantine threshold).
2. Auto-approval patterns from 100+ reviews are representative of future results.
3. Caliber checks (Tier 1 minimum) are a valid proxy for code quality verification.
4. Consumers check quarantine_state before acting on results.

---

## 17. Success Criteria

| # | Criterion | How to Verify |
|---|-----------|---------------|
| 1 | Overnight run → all results in PENDING → morning report shows them | Overnight test |
| 2 | Code result passes Caliber → VERIFIED → Mark approves → TRUSTED | Full lifecycle test |
| 3 | Mark rejects a result → REJECTED + correction record created | Rejection test |
| 4 | After 100+ reviews, high-confidence result auto-approves | Auto-approve test |
| 5 | Stale result >7 days → alert fires | Stale test |

---

## 18. Build Notes / Estimate

State machine: 2 hours (transitions, validation, no-backward rule). Verification integration: 3 hours (Caliber hook, structure check, finding format check). Auto-approval engine: 3 hours (pattern matching, confidence threshold, bootstrapping). Morning report quarantine section: 1 hour. CLI (`rondo review`): 2 hours. Total: ~11 hours.

---

## 19. Test Categories

| Category | What It Tests |
|----------|--------------|
| Lifecycle tests | All valid transitions, no backward transitions |
| Verification tests | Each result type (code, spec, review, fix) verification criteria |
| Auto-approval tests | Bootstrap threshold, confidence matching, audit logging |
| Rejection tests | Rejection preserved, reason recorded, self-correction fed |
| Overnight tests | All results staged, morning report shows PENDING count |

---

## 20. Failure Modes

| Failure | Impact | Mitigation |
|---------|--------|------------|
| Auto-approve false positive | Bad result marked TRUSTED | Conservative start (100 reviews), confidence 0.9 |
| Stale quarantine ignored | Results never reviewed | 7-day alert fires (req 18) |
| Verification check too strict | Good results stuck in PENDING | Review verification criteria, adjust thresholds |

---

## 21. Dependencies + Used By

| Direction | Spec | Relationship |
|-----------|------|-------------|
| Depends on | REQ-100 | Core dispatch produces results being quarantined |
| Depends on | STD-108 | Error resilience for quarantine operations |
| Depends on | CORE-STD-011 | Self-correction — rejected results feed learning |
| Depends on | CORE-STD-012 | Readiness — quarantine health as quality signal |
| Used by | REQ-101 | Overnight results staged in quarantine |
| Used by | IFS-102 | OB reads quarantine_state from results |
| Used by | IFS-101 | Caliber integration for verification checks |

---

## 22. Decisions

| Decision | Rationale | Date |
|----------|-----------|------|
| D1: 3-state, not 2-state | VERIFIED ≠ TRUSTED. Verified means "structurally correct." Trusted means "Mark would ship this." Two different bars. | 2026-03-20 |
| D2: 100 reviews before auto-approve | Auto-approve needs calibration data. 100 gives enough patterns to match against. | 2026-03-20 |
| D3: Keep rejected results | They're the most valuable learning data. "What the AI gets wrong" teaches more than "what it gets right." From ACE-STD-017. | 2026-03-20 |
| D4: Edit preservation | User edits show the gap between "what AI produced" and "what was wanted." Fine-grained feedback. | 2026-03-20 |

---

## 23. Open Questions

1. Should auto-approval patterns be cross-project (learned from OB reviews applied to Caliber)?
2. Should quarantine state be queryable from the morning report CLI?

---

## 24. Glossary

| Term | Definition |
|------|-----------|
| **Quarantine** | Holding state for AI results before they are trusted |
| **PENDING** | Result awaiting verification — not yet checked |
| **VERIFIED** | Result passed automated checks — awaiting human approval |
| **TRUSTED** | Result approved for use — safe to apply |
| **REJECTED** | Result failed verification or human review — kept as learning data |

---

## 25. Risk / Criticality

**HIGH.** Without quarantine, AI results are blindly trusted. A hallucinated fix could be applied to production code. A wrong review finding could block valid work. Quarantine is the trust boundary between AI output and human-approved results.

---

## 26. External Scan

Content moderation systems use similar staged review pipelines (auto-filter → human review → approved). Medical AI systems require human-in-the-loop approval before acting on results. Rondo adapts these patterns for code/spec quality — same principle, different domain.

---

## 27. Security Considerations

Quarantine prevents untrusted AI output from being applied without review. This is a security-adjacent concern: a hallucinated code fix could introduce vulnerabilities. Quarantine is the gate between AI suggestion and human-approved change. See STD-107 for broader security context.

---

## 28. Performance / Resource

Quarantine state tracking: ~1ms per state transition (JSONL append). Verification checks: depends on check type (Caliber: 5-30 seconds, structure: <1 second). Auto-approval pattern matching: <5ms. No significant performance impact on the dispatch pipeline.

---

## 29. Approval Record

| Reviewer | Role | Date | Verdict |
|----------|------|------|---------|
| Mark Hubers | Owner | 2026-03-22 | Approved (Session 84) |

---

## 30. AI Review

— filled after build.

---

## 31. AI Went Wrong

— filled during build.

---

## 32. AI Assumptions

— filled during build.

---

## 33. AI Cost

— filled during build.

---

## 34. Notes

CORE-STD-012 (Requirement Readiness) uses quarantine health (PENDING count, stale count) as a quality signal. CORE-STD-013 (TrackerData) records quarantine events for trend analysis (are results improving over time?). CORE-STD-021 MCP tools in OB may query quarantine state for dashboard display.

---

### Feature Maturity

| Feature | Maturity | Evidence | Retest |
|---------|----------|----------|--------|
| Result quarantine concept | THEORY | Specced for isolating suspect AI results | Phase 1 build |
| Quarantine triggers | THEORY | Specced for conditions that trigger quarantine | Phase 1 build |
| Quarantine review process | THEORY | Specced for human review of quarantined results | Phase 1 build |


## 35. Change History

| Version | Date | What Changed |
|---------|------|-------------|
| 1.0 | 2026-03-20 | Initial. Cross-pollinated from ACE-STD-017 quarantine pattern. 21 requirements. 3-state lifecycle with auto-approval. |
| 1.1 | 2026-03-22 | Filled to 35 sections. Added CORE-STD-012, CORE-STD-013, CORE-IFS-005 refs. Approval record (Mark, Session 84). |
