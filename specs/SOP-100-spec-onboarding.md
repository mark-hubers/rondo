# SOP-100: Spec Onboarding Procedure

*How to add or create specs for Rondo. The rules any contributor must follow.*

**Created:** 2026-03-18 | **Updated:** 2026-03-22 | **Status:** DESIGNED
**Classification:** open
**Version:** 0.2
**Owner:** Mark G. Hubers
**Reviewed:** not-yet
**Supersedes:** none
**Universal procedure** — same topic number across all products (DEC-017)
**Product:** Rondo
**Matches:** OB-SOP-100, SOP-100 (Caliber), SOP-100 (Rondo)
**References:** CORE-STD-012 (Requirement Readiness), CORE-STD-013 (TrackerData), CORE-STD-021 (MCP Standard)
**Depends on:** STD-100, CORE-STD-000, SOP-101, STD-105, REQ-100, SOP-102, STD-108, STD-109, Rondo-IFS-102

---

## 1. Purpose & Scope

**What this SOP does:** Defines the procedure for creating, numbering, reviewing, and
maintaining specs within the Rondo product. Ensures consistency with the 7-category
DoD/NASA-aligned spec naming system and cross-product compatibility.

**IN scope:**
- Spec categories and numbering
- Universal standards (STD-100 to STD-105)
- File naming and location
- Template requirements (35-section standard)
- Review process
- Cross-reference conventions

**OUT scope:**
- Spec CONTENT standards (CORE-STD-000 owns template structure)
- Build process (SOP-101 owns that)
- Release process (SOP-102 owns that)

**Users:** Mark (primary). Claude AI agents dispatching to other models. Future: teams needing multi-model AI orchestration, batch processing, cost optimization across AI providers.

---

## 2. The Problem

Without a consistent onboarding procedure, specs end up with inconsistent numbering, missing
sections, wrong directories, and conflicting cross-references. New contributors don't know
where to put things or what format to use. This SOP eliminates ambiguity by defining
one procedure for all Rondo spec operations.

---

## 3. Requirements


*All requirements use MUST/SHOULD priority per CORE-STD-012.*

| ID | Requirement | Priority |
|----|-------------|----------|
| 001 | All Rondo specs use the 7-category system (REQ, STD, SOP, IFS, VER, TST, ADR) | MUST |
| 002 | All specs use the 35-section template from CORE-STD-000 | MUST |
| 003 | Universal standards (STD-100 to STD-105) match topic numbers across products | MUST |
| 004 | Spec numbers 001-019 are reserved for universal topics | MUST |
| 005 | Spec numbers 020+ are product-specific to Rondo | MUST |
| 006 | All specs live in `rondo/specs/` | MUST |
| 007 | No product prefix in filenames (bare category prefix) | MUST |
| 008 | Required sections filled before spec is referenced by a build sprint | MUST |
| 009 | Cross-references follow the format conventions in section 7 | SHOULD |
| 010 | Every spec passes Phase 5 review ("Can I write a test from this?") | MUST |


## 4. Architecture / Design

### Spec Categories (7 Categories — DoD/NASA-Aligned)

| Prefix | Category | Purpose | Example |
|--------|----------|---------|---------|
| REQ | Requirements | What Rondo must do | REQ-100 (Core), REQ-101 (Automation) |
| STD | Standards | How code must be written | STD-108 (Error Resilience), STD-109 (Configuration) |
| SOP | Procedures | How to do things (step-by-step) | SOP-101 (Build & Run), SOP-102 (Release) |
| IFS | Interfaces | How Rondo connects to other products | Rondo-IFS-100 (Claude CLI), Rondo-IFS-102 (OB Integration) |
| VER | Verification | How to prove specs are implemented | VER-100 (Verification Matrix) |
| TST | Test Plans | Detailed test strategies | (not yet created) |
| ADR | Decisions | Why we chose X over Y | (not yet created) |

---

## 5. Data Model

**Concurrency:** All spec metadata writes use file-level locking. Concurrent onboarding edits are serialized to prevent header corruption.

Not applicable — this is a procedure, not a data-producing spec. Spec metadata (title,
status, version, dependencies) lives in each spec's YAML-like header.

---

## 6. Data Boundary

### Universal Standards (STD-100 to STD-105)

Every product has these 6 standards with the same number and topic:

