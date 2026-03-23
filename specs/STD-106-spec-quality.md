# STD-106: Spec Quality Checks

*The 28-point checklist that validates specs before any code gets built. Every check proven by catching real bugs.*

**Created:** 2026-03-18 | **Status:** DESIGNED
**Classification:** redacted
**Version:** 0.1
**Owner:** Mark G. Hubers
**Reviewed:** not-yet
**Supersedes:** none
**Universal standard** — same topic number across all products (DEC-017)
**Product:** Rondo
**Matches:** CORE-STD-007, Caliber-STD-106, Rondo-STD-106

---

## 1. Purpose & Scope

Defines the 28 checks that every spec must pass before code gets built. These checks are not theoretical — each one earned its place by catching a real bug in a real spec during Sessions 75-79. The checklist is organized into five categories: directional reviews, interface checks, data consistency, structural checks, and deep review. Rondo is the stateless dispatch layer — this standard ensures Rondo's specs are validated before its code is built, with particular attention to the sec/ms duration split and the absence of DB tables.

**IN scope:**
- All 28 checks with pass/fail criteria
- When to run each check (gate mapping)
- Evidence table linking checks to real bugs caught
- Rondo-specific adaptations (stateless design, 446 tests, sec/ms duration split)

**OUT of scope:**
- How OB tracks findings from failed checks (OB-REQ-105 domain)
- How Caliber automates these checks (Caliber-STD-106 domain)
- OB or Caliber product-specific adaptations (CORE-STD-007, Caliber-STD-106)

**Users:** Mark (primary). Claude AI agents dispatching to other models. Future: teams needing multi-model AI orchestration, batch processing, cost optimization across AI providers.

---

## 2. The Problem

Specs are the source of truth for code. A bug in a spec becomes a bug in every implementation. Sessions 75-79 proved this: severity mismatches, heading/filename drift, dangling cross-references, and multi-purpose specs all produced real code defects. The 28-point checklist catches these before code is built, not after.

---

## 3. Requirements

*All requirements in this spec are MUST priority unless marked SHOULD.*

### Directional Reviews (checks 1-7)

1. **FORWARD** — read spec top-down, verify logical flow. Each section builds on the previous. No forward references to undefined concepts.
2. **REVERSE** — read bottom-up, verify each section stands alone. No section depends on context from a section the reader might not have read.
3. **SIDEWAYS** — cross-layer check. Do products agree on data formats, field names, and protocols at every integration boundary?
4. **CC/V** — cross-cutting concerns + completeness verification. All concerns (security, observability, error handling, accessibility) addressed. No implicit "we'll handle that later."
5. **SPEC-to-CODE** — forward traceability. Every numbered requirement has corresponding Rondo dispatch code that implements it. Applies to Rondo's existing codebase (446 tests).
6. **CODE-to-SPEC** — reverse traceability. Every behavior in Rondo dispatch code is covered by a spec requirement. No undocumented dispatch modes or hidden config options.
7. **CROSS-SPEC** — inter-spec references all point to real specs that reference back. No dangling references. No one-way dependencies.

### Interface Checks (checks 8-10)

8. **WIRING** — IFS contracts match on both sides of every product pair. Rondo-IFS-100 (Claude CLI) and Rondo-IFS-102 (OB) must agree with their counterparts.
9. **TRANSPORT MATCH** — both sides agree on transport method (pipe/file/HTTPS/queue). No spec says "file" when the other says "pipe."
10. **MISSING IFS** — every product pair that communicates has BOTH sides spec'd. If Rondo dispatches for OB, both Rondo-IFS-102 and OB-IFS-103 must exist.

### Data Consistency Checks (checks 11-17)

11. **FIELD CONSISTENCY** — same field names across products, verified against NAMING-MAP.md. `cost_usd` is `cost_usd` everywhere. DispatchUsage field names match NAMING-MAP.md exactly.
12. **STATUS VOCABULARY** — all products use the same status values: `done`, `partial`, `error`, `skipped`, `blocked`, `pending`, `in_progress`. No synonyms.
13. **SEVERITY VOCABULARY** — all products use the same severity values: `block`, `warn`, `info`. Where AI returns different terms (critical/warning/nit), the mapping is documented and enforced in code before results leave Rondo.
14. **TIMESTAMP FORMAT** — ISO 8601 UTC everywhere. No local time. No epoch-only fields without documented conversion.
15. **DURATION UNITS** — documented per level. Rondo uses the sec/ms split: `duration_ms` for individual dispatch calls (millisecond precision), `duration_sec` for round-level summaries (second precision). This split is intentional and must be consistent across all Rondo specs.
16. **COST FIELDS** — `cost_usd`, `input_tokens`, `output_tokens` consistent everywhere. Same types, same precision, same null handling. DispatchUsage fields are the canonical source.
17. **CONFIG PATTERN** — COALESCE order (CLI > env > file > default) consistent everywhere. Rondo model selection follows this chain: `--model` flag > `task.model` hint > `config.default_model` > `"sonnet"`.

