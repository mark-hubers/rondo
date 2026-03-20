# SOP-100: Spec Onboarding Procedure

*How to add or create specs for Rondo. The rules any contributor must follow.*

**Created:** 2026-03-18 | **Status:** DESIGNED
**Classification:** open
**Version:** 0.1
**Owner:** Mark G. Hubers
**Reviewed:** not-yet
**Supersedes:** none
**Universal procedure** — same topic number across all products (DEC-017)
**Product:** Rondo
**Matches:** OB-SOP-100, Caliber-SOP-100, Rondo-SOP-100

---

## 1. Spec Categories (7 Categories — DoD/NASA-Aligned)

| Prefix | Category | Purpose | Example |
|--------|----------|---------|---------|
| REQ | Requirements | What Rondo must do | REQ-100 (Core), REQ-101 (Automation) |
| STD | Standards | How code must be written | STD-108 (Error Resilience), STD-109 (Configuration) |
| SOP | Procedures | How to do things (step-by-step) | SOP-100 (Build & Run), SOP-010 (Release) |
| IFS | Interfaces | How Rondo connects to other products | IFS-100 (Claude CLI), IFS-102 (OB Integration) |
| VER | Verification | How to prove specs are implemented | VER-100 (Verification Matrix) |
| TST | Test Plans | Detailed test strategies | (not yet created) |
| ADR | Decisions | Why we chose X over Y | (not yet created) |

---

## 2. Universal Standards (STD-100 to STD-105)

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

## 3. Numbering Rules

| Range | Scope | Rule |
|-------|-------|------|
| 001-019 | Universal | Same topic across all products. Never product-specific. |
| 020+ | Product-specific | Unique to Rondo. Free to number as needed. |

**Rondo-specific examples:** STD-108 (Error Resilience), STD-109 (Configuration), STD-110 (Concurrency Safety), STD-111 (Code Quality).

---

## 4. Template

Use the 35-section template defined in CORE-STD-000-spec-standard.md. All specs must include at minimum:

**Required sections:** Purpose & Scope, The Problem, Requirements, Architecture/Design, Data Model, Data Boundary, Integration Points, Assumptions, Success Criteria, Dependencies + Used By, Decisions, Change History.

**Optional sections:** MCP/API Interface, States & Modes, Configuration, Quality Attributes, Shared Patterns, Self-Correction, and all AI sections (29-34).

---

## 5. Where Specs Live

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

## 6. How to Add a New Spec

1. Determine the category (REQ, STD, SOP, IFS, VER, TST, ADR)
2. Check existing specs for naming conflicts
3. Pick the next available number in the appropriate range
4. Copy the 35-section template from OB-00
5. Fill required sections (minimum viable spec)
6. Add header: title, description, created date, status, depends-on, used-by
7. Commit with message: `Add Rondo [PREFIX]-NNN: brief description`

---

## 7. Cross-References

When referencing specs from other products:

| Referencing | Format | Example |
|-------------|--------|---------|
| Rondo spec from Rondo | `SOP-100` or `REQ-100` | "See REQ-100 (Core)" |
| OB spec from Rondo | `OB-NN` or `OB-SOP-NNN` | "OB-SOP-100 defines build integration" |
| Caliber spec from Rondo | `Caliber SOP-020` | "Caliber SOP-020 defines the build flow" |
| Cross-product interface | `IFS-NNN` with product context | "IFS-102 defines OB integration" |

Use IFS specs to formally define integration points between products.

---

## 8. Review Process

1. Spec must pass OB's 9-phase spec refinement process (CORE-SOP-006, ORB-03)
2. At minimum, Phase 5 must pass: "Can I write a test from this spec?" = yes
3. Cross-spec vocabulary check against existing Rondo specs
4. Rondo-specific: verify task API contracts are complete (input schema, output schema, error types)
5. Spec must be reviewed before any build sprint references it

---

## 9. NAMING-MAP.md

Before adding new data structures (classes, config keys, task types):

1. Check existing specs for naming conventions (especially STD-100, REQ-100)
2. Check OB's `ace/ID-CHEATSHEET.md` for cross-product naming
3. Ensure no name collision with Rondo's existing task types or config keys
4. Rondo-specific: check `rondo.toml` schema for config key naming

---

## 10. Change History

| Version | Date | What Changed |
|---------|------|-------------|
| 0.1 | 2026-03-18 | Initial draft — universal SOP-011 for Rondo. |
