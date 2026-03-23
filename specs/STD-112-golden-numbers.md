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

## 1. Purpose & Scope

Defines how Rondo tracks golden numbers — the counts that must stay consistent between code, config, and documentation. When docs say "3 models supported" but config allows 5, drift has occurred. This spec catches drift before it becomes a runtime surprise.

**IN scope:** Golden number registry, appearance tracking, drift detection, CLI reporting.
**OUT of scope:** OB golden numbers (OB-REQ-108), Caliber golden numbers (STD-110 (Caliber)).

**Users:** Mark (primary). Claude AI agents dispatching to other models. Future: teams needing multi-model AI orchestration, batch processing, cost optimization across AI providers.

---

## 2. The Problem

Numbers that appear in multiple places drift silently. A new exit code gets added to the code but not to the docs. A new model is supported but the model count in the README is stale. Without golden number tracking, these inconsistencies accumulate until a consumer reads the wrong number and makes a wrong decision.

---

## 3. Requirements


*All requirements use MUST/SHOULD priority per CORE-STD-012.*

| ID | Requirement | Priority | Verified By |
|----|-------------|----------|-------------|
| 001 | Define golden numbers: id, name, authority_source, current_value, description | MUST | Registry test |
| 002 | Track appearances: every file that mentions a golden number | MUST | Appearance test |
| 003 | Consistency check: authority vs appearances. Report MATCH/DRIFT/MISSING. | MUST | Check test |
| 004 | Drift detection in preflight (REQ-103): YELLOW if drift found | MUST | Preflight test |


### Rondo's Golden Numbers

| ID | Requirement | Priority | Verified By |
|----|-------------|----------|-------------|
| 005 | `supported_model_count`: number of models Rondo can dispatch to | MUST | Count test |
| 006 | `max_workers`: maximum parallel dispatch workers | MUST | Count test |
| 007 | `task_type_count`: number of task types (review/fix/generate/contradiction/etc.) | MUST | Count test |
| 008 | `exit_code_count`: number of defined exit codes (0/1/2/130) | MUST | Count test |
| 009 | `error_code_count`: number of ERR_* codes in STD-108 | MUST | Count test |
| 010 | `rondo golden` CLI: show all golden numbers with drift status | SHOULD | CLI test |
| 011 | `rondo golden --check` CLI: exit 1 if drift found | SHOULD | Check test |


---

## 4. Architecture / Design

Golden numbers are stored in a registry (Python dict or TOML file) with each entry defining: `id`, `name`, `authority_source` (the file/line that IS the truth), `current_value`, and `description`. A scanner walks all files to find appearances of each number and compares against the authority source.

---

## 5. Data Model

Registry entry: `{id: str, name: str, authority_source: str, current_value: int, description: str}`. Appearance: `{golden_id: str, file: str, line: int, found_value: int}`. Drift report: `{golden_id: str, authority_value: int, appearances: list[Appearance], status: "MATCH"|"DRIFT"|"MISSING"}`.

---

## 6. Data Boundary

Golden numbers are internal to Rondo's development process. They do not cross product boundaries. OB and Caliber maintain their own golden number registries. The shared concept (from OB-REQ-108) is the pattern, not the data.

---

## 7. MCP / API Interface

No MCP interface. Golden numbers are a development-time check, not a runtime service. CORE-IFS-005 MCP tools do not expose golden number queries. The `rondo golden` CLI is the query interface.

---

## 8. States & Modes

Each golden number has one of three drift states: `MATCH` (authority = all appearances), `DRIFT` (authority != some appearance), `MISSING` (authority exists but no appearances found — orphaned number). Preflight shows YELLOW for any non-MATCH state.

---

## 9. Configuration

Golden number registry location: `rondo/golden-numbers.toml` or inline in `config.py`. Not configurable per environment — golden numbers are the same everywhere. Drift detection threshold: exact match only (no tolerance for "close enough").

---

## 10. Rules & Constraints

1. **Authority is singular.** Same as STD-110 (Caliber) and OB-REQ-108. One source of truth per number. Violation ID: `STD112-SINGLE-AUTHORITY`
2. **Code > Config > Docs.** Runtime behavior wins over documentation. Violation ID: `STD112-HIERARCHY`

---

## 11. Quality Attributes

- **Single source of truth:** Each golden number has exactly one authority source.
- **Automated detection:** Drift found by scanner, not by human review.
- **Preflight integration:** Drift is visible before work starts, not discovered mid-build.

---

## 12. Shared Patterns

- **Golden number pattern:** Cross-pollinated from OB-REQ-108, adapted for dispatch counts.
- **Authority hierarchy:** Code > Config > Docs. Same priority as COALESCE (STD-102).
- **Preflight check:** Same integration point as STD-103 test results and STD-106 spec quality.

---

## 13. Integration Points

| Integration | What Crosses | Standard Enforced |
|-------------|-------------|-------------------|
| STD-112 → Preflight | Drift status shown at session start | YELLOW if drift found |
| STD-112 → STD-103 | Test count is a golden number | Coverage ratchet |
| STD-112 → STD-105 | Model count is a golden number | Model allowlist |
| STD-112 → CORE-STD-012 | Golden number health feeds readiness | Prerequisite check |

---

## 14. Standards Applied

