# STD-007: Spec Quality Checks

*The 28-point checklist that validates specs before any code gets built. Every check proven by catching real bugs.*

**Created:** 2026-03-18 | **Status:** DESIGNED
**Classification:** redacted
**Version:** 0.1
**Owner:** Mark G. Hubers
**Reviewed:** not-yet
**Supersedes:** none
**Universal standard** — same topic number across all products (DEC-017)
**Product:** Rondo
**Matches:** OB-STD-007, Caliber-STD-007, Rondo-STD-007

---

## 1. Purpose & Scope

Defines the 28 checks that every spec must pass before code gets built. These checks are not theoretical — each one earned its place by catching a real bug in a real spec during Sessions 75-79. The checklist is organized into five categories: directional reviews, interface checks, data consistency, structural checks, and deep review. Rondo is the stateless dispatch layer — this standard ensures Rondo's specs are validated before its code is built, with particular attention to the sec/ms duration split and the absence of DB tables.

**IN scope:**
- All 28 checks with pass/fail criteria
- When to run each check (gate mapping)
- Evidence table linking checks to real bugs caught
- Rondo-specific adaptations (stateless design, 446 tests, sec/ms duration split)

**OUT of scope:**
- How OB tracks findings from failed checks (OB-07 domain)
- How Caliber automates these checks (Caliber-STD-007 domain)
- OB or Caliber product-specific adaptations (OB-STD-007, Caliber-STD-007)

---

## 3. Requirements

### Directional Reviews (checks 1-7)

1. **FORWARD** — read spec top-down, verify logical flow. Each section builds on the previous. No forward references to undefined concepts.
2. **REVERSE** — read bottom-up, verify each section stands alone. No section depends on context from a section the reader might not have read.
3. **SIDEWAYS** — cross-layer check. Do products agree on data formats, field names, and protocols at every integration boundary?
4. **CC/V** — cross-cutting concerns + completeness verification. All concerns (security, observability, error handling, accessibility) addressed. No implicit "we'll handle that later."
5. **SPEC-to-CODE** — forward traceability. Every numbered requirement has corresponding Rondo dispatch code that implements it. Applies to Rondo's existing codebase (446 tests).
6. **CODE-to-SPEC** — reverse traceability. Every behavior in Rondo dispatch code is covered by a spec requirement. No undocumented dispatch modes or hidden config options.
7. **CROSS-SPEC** — inter-spec references all point to real specs that reference back. No dangling references. No one-way dependencies.

### Interface Checks (checks 8-10)

8. **WIRING** — IFS contracts match on both sides of every product pair. Rondo-IFS-001 (Claude CLI) and Rondo-IFS-003 (OB) must agree with their counterparts.
9. **TRANSPORT MATCH** — both sides agree on transport method (pipe/file/HTTPS/queue). No spec says "file" when the other says "pipe."
10. **MISSING IFS** — every product pair that communicates has BOTH sides spec'd. If Rondo dispatches for OB, both Rondo-IFS-003 and OB-IFS-004 must exist.

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
19. **HEADING vs FILENAME** — spec title number matches filename number. `STD-007` in the heading matches `STD-007-spec-quality.md` in the filename.
20. **UNIVERSAL NUMBER ALIGNMENT** — STD/SOP numbers mean the same topic in every product. STD-007 is spec quality checks in OB, Caliber, AND Rondo.
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
| 18 | 79 | OB-05 had 3 purposes — split into OB-05 + OB-32 + OB-33 |
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

## 35. Change History

| Version | Date | What Changed |
|---------|------|-------------|
| 0.1 | 2026-03-18 | Initial draft. 28 checks across 5 categories: directional (7), interface (3), data consistency (7), structural (6), deep review (5). Gate mapping, evidence table from Sessions 75-79. Rondo adaptations for stateless design, sec/ms duration split, and 446-test traceability. |
