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
**Depends on:** REQ-100 (Core), STD-108 (Error Resilience), CORE-STD-011 (Self-Correction) | **Used by:** REQ-101 (Automation), IFS-102 (OB Integration)
**Cross-pollinated from:** ACE F17 (Data Lifecycle — quarantine pattern) — adapted from knowledge quarantine to dispatch result quarantine

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

---

## 3. Requirements

### 3-State Lifecycle

| # | Requirement | Priority | Verified By |
|---|------------|----------|-------------|
| 1 | All AI-generated results start in `PENDING` state (quarantine) | MUST | Lifecycle test |
| 2 | Results that pass verification criteria move to `VERIFIED` | MUST | Verification test |
| 3 | `VERIFIED` results that get human approval (or auto-approval) move to `TRUSTED` | MUST | Approval test |
| 4 | Results that fail verification OR are rejected by human move to `REJECTED` | MUST | Rejection test |
| 5 | `REJECTED` results are KEPT (not deleted) — they are negative examples for CORE-STD-011 self-correction | MUST | Retention test |
| 6 | State transitions: PENDING→VERIFIED, PENDING→REJECTED, VERIFIED→TRUSTED, VERIFIED→REJECTED. No backward transitions. | MUST | Transition test |

### Verification Criteria

| # | Requirement | Priority | Verified By |
|---|------------|----------|-------------|
| 7 | Code results: must pass Caliber checks (Tier 1 minimum). Zero BLOCK findings = VERIFIED. | MUST | Code test |
| 8 | Spec/doc results: must have valid structure (per CORE-STD-000). Required sections present = VERIFIED. | SHOULD | Spec test |
| 9 | Review results: must have valid finding format (file, severity, message). Parseable = VERIFIED. | SHOULD | Review test |
| 10 | Fix results: original file + fix produces fewer findings than original alone. Improvement = VERIFIED. | SHOULD | Fix test |
| 11 | Any result with `status: error` stays PENDING (never auto-verifies) | MUST | Error test |

### Auto-Approval

| # | Requirement | Priority | Verified By |
|---|------------|----------|-------------|
| 12 | Start conservative: 0 auto-approvals until Mark has manually reviewed 100+ results | MUST | Bootstrap test |
| 13 | After 100+ manual reviews: high-confidence results (confidence >0.9) matching patterns Mark approved before can auto-promote to TRUSTED | SHOULD | Auto test |
| 14 | Auto-approval threshold configurable: `[quarantine] auto_approve_min_reviews = 100` | SHOULD | Config test |
| 15 | Auto-approved results still logged: "AUTO-APPROVED: matched pattern from review #{review_id}" | MUST | Audit test |

### Overnight Staging

| # | Requirement | Priority | Verified By |
|---|------------|----------|-------------|
| 16 | Overnight results: all stay in PENDING until morning. Human reviews in morning report. | MUST | Overnight test |
| 17 | Morning report sections: "N results PENDING review" with task names, confidence scores, and quick-approve links | SHOULD | Report test |
| 18 | Stale quarantine: results PENDING >7 days without review → alert "Results aging in quarantine" | SHOULD | Stale test |

### Learning from Rejection

| # | Requirement | Priority | Verified By |
|---|------------|----------|-------------|
| 19 | Rejected results feed CORE-STD-011: record_outcome(was_corrected=True, correction_source='review_rejected') | MUST | Learning test |
| 20 | Edited results (user modifies before approving) are MOST valuable — show what was close but wrong | MUST | Edit test |
| 21 | Track rejection reasons: `wrong_approach`, `incomplete`, `hallucinated`, `style_mismatch`, `other` | SHOULD | Reason test |

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

## 17. Success Criteria

| # | Criterion | How to Verify |
|---|-----------|---------------|
| 1 | Overnight run → all results in PENDING → morning report shows them | Overnight test |
| 2 | Code result passes Caliber → VERIFIED → Mark approves → TRUSTED | Full lifecycle test |
| 3 | Mark rejects a result → REJECTED + correction record created | Rejection test |
| 4 | After 100+ reviews, high-confidence result auto-approves | Auto-approve test |
| 5 | Stale result >7 days → alert fires | Stale test |

---

## 22. Decisions

| Decision | Rationale | Date |
|----------|-----------|------|
| D1: 3-state, not 2-state | VERIFIED ≠ TRUSTED. Verified means "structurally correct." Trusted means "Mark would ship this." Two different bars. | 2026-03-20 |
| D2: 100 reviews before auto-approve | Auto-approve needs calibration data. 100 gives enough patterns to match against. | 2026-03-20 |
| D3: Keep rejected results | They're the most valuable learning data. "What the AI gets wrong" teaches more than "what it gets right." From ACE F17. | 2026-03-20 |
| D4: Edit preservation | User edits show the gap between "what AI produced" and "what was wanted." Fine-grained feedback. | 2026-03-20 |

---

## 35. Change History

| Version | Date | What Changed |
|---------|------|-------------|
| 1.0 | 2026-03-20 | Initial. Cross-pollinated from ACE F17 quarantine pattern. 21 requirements. 3-state lifecycle with auto-approval. |
