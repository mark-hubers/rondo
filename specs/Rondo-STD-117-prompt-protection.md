# Rondo-STD-117: Prompt Protection

*Task templates are code. Track versions, detect weakening, prevent silent degradation of AI review quality.*

**Product:** Rondo
**Category:** STD
**Created:** 2026-03-20 | **Updated:** 2026-03-20 | **Status:** DESIGNED
**Classification:** open
**Version:** 1.0
**Owner:** Mark G. Hubers
**Reviewed:** not-yet
**Depends on:** Rondo-REQ-100 (Core), Rondo-STD-113 (Audit Trail), CORE-STD-011 (Self-Correction), CORE-STD-012, CORE-STD-021, CORE-STD-013 | **Used by:** Rondo-REQ-108 (Template Promotion), Rondo-IFS-101 (Caliber Integration)
**Cross-pollinated from:** Caliber Rondo-STD-107 (Security — prompt protection/versioning) — elevated from quality concern to security standard

---

## 1. Purpose & Scope

**What this spec does:** Task templates define what AI is asked to do. A weakened template (rules removed, severity lowered, checks skipped) is an invisible quality hole — AI does less, nobody notices until the codebase degrades. This spec versions task templates, detects weakening (fewer rules, lower bars), and alerts when templates change.

**Users:** Mark (primary). Claude AI agents dispatching to other models. Future: teams needing multi-model AI orchestration, batch processing, cost optimization across AI providers.

---

## 2. The Problem

Task templates define what AI is asked to do. A weakened template (rules removed, severity lowered, checks skipped) degrades review quality silently — AI does less, nobody notices until code quality drops. Templates are code. They need versioning, change detection, and weakening alerts, just like source code.

---

## 3. Requirements


*All requirements use MUST/SHOULD priority per CORE-STD-012.*

| ID | Requirement | Priority | Verified By |
|----|-------------|----------|-------------|
| 001 | Every task template has a version hash (SHA-256 of content) | MUST | Hash test |
| 002 | Template changes detected by hash comparison against last-known version | MUST | Change test |
| 003 | Weakening detection: if a template change REMOVES rules, LOWERS severity thresholds, or SKIPS checks, flag as "WEAKENED" (severity: warn) | MUST | Weaken test |
| 004 | Strengthening detection: if a template change ADDS rules or RAISES bars, flag as "STRENGTHENED" (severity: info — positive change) | SHOULD | Strengthen test |
| 005 | Template change log: old_hash, new_hash, change_type (weakened/strengthened/modified), changed_at, changed_by | MUST | Log test |
| 006 | Alert on weakening: "Template 'review_forward' was weakened: 3 rules removed" shown in preflight | MUST | Alert test |
| 007 | Template freeze: `rondo freeze <template>` — changes require explicit `rondo unfreeze` with reason | SHOULD | Freeze test |
| 008 | Frozen template modified → finding (severity: block). Someone changed a frozen template without unfreezing. | MUST | Frozen test |
| 009 | `rondo templates --changes` CLI: show template change history | SHOULD | History test |
| 010 | Rule counting: parse template for rule-like patterns (numbered items, "MUST", "NEVER", constraint keywords). Compare counts across versions. | SHOULD | Count test |
| 011 | When OB-connected: template versions and change events included in OAResult | SHOULD | Integration test |
| 012 | CORE-STD-011 integration: track whether template changes improved or degraded dispatch quality (guess: "this change will improve results" → measure: did results actually improve?) | SHOULD | Correction test |


---

## 4. Architecture / Design

Template protection operates as a pre-dispatch check: before dispatching a task, compare the current template hash against the last-known hash. If changed, classify the change (weakened/strengthened/modified) by comparing rule counts and severity thresholds. Frozen templates require explicit unfreeze before changes are accepted.

---

## 5. Data Model

Template record: `{template_name, current_hash (SHA-256), rule_count, severity_thresholds: dict, frozen: bool, last_changed_at, last_changed_by}`. Change log entry: `{template_name, old_hash, new_hash, change_type: "weakened"|"strengthened"|"modified", changed_at, changed_by, rule_delta: int}`.

---

## 6. Data Boundary

Template protection is internal to Rondo. Template records and change logs are stored locally (TOML or JSONL). When OB-connected, template versions and change events are included in OAResult. The boundary is the change event metadata in results, not the template content itself.

---

## 7. MCP / API Interface