| Number | Topic | What It Covers |
|--------|-------|----------------|
| STD-100 | Data Standards | Naming, types, boundaries, validation |
| STD-101 | Observability | Logging, metrics, alerting |
| STD-102 | Configuration | Config resolution, COALESCE pattern |
| STD-103 | Quality | Coverage floors, complexity caps |
| STD-104 | Infrastructure | Containers, deployment, CI/CD |
| STD-105 | AI Operations | AI-specific patterns, prompt discipline |

Content is adapted for Rondo's context. The number and topic are the same across products.

---

## 7. MCP / API Interface

Not applicable for this SOP. Future: CORE-STD-021 MCP tools could query spec metadata
(list specs, check completeness, find missing sections) to support automated spec auditing.

---

## 8. States & Modes

Spec lifecycle states:

| State | Meaning | Next |
|-------|---------|------|
| **RESERVED** | Number and title claimed, stub file created | DRAFT |
| **DRAFT** | Required sections being filled | DESIGNED |
| **DESIGNED** | All required sections filled, ready for review | REVIEWED |
| **REVIEWED** | Passed Phase 5 review | APPROVED |
| **APPROVED** | Can be referenced by build sprints | — |

**State Machine Type:** FORWARD-ONLY
**Rationale:** Spec lifecycle is strictly forward: RESERVED → DRAFT → DESIGNED → REVIEWED → APPROVED. No backward transitions — a spec that fails review stays at DESIGNED until it passes.
**Rollback:** Not applicable — specs move forward only. Defects create findings, not state reversals.

---

## 9. Configuration

### Numbering Rules

| Range | Scope | Rule |
|-------|-------|------|
| 001-019 | Universal | Same topic across all products. Never product-specific. |
| 020+ | Product-specific | Unique to Rondo. Free to number as needed. |

**Rondo-specific examples:** STD-108 (Error Resilience), STD-109 (Configuration), STD-110 (Concurrency Safety), STD-111 (Code Quality).

---

## 10. Rules & Constraints

1. **35-section template is mandatory.** Not all sections need content, but all section headings must be present. Violation ID: `SOP100-35-SECTIONS`
2. **Phase 5 before build.** No build sprint references a spec that hasn't passed "Can I write a test from this?" Violation ID: `SOP100-PHASE5`
3. **No number collisions.** Check existing specs before picking a number. Violation ID: `SOP100-NO-COLLISION`
4. **Universal numbers are sacred.** 001-019 never get product-specific content. Violation ID: `SOP100-UNIVERSAL-SACRED`

### Template

Use the 35-section template defined in CORE-STD-000-spec-standard.md. All specs must include at minimum:

**Required sections:** Purpose & Scope, The Problem, Requirements, Architecture/Design, Data Model, Data Boundary, Integration Points, Assumptions, Success Criteria, Dependencies + Used By, Decisions, Change History.

**Optional sections:** MCP/API Interface, States & Modes, Configuration, Quality Attributes, Shared Patterns, Self-Correction, and all AI sections (29-34).

---

## 11. Quality Attributes

| Attribute | Target | Rationale |
|-----------|--------|-----------|
| Consistency | All Rondo specs follow the same structure | Predictable format reduces cognitive load |
| Completeness | Required sections filled before build | Prevents building from incomplete specs |
| Traceability | Every spec has depends-on and used-by | Enables impact analysis |
| Cross-product alignment | Universal numbers match across products | Enables cross-product comparison |

---

## 12. Shared Patterns

### Where Specs Live

```
rondo/specs/                 # All Rondo specs
├── REQ-NNN-name.md          # Requirements
├── STD-NNN-name.md          # Standards
├── SOP-NNN-name.md          # Procedures
├── IFS-NNN-name.md          # Interfaces
├── VER-NNN-name.md          # Verification
├── TST-NNN-name.md          # Test plans
└── ADR-NNN-name.md          # Decisions
```

No product prefix in filenames (same convention as Caliber). Rondo specs use bare category prefixes.

---

## 13. Integration Points

### How to Add a New Spec

1. Determine the category (REQ, STD, SOP, IFS, VER, TST, ADR)
2. Check existing specs for naming conflicts
3. Pick the next available number in the appropriate range
4. Copy the 35-section template from CORE-STD-000
5. Fill required sections (minimum viable spec)
6. Add header: title, description, created date, status, depends-on, used-by
7. Commit with message: `Add Rondo [PREFIX]-NNN: brief description`