### Structural Checks (checks 18-23)

18. **ONE PURPOSE** — spec can be described in one sentence without "and." If not, split it.
19. **HEADING vs FILENAME** — spec title number matches filename number. `STD-106` in the heading matches `STD-106-spec-quality.md` in the filename.
20. **UNIVERSAL NUMBER ALIGNMENT** — STD/SOP numbers mean the same topic in every product. STD-106 is spec quality checks in OB, Caliber, AND Rondo.
21. **TABLE OWNERSHIP** — spec declares which DB tables it owns. For Rondo: this check confirms Rondo owns NO tables (stateless by design). Any spec claiming a DB table is a design violation.
22. **REQUIRED SECTIONS** — all sections marked "REQUIRED" in the spec template are filled before build. No placeholder text, no "TBD" in required fields.
23. **STALE REFERENCE** — no docs say "NOT YET" for things that ARE done. After completing work, update all references.

### Deep Review Checks (checks 24-28)

24. **DEEP REVIEW v1** — cross-spec vocabulary audit. Two specs never use different words for the same concept. Consistent terminology across all Rondo specs.
25. **DEEP REVIEW v2** — "can I write a test from this requirement?" must be YES for every numbered requirement. Vague requirements fail this check.
26. **CROSS-FIELD** — related numeric fields have logical ordering. `min < max`, `timeout > retry_delay`, `warn_threshold < error_threshold`. No contradictory ranges. The watchdog_timeout >= task_timeout gap (Session 75) was caught by this check.
27. **DEPENDENCY GRAPH** — "Depends on" references don't create circular dependencies. If A depends on B and B depends on A, one dependency is wrong.
28. **ORPHAN CHECK** — no spec that nobody references (orphan spec), no requirement that nothing implements (orphan req). Every spec and every requirement must be connected to the graph.

---

## 4. Architecture / Design

The 28 checks are organized into 5 categories executed in order: directional reviews (1-7), interface checks (8-10), data consistency (11-17), structural checks (18-23), deep review (24-28). Each category targets a different failure mode. The checks can be run manually or automated via Caliber dispatches through Rondo.

---

## 5. Data Model

Check results are captured as findings: check number, pass/fail, spec name, description of violation, evidence (line number or cross-reference). Findings feed into OB's audit trail (OB-REQ-105) or Rondo's spool files when checks are automated.

---

## 6. Data Boundary

Spec quality checks read specs (input) and produce findings (output). The boundary is spec files on one side and finding records on the other. Rondo's own specs are validated by these checks. When automated via Caliber, findings go to spool files per STD-101.

---

## 7. MCP / API Interface

No direct MCP interface. Spec quality checks are run as Rondo tasks (dispatched to Claude for deep review) or as local scripts (structural checks). CORE-IFS-005 MCP tools could expose check results in future via consumer stores.

---

## 8. States & Modes

Checks run in two modes: manual (human-driven review using the checklist) and automated (Caliber dispatches checks through Rondo). Both modes use the same 28 checks. Automated mode produces machine-parseable findings; manual mode produces review notes.

---

## 9. Configuration

No configuration — the 28 checks are fixed. Check thresholds (e.g., what constitutes a "structural" vs "deep" check) are defined in this spec, not in config files. The check list is versioned with the spec, not with config.

---

## 10. Rules & Constraints

### When to Run

| Gate | Which Checks | Minimum |
|------|-------------|---------|
| ORB-03 exit (specs written) | 18-23 (structural) | All must pass |
| ORB-04 (spec review) | 1-7 (directional) + 24-28 (deep) | All must pass |
| Before any build | 8-17 (interface + data) | All must pass |
| After any spec change | 7, 11-13, 19, 23 (quick validation) | Re-run affected |
| Monthly | ALL 28 | Full audit |

