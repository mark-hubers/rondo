# STD-117: Prompt Protection

*Task templates are code. Track versions, detect weakening, prevent silent degradation of AI review quality.*

**Product:** Rondo
**Category:** STD
**Created:** 2026-03-20 | **Updated:** 2026-03-20 | **Status:** DESIGNED
**Classification:** open
**Version:** 1.0
**Owner:** Mark G. Hubers
**Reviewed:** not-yet
**Depends on:** REQ-100 (Core), STD-113 (Audit Trail), CORE-STD-011 (Self-Correction) | **Used by:** REQ-108 (Template Promotion), IFS-101 (Caliber Integration)
**Cross-pollinated from:** Caliber STD-107 (Security — prompt protection/versioning) — elevated from quality concern to security standard

---

## 1. Purpose & Scope

**What this spec does:** Task templates define what AI is asked to do. A weakened template (rules removed, severity lowered, checks skipped) is an invisible quality hole — AI does less, nobody notices until the codebase degrades. This spec versions task templates, detects weakening (fewer rules, lower bars), and alerts when templates change.

---

## 3. Requirements

| # | Requirement | Priority | Verified By |
|---|------------|----------|-------------|
| 1 | Every task template has a version hash (SHA-256 of content) | MUST | Hash test |
| 2 | Template changes detected by hash comparison against last-known version | MUST | Change test |
| 3 | Weakening detection: if a template change REMOVES rules, LOWERS severity thresholds, or SKIPS checks, flag as "WEAKENED" (severity: warn) | MUST | Weaken test |
| 4 | Strengthening detection: if a template change ADDS rules or RAISES bars, flag as "STRENGTHENED" (severity: info — positive change) | SHOULD | Strengthen test |
| 5 | Template change log: old_hash, new_hash, change_type (weakened/strengthened/modified), changed_at, changed_by | MUST | Log test |
| 6 | Alert on weakening: "Template 'review_forward' was weakened: 3 rules removed" shown in preflight | MUST | Alert test |
| 7 | Template freeze: `rondo freeze <template>` — changes require explicit `rondo unfreeze` with reason | SHOULD | Freeze test |
| 8 | Frozen template modified → finding (severity: block). Someone changed a frozen template without unfreezing. | MUST | Frozen test |
| 9 | `rondo templates --changes` CLI: show template change history | SHOULD | History test |
| 10 | Rule counting: parse template for rule-like patterns (numbered items, "MUST", "NEVER", constraint keywords). Compare counts across versions. | SHOULD | Count test |
| 11 | When OB-connected: template versions and change events included in OAResult | SHOULD | Integration test |
| 12 | CORE-STD-011 integration: track whether template changes improved or degraded dispatch quality (guess: "this change will improve results" → measure: did results actually improve?) | SHOULD | Correction test |

---

## 10. Rules & Constraints

1. **Templates are code.** Version them. Review changes. Don't let anyone silently weaken review prompts. Violation ID: `STD117-TEMPLATES-ARE-CODE`
2. **Weakening is suspicious.** Not always wrong — but always worth flagging. Removing rules from a review prompt = less review = lower quality. Violation ID: `STD117-FLAG-WEAKENING`
3. **Frozen = locked.** Frozen templates need explicit unfreeze. Bypass = block finding. Violation ID: `STD117-FROZEN`
4. **Measure the change.** Don't just detect weakening — measure its EFFECT via CORE-STD-011. A "weakened" template that produces BETTER results was actually strengthened. Violation ID: `STD117-MEASURE-EFFECT`

---

## 17. Success Criteria

| # | Criterion | How to Verify |
|---|-----------|---------------|
| 1 | Template rule removed → "WEAKENED" alert in preflight | Weaken test |
| 2 | Frozen template changed → block finding | Frozen test |
| 3 | Template version hash changes tracked in change log | Log test |
| 4 | Weakened template → dispatch quality measured → correlation reported | Effect test |

---

## 35. Change History

| Version | Date | What Changed |
|---------|------|-------------|
| 1.0 | 2026-03-20 | Initial. Cross-pollinated from Caliber STD-107. 12 requirements. |