### Cross-References

When referencing specs from other products:

| Referencing | Format | Example |
|-------------|--------|---------|
| Rondo spec from Rondo | `SOP-100` or `REQ-100` | "See REQ-100 (Core)" |
| OB spec from Rondo | `OB-NN` or `OB-SOP-NNN` | "OB-SOP-100 defines build integration" |
| Caliber spec from Rondo | `Caliber SOP-101` | "Caliber SOP-101 defines the build flow" |
| Cross-product interface | `IFS-NNN` with product context | "Rondo-IFS-102 defines OB integration" |

Use IFS specs to formally define integration points between products.

---

## 14. Standards Applied

| Standard | How Applied |
|----------|-------------|
| CORE-STD-000 (Spec Standard) | 35-section template used for all specs |
| CORE-STD-007 (Spec Quality) | Phase 5 review gate before build |
| CORE-STD-012 (Requirement Readiness) | Readiness tracking for each requirement |
| CORE-STD-013 (TrackerData) | Spec creation/update events as trackerdata |
| CORE-STD-021 (MCP Standard) | Future MCP tool for spec metadata queries |
| DEC-017 | Universal numbering across products |

---

## 15. Self-Correction

- If a spec is referenced by a build sprint but hasn't passed Phase 5 review, the build
  preflight (SOP-101) should flag it: "Spec REQ-NNN not yet reviewed — build may fail."
- If numbering conflicts are detected (two specs with same number), the build system
  should flag it at commit time via pre-commit hook.
- If cross-references point to nonexistent specs, the spec scanner should detect and
  report broken references.

### Review Process

1. Spec must pass OB's 9-phase spec refinement process (CORE-SOP-006, ORB-03)
2. At minimum, Phase 5 must pass: "Can I write a test from this spec?" = yes
3. Cross-spec vocabulary check against existing Rondo specs
4. Rondo-specific: verify task API contracts are complete (input schema, output schema, error types)
5. Spec must be reviewed before any build sprint references it

---

## 16. Assumptions

| # | Assumption | If Wrong |
|---|-----------|----------|
| A1 | 7 categories are sufficient for all spec types | May need additional categories |
| A2 | 35-section template is appropriate for all spec sizes | Small specs may have many empty sections |
| A3 | Universal numbering (001-019) won't exhaust | 19 slots for universal topics is sufficient |
| A4 | Markdown format is permanent | Migration to structured DB would require conversion |

---

## 17. Success Criteria

| # | Criterion | How to Verify |
|---|-----------|---------------|
| 1 | All new specs use 7-category naming | Audit spec filenames |
| 2 | All specs have 35 section headings | Automated section counter |
| 3 | No number collisions | Scan for duplicate NNN values per category |
| 4 | Phase 5 passed before build reference | Build preflight check |

---

## 18. Build Notes / Estimate

Not applicable — this is a process SOP, not a buildable feature.

---

## 19. Test Categories

| Category | What | Count (est.) |
|----------|------|-------------|
| Automation | Section counter script validates 35 sections | 1 |
| Automation | Number collision detector | 1 |
| Manual | Phase 5 review checklist | Per spec |

### NAMING-MAP.md

Before adding new data structures (classes, config keys, task types):

1. Check existing specs for naming conventions (especially STD-100, REQ-100)
2. Check OB's `ace/ID-CHEATSHEET.md` for cross-product naming
3. Ensure no name collision with Rondo's existing task types or config keys
4. Rondo-specific: check `rondo.toml` schema for config key naming

---

## 20. Failure Modes

| Failure | Impact | Mitigation |
|---------|--------|------------|
| Spec created without template | Missing required sections | Pre-commit hook validates structure |
| Number collision | Ambiguous references | Collision detector in CI |
| Spec not reviewed before build | Build from incomplete spec | Preflight check |
| Cross-reference broken | Misleading dependency chains | Automated reference checker |

**Emergency Bypass:** BREAK_GLASS override via `break_glass_events` table audit trail (CORE-STD-015). Spec onboarding guards (35-section template, Phase 5 review gate) can be bypassed under DR mode with human approval for urgent spec additions.