### Evidence — Real Bugs Caught

| Check # | Session | What It Caught |
|---------|---------|---------------|
| 13 | 79 | Severity mismatch: AI returns critical/warning/nit, OB stores block/warn/info. Would have been runtime error. |
| 19 | 79 | 9 SOP files with heading numbers not matching filenames |
| 18 | 79 | OB-REQ-103 had 3 purposes — split into OB-REQ-103 + OB-REQ-127 + OB-REQ-128 |
| 23 | 79 | INTEGRATION-ARCHITECTURE.md said 3 specs "NOT YET" when they were done |
| 7 | 79 | Zero broken cross-references across 73+ specs after massive renumbering |
| 24 | 77 | Gemini found 5 vocabulary inconsistencies across OB specs |
| 26 | 75 | Google AI found watchdog_timeout >= task_timeout gap |
| CROSS-SPEC | 75 | 30 issues (5 build-blockers) found in Rondo cross-spec review |

### Rondo-Specific Adaptations

- Checks 5-6 apply to Rondo's dispatch code (446 tests). Every dispatch behavior, config option, and error path must trace to a spec requirement and back.
- Check 15 documents the sec/ms split: `duration_ms` for individual dispatches, `duration_sec` for round summaries. This is the most common consistency error in Rondo specs.
- Check 21 confirms Rondo owns NO database tables. Rondo is stateless by design. Any spec claiming table ownership is a design violation — Rondo produces DispatchUsage objects, consumers (OB) persist them.
- Check 26 is where Rondo's watchdog_timeout >= task_timeout gap was caught in Session 75. Numeric field ordering is critical for timeout/retry logic.

---

## 11. Quality Attributes

- **Completeness:** 28 checks cover directional, interface, data, structural, and deep review dimensions.
- **Evidence-backed:** Every check earned its place by catching a real bug (evidence table in section 10).
- **Testable:** Each check has clear pass/fail criteria — no subjective judgment calls.

---

## 12. Shared Patterns

- **Multi-directional review:** FORWARD + REVERSE + SIDEWAYS + CC/V. Same pattern used in ACE Orbit methodology at every major step.
- **Cross-spec vocabulary audit:** Check 24. Same pattern used across OB, Caliber, and Rondo specs.
- **Traceability matrix:** Checks 5-6. Spec→Code and Code→Spec tracing shared with VER-100.

---

## 13. Integration Points

| Integration | What Crosses | Standard Enforced |
|-------------|-------------|-------------------|
| STD-106 → Caliber | Automated checks dispatched via Rondo | STD-101 finding format |
| STD-106 → OB | Findings stored in OB audit trail | OB-REQ-105 finding schema |
| STD-106 → NAMING-MAP.md | Check 11 verifies field consistency | STD-100 conventions |
| STD-106 → CORE-STD-012 | Spec quality gates requirement readiness | Readiness prerequisites |

---

## 14. Standards Applied

| Standard | How It Applies |
|----------|---------------|
| CORE-STD-007 | Parent spec quality standard — 28 checks adapted per product |
| CORE-STD-012 | Requirement readiness — spec quality checks must pass before READY |
| CORE-STD-013 | TrackerData — check results are trackable events |
| CORE-IFS-005 | MCP standard — check results queryable via consumer MCP tools |

---

## 15. Self-Correction

Spec quality checks are a self-correction mechanism for the specification layer. Each check that fails produces a finding that must be resolved before build. The evidence table (section 10) shows which checks caught real bugs — this history refines the checklist over time (CORE-STD-011 pattern applied to specs, not code).

---

## 16. Assumptions

1. All specs follow the 35-section template (CORE-STD-000).
2. NAMING-MAP.md is current and reflects actual cross-product field names.
3. Cross-references between specs use stable identifiers (spec numbers, not filenames).
4. Automated checks via Caliber produce the same results as manual checks.

---

## 17. Success Criteria

| # | Criterion | How to Verify |
|---|-----------|---------------|
| 1 | All 28 checks pass on every Rondo spec before build | Gate check |
| 2 | Zero dangling cross-references across Rondo spec set | Check 7 |
| 3 | NAMING-MAP.md alignment: zero DRIFT entries for Rondo fields | Check 11 |
| 4 | Every numbered requirement is testable (can write a test from it) | Check 25 |