| Standard | How It Applies |
|----------|---------------|
| OB-REQ-108 | Origin pattern — Rondo adapts golden numbers from methodology to dispatch counts |
| CORE-STD-012 | Requirement readiness — golden number drift blocks READY state |
| CORE-STD-013 | TrackerData — drift events are trackable for trend analysis |
| CORE-IFS-005 | MCP standard — golden numbers not exposed via MCP (development-time only) |

---

## 15. Self-Correction

Golden numbers are a self-correction mechanism for documentation drift. When code adds a new model but docs are stale, the scanner detects the mismatch. This is CORE-STD-011 applied to counts: the system detects its own inconsistency and reports it for correction.

---

## 16. Assumptions

1. Authority sources are machine-parseable (Python constants, TOML values, not prose).
2. Appearances can be found by text search (the number appears literally in files).
3. Golden numbers change infrequently — drift detection runs at preflight, not continuously.
4. Five golden numbers is sufficient for Rondo v1.0 — more added as the product grows.

---

## 17. Success Criteria

| # | Criterion | How to Verify |
|---|-----------|---------------|
| 1 | New model added → golden number drift detected in preflight | Drift test |
| 2 | `rondo golden` shows all 5 numbers with MATCH status | CLI test |
| 3 | `rondo golden --check` exits 1 when drift exists | Exit code test |

---

## 18. Build Notes / Estimate

Registry definition: 1 hour. Scanner (file walk + regex): 2 hours. CLI (`rondo golden`, `rondo golden --check`): 2 hours. Preflight integration: 1 hour. Total: ~6 hours.

---

## 19. Test Categories

| Category | What It Tests |
|----------|--------------|
| Registry tests | Golden number definition, authority source validation |
| Scanner tests | Appearance detection, drift reporting |
| CLI tests | `rondo golden` output format, `--check` exit codes |
| Preflight tests | YELLOW status when drift found |

---

## 20. Failure Modes

| Failure | Impact | Mitigation |
|---------|--------|------------|
| Authority source moved | Scanner reports MISSING (false alarm) | Update registry when refactoring |
| Number appears in comment | False appearance detected | Scanner uses context-aware matching |
| New golden number not registered | Drift goes undetected | Review golden numbers when adding features |

---

## 21. Dependencies + Used By

| Direction | Spec | Relationship |
|-----------|------|-------------|
| Depends on | REQ-100 | Core defines task types, models, exit codes being counted |
| Depends on | STD-102 | Config defines model list and worker limits |
| Depends on | CORE-STD-012 | Readiness tracking — drift blocks READY |
| Used by | REQ-103 | Preflight displays golden number drift |

---

## 22. Decisions

| Decision | Rationale | Date |
|----------|-----------|------|
| D1: 5 golden numbers for v1.0 | model count, max workers, task types, exit codes, error codes — covers the critical counts | 2026-03-20 |
| D2: Code > Config > Docs | Runtime behavior is the ultimate truth — docs are derived | 2026-03-20 |
| D3: Exact match only | "Close enough" is still wrong for counts | 2026-03-20 |

---

## 23. Open Questions

1. Should golden numbers include spec count and convention count (from STD-103)?
2. Should drift history be tracked over time for trend analysis?

---

## 24. Glossary

| Term | Definition |
|------|-----------|
| **Golden number** | A count that must be consistent across code, config, and docs |
| **Authority source** | The single file/line that IS the truth for a golden number |
| **Drift** | When an appearance of a golden number disagrees with its authority |

---

## 25. Risk / Criticality

**MEDIUM.** Golden number drift causes confusion (wrong docs, wrong assumptions) but not runtime failures. The main risk is stale documentation that misleads consumers. Preflight integration makes drift visible early.

---

## 26. External Scan

Golden numbers are an internal pattern from OB-REQ-108. No external framework for tracking code/doc count consistency. The concept is similar to "assertion counting" in formal verification but applied to documentation.

---

## 27. Security Considerations

No direct security impact. Golden numbers track counts, not secrets. The `error_code_count` golden number indirectly supports security by ensuring all error codes are documented (no undocumented error paths).

---

## 28. Performance / Resource

Scanner runs once at preflight (~100ms for a small codebase). No runtime overhead. Golden number registry is a small file (<1KB). No performance concerns.

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

CORE-STD-012 (Requirement Readiness) uses golden number health as a readiness signal — if counts are drifting, the system is not in a consistent state. CORE-STD-013 (TrackerData) could ingest drift events for cross-session trend analysis. CORE-IFS-005 is not applicable — golden numbers are development-time only.

---

### Feature Maturity

| Feature | Maturity | Evidence | Retest |
|---------|----------|----------|--------|
| Golden number definitions | THEORY | Specced for Rondo-specific quality thresholds | Phase 1 build |
| Drift detection | THEORY | Specced for automated drift alerting | Phase 2 build |
| Threshold auto-adjustment | THEORY | Specced for data-driven tuning | Phase 3 build |


## 35. Change History

| Version | Date | What Changed |
|---------|------|-------------|
| 1.0 | 2026-03-20 | Initial. Cross-pollinated from OB-REQ-108. 11 requirements, 5 golden numbers. |
| 1.1 | 2026-03-22 | Filled to 35 sections. Added CORE-STD-012, CORE-STD-013, CORE-IFS-005 refs. Approval record (Mark, Session 84). |