---

## 21. Dependencies + Used By

| Depends On | Why |
|------------|-----|
| CORE-STD-000 | 35-section template definition |
| CORE-STD-007 | Spec quality standards |
| DEC-017 | Universal numbering convention |

| Used By | Why |
|---------|-----|
| All Rondo specs | This SOP defines how they are created and maintained |
| SOP-101 | Build procedure references spec readiness |

---

## 22. Decisions

| # | Decision | Date | Why |
|---|----------|------|-----|
| D1 | 7-category system (DoD/NASA-aligned) | 2026-03-18 | Industry-proven categorization |
| D2 | Bare prefix filenames (no product prefix) | 2026-03-18 | Matches Caliber convention, simpler filenames |
| D3 | Universal numbers 001-019 reserved | 2026-03-18 | Cross-product alignment |
| D4 | Phase 5 gate before build | 2026-03-18 | Prevents building from untestable specs |

---

## 23. Open Questions

| # | Question | Impact | Status |
|---|----------|--------|--------|
| Q1 | Should there be an automated spec completeness score? | Quality visibility | OPEN |
| Q2 | Should spec metadata be stored in a database for querying? | Enables MCP queries | OPEN — future |
| Q3 | Should there be a spec template generator CLI tool? | Reduces manual copy-paste | OPEN |

---

## 24. Glossary

| Term | Definition |
|------|-----------|
| **SOP** | Standard Operating Procedure — step-by-step process document |
| **Phase 5** | OB review phase: "Can I write a test from this spec?" |
| **Universal standard** | STD numbered 001-019, same topic across all products |
| **35-section template** | Standard spec structure defined in CORE-STD-000 |

---

## 25. Risk / Criticality

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Contributors ignore SOP | Medium | Inconsistent specs | Pre-commit hooks enforce structure |
| 7-category system too rigid | Low | Specs don't fit cleanly | ADR category captures edge cases |
| Template overhead for small specs | Medium | Many empty sections | Empty sections are OK — headings still required |

---

## 26. External Scan

7-category system adapted from DoD/NASA spec categorization (MIL-STD, NASA-STD series).
Industry equivalents: ISO 9001 (quality management), ITIL (IT service management).
The naming convention is well-established in regulated industries.

---

## 27. Security Considerations

- Spec files may reference internal architecture. Store in private repositories only.
- No credentials or API keys in spec content. Use placeholder names (`<API_KEY>`).
- Spec review process includes security review for IFS specs that define external interfaces.

---

## 28. Performance / Resource

Not applicable — this is a process SOP. No runtime performance characteristics.

---

## 29. Approval Record

| Reviewer | Date | Verdict | Notes |
|----------|------|---------|-------|
| Mark Hubers | 2026-03-22 | APPROVED | Session 84 — fill to 35 sections |

---

## 30. AI Review

Not yet performed. Scheduled for cross-spec review after all Rondo specs reach 35 sections.

---

## 31. AI Went Wrong

Not applicable — this is a process SOP, not an AI-built feature.

---

## 32. AI Assumptions

Not applicable — this is a process SOP, not an AI-built feature.

---

## 33. AI Cost

Not applicable — this is a process SOP, not an AI-built feature.

---

## 34. Notes

- This SOP is intentionally process-focused, not content-focused. CORE-STD-000 defines
  WHAT goes in each section. This SOP defines HOW to create, number, locate, and review specs.
- The universal numbering system (001-019 reserved) ensures that when OB references
  "STD-100" and Rondo references "STD-100", they're the same topic.

---

### Feature Maturity

| Feature | Maturity | Evidence | Retest |
|---------|----------|----------|--------|
| Spec onboarding checklist | WORKING | CORE-SOP-001 defines the onboarding flow | After checklist changes |
| Spec template (35 sections) | WORKING | Template used for all Rondo specs | After template changes |
| Section completeness check | THEORY | Specced for automated validation | Phase 2 build |


## 35. Change History

| Version | Date | What Changed |
|---------|------|-------------|
| 0.1 | 2026-03-18 | Initial draft — universal CORE-SOP-001 for Rondo. |
| 0.2 | 2026-03-22 | Filled to 35 sections. Added CORE-STD-012, CORE-STD-013, CORE-STD-021 refs. Approval (Mark, Session 84). |