---

## 18. Build Notes / Estimate

Automated structural checks (18-23): 3 hours (script to validate headings, filenames, sections). Automated data checks (11-17): 4 hours (NAMING-MAP.md parser, status vocabulary validator). Directional and deep checks: manual, ~2 hours per spec. Total automation: ~7 hours.

---

## 19. Test Categories

| Category | What It Tests |
|----------|--------------|
| Structural check tests | Heading/filename match, required sections present |
| Data consistency tests | NAMING-MAP.md alignment, status vocabulary |
| Cross-reference tests | All refs point to existing specs, bidirectional |
| Evidence regression tests | Bugs from evidence table stay caught |

---

## 20. Failure Modes

| Failure | Impact | Mitigation |
|---------|--------|------------|
| New spec skips checks | Bugs enter code from unvalidated spec | Gate enforcement at ORB-03/ORB-04 |
| Check produces false positive | Valid spec blocked unnecessarily | Review check definition, update criteria |
| NAMING-MAP.md stale | Check 11 passes but names are actually wrong | Monthly NAMING-MAP.md refresh |

---

## 21. Dependencies + Used By

| Direction | Spec | Relationship |
|-----------|------|-------------|
| Depends on | CORE-STD-007 | Parent spec quality standard |
| Depends on | CORE-STD-000 | Spec template defines required sections |
| Depends on | CORE-STD-012 | Readiness tracking for spec quality gates |
| Used by | All Rondo specs | Every spec must pass these 28 checks |
| Used by | VER-100 | Verification spec references traceability checks |

---

## 22. Decisions

| Decision | Rationale | Date |
|----------|-----------|------|
| D1: 28 checks, not fewer | Each earned its place by catching a real bug. No theoretical checks. | 2026-03-18 |
| D2: Evidence table mandatory | Every check must cite the session/bug it caught. No unjustified checks. | 2026-03-18 |
| D3: Rondo-specific adaptations | Stateless design, sec/ms split, no-DB ownership need product-specific checks | 2026-03-18 |

---

## 23. Open Questions

None currently. The 28-check set is stable after Session 79 cross-spec review.

---

## 24. Glossary

| Term | Definition |
|------|-----------|
| **Directional review** | Reading a spec in a specific direction (forward, reverse, sideways) to catch different bug types |
| **Cross-spec review** | Comparing multiple specs for vocabulary consistency and reference integrity |
| **Convention check** | Verifying that a spec follows naming, numbering, and structural conventions |

---

## 25. Risk / Criticality

**HIGH.** Spec quality is the foundation of code quality. A bad spec produces bad code, bad tests, and bad reviews. The 28-check gate is the primary defense against spec-level defects propagating to the codebase.

---

## 26. External Scan

DoD/NASA verification practices inspired the multi-directional review approach. Google's AI reviewer (Gemini) was used for independent cross-spec review (Session 77). No commercial spec quality tool covers AI-specific checks like the sec/ms split or stateless ownership verification.

---

## 27. Security Considerations

Check 21 (table ownership) prevents Rondo from accidentally claiming database tables — a design violation that could create security surface. Checks 5-6 (traceability) ensure no undocumented dispatch behavior exists that could be exploited. No direct security impact from the checks themselves.

---

## 28. Performance / Resource

Manual review: ~2 hours per spec (all 28 checks). Automated structural/data checks: ~30 seconds per spec. Full Rondo spec set (15 specs): ~30 hours manual or ~8 minutes automated for automatable checks. Human review for directional/deep checks cannot be automated.

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

CORE-STD-012 (Requirement Readiness) requires spec quality checks to pass before any requirement reaches READY state. CORE-STD-013 (TrackerData) records check results for trend analysis (are specs getting better over time?). CORE-IFS-005 MCP tools could expose spec quality dashboards in future versions.

---

## 35. Change History

| Version | Date | What Changed |
|---------|------|-------------|
| 0.1 | 2026-03-18 | Initial draft. 28 checks across 5 categories: directional (7), interface (3), data consistency (7), structural (6), deep review (5). Gate mapping, evidence table from Sessions 75-79. Rondo adaptations for stateless design, sec/ms duration split, and 446-test traceability. |
| 0.2 | 2026-03-22 | Filled to 35 sections. Added CORE-STD-012, CORE-STD-013, CORE-IFS-005 refs. Approval record (Mark, Session 84). |