No MCP interface for template management. Templates are managed via `rondo freeze`, `rondo unfreeze`, and `rondo templates --changes` CLI commands. CORE-STD-021 MCP tools do not expose template management — it is a local development concern.

---

## 8. States & Modes

Templates have two states: `ACTIVE` (normal, changes detected and classified) and `FROZEN` (locked, changes produce block findings). Frozen templates require `rondo unfreeze <template> --reason "..."` before modification. Freeze/unfreeze events are logged in the change log.

**State Machine Type:** BIDIRECTIONAL
**Rationale:** Templates transition ACTIVE ↔ FROZEN via freeze/unfreeze commands. Both directions are explicit human actions with logged reasons. The cycle can repeat indefinitely.
**Rollback:** `rondo unfreeze <template> --reason "..."` returns a FROZEN template to ACTIVE.

---

## 9. Configuration

```toml
[templates]
change_detection = true
freeze_by_default = false          # New templates start unfrozen
rule_count_method = "keyword"      # "keyword" (MUST/NEVER/etc.) or "numbered" (numbered items)
```

---

## 10. Rules & Constraints

1. **Templates are code.** Version them. Review changes. Don't let anyone silently weaken review prompts. Violation ID: `STD117-TEMPLATES-ARE-CODE`
2. **Weakening is suspicious.** Not always wrong — but always worth flagging. Removing rules from a review prompt = less review = lower quality. Violation ID: `STD117-FLAG-WEAKENING`
3. **Frozen = locked.** Frozen templates need explicit unfreeze. Bypass = block finding. Violation ID: `STD117-FROZEN`
4. **Measure the change.** Don't just detect weakening — measure its EFFECT via CORE-STD-011. A "weakened" template that produces BETTER results was actually strengthened. Violation ID: `STD117-MEASURE-EFFECT`

---

## 11. Quality Attributes

- **Transparency:** Every template change is detected, classified, and logged.
- **Protection:** Frozen templates cannot be silently weakened.
- **Measurability:** Weakening/strengthening is quantified (rule count delta, severity changes).

---

## 12. Shared Patterns

- **Hash-based change detection:** Same pattern as git content addressing and Rondo-STD-113 prompt hashing.
- **Freeze/unfreeze with reason:** Same pattern as database migration locks.
- **Weakening detection:** Rule counting is a novel pattern specific to prompt quality protection.

---

## 13. Integration Points

| Integration | What Crosses | Standard Enforced |
|-------------|-------------|-------------------|
| Rondo-STD-117 → Preflight | Weakening alerts shown at session start | Template change detection |
| Rondo-STD-117 → OB | Template versions in OAResult | Rondo-IFS-102 metadata |
| Rondo-STD-117 → CORE-STD-011 | Template change effect measured | record_guess/record_outcome |
| Rondo-STD-117 → CORE-STD-013 | Template change events as TrackerData | Append-only tracking |

---

## 14. Standards Applied

| Standard | How It Applies |
|----------|---------------|
| Caliber Rondo-STD-107 | Origin pattern — prompt protection elevated from Caliber to Rondo |
| CORE-STD-011 | Self-correction — measure whether template changes improve results |
| CORE-STD-012 | Requirement readiness — frozen template violation blocks READY |
| CORE-STD-013 | TrackerData — template change events are trackable |
| CORE-STD-021 | MCP standard — template data not exposed via MCP (local only) |

---

## 15. Self-Correction

CORE-STD-011 integration: when a template changes, record a guess ("this change will improve dispatch quality"). After subsequent dispatches, measure whether results actually improved. A "weakened" template that produces better results was actually a refinement — the measurement overrides the classification.

---

## 16. Assumptions

1. Rule counting via keyword matching (MUST, NEVER, SHALL, etc.) is a reasonable proxy for template strength.
2. Template content is text-parseable (not binary or encrypted).
3. SHA-256 hash collisions are negligible (standard cryptographic assumption).
4. Template changes are infrequent — change detection at dispatch time is sufficient.

---

## 17. Success Criteria

| # | Criterion | How to Verify |
|---|-----------|---------------|
| 1 | Template rule removed → "WEAKENED" alert in preflight | Weaken test |
| 2 | Frozen template changed → block finding | Frozen test |
| 3 | Template version hash changes tracked in change log | Log test |
| 4 | Weakened template → dispatch quality measured → correlation reported | Effect test |

---

## 18. Build Notes / Estimate

