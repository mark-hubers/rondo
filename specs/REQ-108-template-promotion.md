# REQ-108: Task Template Promotion

*Useful twice = permanent template. Track one-off task definitions, promote the ones that stick.*

**Product:** Rondo
**Category:** REQ
**Created:** 2026-03-20 | **Updated:** 2026-03-20 | **Status:** DESIGNED
**Classification:** open
**Version:** 1.0
**Owner:** Mark G. Hubers
**Reviewed:** not-yet
**Depends on:** REQ-100 (Core), STD-113 (Dispatch Audit Trail) | **Used by:** REQ-101 (Automation)
**Cross-pollinated from:** OB-REQ-112 (Ad-Hoc Promotion) — adapted from methodology tool promotion to task template promotion

---

## 1. Purpose & Scope

**What this spec does:** Users create one-off task definitions for specific dispatches. Some are used once and forgotten. Others get reused 5, 10, 20 times — these are templates hiding in plain sight. This spec tracks usage and promotes popular task definitions to built-in templates, so proven patterns get reused instead of reinvented.

---

## 3. Requirements

| # | Requirement | Priority | Verified By |
|---|------------|----------|-------------|
| 1 | Track every unique task definition by prompt_hash: first_used_at, last_used_at, usage_count | MUST | Tracking test |
| 2 | Promotion threshold: usage_count >= 2 in different sessions = promotion candidate | MUST | Threshold test |
| 3 | Promotion lifecycle: `ADHOC` (one-off) → `CANDIDATE` (used 2+) → `TEMPLATE` (promoted to built-in) → `ARCHIVED` (unused 90+ days) | MUST | Lifecycle test |
| 4 | `rondo templates` CLI: show all templates with usage count and last_used_at | SHOULD | CLI test |
| 5 | `rondo templates --candidates` CLI: show promotion candidates (used 2+ but not yet promoted) | SHOULD | Candidates test |
| 6 | Promotion: copy task definition to `~/.rondo/templates/` with a name. Available in `rondo run --template <name>`. | SHOULD | Promote test |
| 7 | Auto-surface candidates in morning report: "3 task definitions used 2+ times — consider promoting" | SHOULD | Report test |
| 8 | Template usage feeds back: promoted templates tracked for continued usage. If unused 90+ days → suggest archiving. | SHOULD | Archive test |
| 9 | When OB-connected: template promotion events included in OAResult metadata | SHOULD | Integration test |
| 10 | Derived from STD-113 audit trail (prompt_hash grouping) — no separate tracking DB needed | MUST | Source test |

---

## 10. Rules & Constraints

1. **2 uses = candidate.** Not 1 (too aggressive), not 5 (too conservative). 2 in different sessions proves it wasn't a typo. Violation ID: `REQ108-TWO-USES`
2. **Promotion is manual.** Auto-surfacing is fine. Auto-promoting is not — Mark decides what becomes a template. Violation ID: `REQ108-MANUAL-PROMOTE`
3. **Archive, don't delete.** Unused templates might be seasonal. Archive preserves them. Violation ID: `REQ108-ARCHIVE`

---

## 35. Change History

| Version | Date | What Changed |
|---------|------|-------------|
| 1.0 | 2026-03-20 | Initial. Cross-pollinated from OB-REQ-112. 10 requirements. |
