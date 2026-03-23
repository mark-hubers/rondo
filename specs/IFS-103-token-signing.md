<!-- document-type: reference -->
# IFS-103: Token & Signing Interface — SUPERSEDED

**THIS SPEC HAS BEEN ABSORBED INTO CORE-IFS-002 (Token & Signing Interface).**

Requirements from this spec are now in `core/specs/CORE-IFS-002-token-signing.md` — the single universal token/signing spec for all products.

**Product role:** Rondo is the DELEGATOR — passes token in OAPayload.auth.token so workers can sign on behalf of the issuer.

**What to read instead:** CORE-IFS-002 (48 reqs, full §4/§5/§6, cross-product roles defined)

**Created:** 2026-03-18 | **Updated:** 2026-03-22 | **Status:** SUPERSEDED
**Classification:** open
**Version:** 0.2
**Owner:** Mark G. Hubers
**Reviewed:** not-yet
**Supersedes:** none
**Superseded by:** CORE-IFS-002
**References:** CORE-STD-012 (Requirement Readiness), CORE-STD-013 (TrackerData), CORE-IFS-005 (MCP Standard)

---

## 1. Purpose & Scope

SUPERSEDED. See CORE-IFS-002 for the universal token and signing interface.
Rondo's role: DELEGATOR — passes tokens in OAPayload.auth.token to downstream workers.

**Users:** Mark (primary). Claude AI agents dispatching to other models. Future: teams needing multi-model AI orchestration, batch processing, cost optimization across AI providers.

---

## 2. The Problem

SUPERSEDED. Token and signing requirements are cross-product concerns. Having per-product
specs caused duplication and drift. CORE-IFS-002 consolidates all products.

---

## 3. Requirements

*All requirements in this spec are MUST priority unless marked SHOULD.*

SUPERSEDED. All 48 requirements live in CORE-IFS-002. Rondo-specific requirements are
tagged with `product: rondo` in the universal spec.

---

## 4. Architecture / Design

SUPERSEDED. See CORE-IFS-002 §4 for the universal token architecture.

---

## 5. Data Model

SUPERSEDED. See CORE-IFS-002 §5 for token data model.

---

## 6. Data Boundary

SUPERSEDED. See CORE-IFS-002 §6 for data boundary.

---

## 7. MCP / API Interface

SUPERSEDED. See CORE-IFS-002 and CORE-IFS-005 for MCP token validation tools.

---

## 8. States & Modes

SUPERSEDED. See CORE-IFS-002 for token lifecycle states.

---

## 9. Configuration

SUPERSEDED. See CORE-IFS-002 for token configuration patterns.

---

## 10. Rules & Constraints

SUPERSEDED. See CORE-IFS-002 §10 for token rules and constraints.

---

## 11. Quality Attributes

SUPERSEDED. See CORE-IFS-002 §11 for quality attributes.

---

## 12. Shared Patterns

SUPERSEDED. See CORE-IFS-002 §12 for shared token patterns.

---

## 13. Integration Points

SUPERSEDED. See CORE-IFS-002 §13 for cross-product integration points.

---

## 14. Standards Applied

| Standard | How Applied |
|----------|-------------|
| CORE-IFS-002 | This spec absorbed into CORE-IFS-002 |
| CORE-STD-012 | Requirement readiness tracked in CORE-IFS-002 |
| CORE-STD-013 | TrackerData patterns in CORE-IFS-002 |
| CORE-IFS-005 | MCP token validation in CORE-IFS-002 |

---

## 15. Self-Correction

SUPERSEDED. See CORE-IFS-002 §15.

---

## 16. Assumptions

SUPERSEDED. See CORE-IFS-002 §16.

---

## 17. Success Criteria

SUPERSEDED. See CORE-IFS-002 §17.

---

## 18. Build Notes / Estimate

Not applicable — spec is superseded.

---

## 19. Test Categories

SUPERSEDED. See CORE-IFS-002 §19.

---

## 20. Failure Modes

SUPERSEDED. See CORE-IFS-002 §20.

---

## 21. Dependencies + Used By

| Depends On | Why |
|------------|-----|
| CORE-IFS-002 | Superseding spec — all requirements live there |

| Used By | Why |
|---------|-----|
| IFS-102 | OAPayload.auth.token delegation |

---

## 22. Decisions

| # | Decision | Date | Why |
|---|----------|------|-----|
| D1 | Absorb into CORE-IFS-002 | 2026-03-20 | Token/signing is cross-product — one spec, not four |

---

## 23. Open Questions

No open questions — spec is superseded.

---

## 24. Glossary

See CORE-IFS-002 §24 for token/signing glossary.

---

## 25. Risk / Criticality

No additional risk — spec is superseded.

---

## 26. External Scan

See CORE-IFS-002 §26.

---

## 27. Security Considerations

See CORE-IFS-002 §27 — token security is critical and addressed in the universal spec.

---

## 28. Performance / Resource

See CORE-IFS-002 §28.

---

## 29. Approval Record

| Reviewer | Date | Verdict | Notes |
|----------|------|---------|-------|
| Mark Hubers | 2026-03-22 | APPROVED (as superseded redirect) | Session 84 — 35 section headers added |

---

## 30. AI Review

Not applicable — spec is superseded.

---

## 31. AI Went Wrong

Not applicable — spec is superseded.

---

## 32. AI Assumptions

Not applicable — spec is superseded.

---

## 33. AI Cost

Not applicable — spec is superseded.

---

## 34. Notes

- This file is kept as a redirect so that any existing references to IFS-103 land here
  and are directed to CORE-IFS-002. Do not delete this file.
- Session 84 added 35 section headers with SUPERSEDED redirects for template compliance.

---

### Feature Maturity

| Feature | Maturity | Evidence | Retest |
|---------|----------|----------|--------|
| Token signing for Rondo | THEORY | Superseded — consolidated to CORE-IFS-002 | After CORE-IFS-002 build |


## 35. Change History

| Version | Date | What Changed |
|---------|------|-------------|
| 0.1 | 2026-03-18 | Initial draft. |
| SUPERSEDED | 2026-03-20 | Absorbed into CORE-IFS-002. This file kept as redirect. |
| 0.2 | 2026-03-22 | Added 35 section headers with SUPERSEDED redirects. CORE-STD-012, CORE-STD-013, CORE-IFS-005 refs. Approval (Mark, Session 84). |