Hash computation and change detection: 2 hours. Rule counter (keyword parser): 2 hours. Weakening/strengthening classifier: 2 hours. Freeze/unfreeze state management: 1 hour. CLI commands: 2 hours. Preflight integration: 1 hour. Total: ~10 hours.

---

## 19. Test Categories

| Category | What It Tests |
|----------|--------------|
| Hash tests | Template content → SHA-256 hash, change detection |
| Rule counting tests | Keyword extraction (MUST/NEVER/etc.), count comparison |
| Classification tests | Weakened vs strengthened vs modified categorization |
| Freeze tests | Frozen template modified → block finding |
| Change log tests | Log entries capture all required fields |

---

## 20. Failure Modes

| Failure | Impact | Mitigation |
|---------|--------|------------|
| Rule counter miscount | Wrong classification (weakened vs strengthened) | Multiple counting methods (keyword + numbered) |
| Frozen template bypass | Template weakened without detection | Block finding on any frozen change |
| Hash registry corruption | All templates appear "changed" | Registry is a simple file — easy to rebuild |

---

## 21. Dependencies + Used By

| Direction | Spec | Relationship |
|-----------|------|-------------|
| Depends on | Rondo-REQ-100 | Core dispatch uses templates being protected |
| Depends on | Rondo-STD-113 | Audit trail links template version to dispatch |
| Depends on | CORE-STD-011 | Self-correction — measure template change effects |
| Depends on | CORE-STD-012 | Readiness — frozen template violations block READY |
| Used by | Rondo-REQ-108 | Template promotion lifecycle |
| Used by | Rondo-IFS-101 | Caliber integration uses protected templates |

---

## 22. Decisions

| Decision | Rationale | Date |
|----------|-----------|------|
| D1: Templates are code | Version, review, and protect — same discipline as source | 2026-03-20 |
| D2: Weakening flagged, not blocked (unless frozen) | Weakening might be intentional refinement | 2026-03-20 |
| D3: Rule counting as proxy | Imperfect but practical — catches obvious weakening | 2026-03-20 |

---

## 23. Open Questions

1. Should template versions be stored in git (tracked alongside code)?
2. Should weakening detection use semantic analysis (AI-driven) instead of keyword counting?

---

## 24. Glossary

| Term | Definition |
|------|-----------|
| **Task template** | The prompt text sent to AI for a specific task type |
| **Weakening** | Template change that removes rules, lowers thresholds, or skips checks |
| **Strengthening** | Template change that adds rules or raises quality bars |
| **Frozen** | Template state that blocks all changes without explicit unfreeze |

---

## 25. Risk / Criticality

**MEDIUM-HIGH.** Template weakening is an invisible quality hole. AI does less, results look OK (fewer findings = "cleaner" code), but actual quality drops. Detection is the primary defense against silent template degradation.

---

## 26. External Scan

No existing tool tracks prompt template versioning or weakening detection. This is novel in the AI operations space. The concept draws from code coverage ratchets (Rondo-STD-103) — quality measures that only go up — applied to prompt content.

---

## 27. Security Considerations

Template weakening could be an attack vector: an adversary modifies a review template to skip security checks, then submits code that would have been caught. Frozen templates (req 7-8) defend against this. See Rondo-STD-107 for broader security context.

---

## 28. Performance / Resource

Hash computation: <1ms per template. Rule counting: ~5ms per template (regex scan). Total per-dispatch overhead: <10ms (single template check). Template registry: <1KB. No significant performance impact.

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

CORE-STD-012 (Requirement Readiness) treats frozen template violations as blockers. CORE-STD-013 (TrackerData) records template change events for trend analysis (are templates getting stronger or weaker over time?). CORE-STD-021 MCP tools do not expose template management — it is local to Rondo's development workflow.

---

### Feature Maturity

| Feature | Maturity | Evidence | Retest |
|---------|----------|----------|--------|
| Prompt protection rules | THEORY | Specced for preventing prompt injection in tasks | Phase 1 build |
| Input validation | THEORY | Specced for sanitizing task inputs | Phase 1 build |
| Prompt template locking | THEORY | Specced for immutable prompt sections | Phase 1 build |


## 35. Change History

| Version | Date | What Changed |
|---------|------|-------------|
| 1.0 | 2026-03-20 | Initial. Cross-pollinated from Caliber Rondo-STD-107. 12 requirements. |
| 1.1 | 2026-03-22 | Filled to 35 sections. Added CORE-STD-012, CORE-STD-013, CORE-STD-021 refs. Approval record (Mark, Session 84). |
