# STD-112: Golden Numbers

*Track the counts that matter. Model count, worker count, task type count. Drift detection catches "docs say 3 models but config supports 5."*

**Product:** Rondo
**Category:** STD
**Created:** 2026-03-20 | **Updated:** 2026-03-20 | **Status:** DESIGNED
**Classification:** open
**Version:** 1.0
**Owner:** Mark G. Hubers
**Reviewed:** not-yet
**Depends on:** REQ-100 (Core), STD-102 (Configuration) | **Used by:** REQ-103 (Preflight)
**Cross-pollinated from:** OB-REQ-108 (Golden Numbers) — adapted from methodology counts to dispatch counts

---

## 3. Requirements

| # | Requirement | Priority | Verified By |
|---|------------|----------|-------------|
| 1 | Define golden numbers: id, name, authority_source, current_value, description | MUST | Registry test |
| 2 | Track appearances: every file that mentions a golden number | MUST | Appearance test |
| 3 | Consistency check: authority vs appearances. Report MATCH/DRIFT/MISSING. | MUST | Check test |
| 4 | Drift detection in preflight (REQ-103): YELLOW if drift found | MUST | Preflight test |

### Rondo's Golden Numbers

| # | Requirement | Priority | Verified By |
|---|------------|----------|-------------|
| 5 | `supported_model_count`: number of models Rondo can dispatch to | MUST | Count test |
| 6 | `max_workers`: maximum parallel dispatch workers | MUST | Count test |
| 7 | `task_type_count`: number of task types (review/fix/generate/contradiction/etc.) | MUST | Count test |
| 8 | `exit_code_count`: number of defined exit codes (0/1/2/130) | MUST | Count test |
| 9 | `error_code_count`: number of ERR_* codes in STD-108 | MUST | Count test |
| 10 | `rondo golden` CLI: show all golden numbers with drift status | SHOULD | CLI test |
| 11 | `rondo golden --check` CLI: exit 1 if drift found | SHOULD | Check test |

---

## 10. Rules & Constraints

1. **Authority is singular.** Same as Caliber-STD-110 and OB-REQ-108. One source of truth per number. Violation ID: `STD112-SINGLE-AUTHORITY`
2. **Code > Config > Docs.** Runtime behavior wins over documentation. Violation ID: `STD112-HIERARCHY`

---

## 35. Change History

| Version | Date | What Changed |
|---------|------|-------------|
| 1.0 | 2026-03-20 | Initial. Cross-pollinated from OB-REQ-108. 11 requirements, 5 golden numbers. |
