# STD-116: Oscillation Detection

*Fix for A breaks B. Fix for B breaks A. Three cycles = halt. Don't loop forever.*

**Product:** Rondo
**Category:** STD
**Created:** 2026-03-20 | **Updated:** 2026-03-20 | **Status:** DESIGNED
**Classification:** open
**Version:** 1.0
**Owner:** Mark G. Hubers
**Reviewed:** not-yet
**Depends on:** REQ-100 (Core), STD-108 (Error Resilience), CORE-STD-011, CORE-STD-012, CORE-STD-021, CORE-STD-013 | **Used by:** REQ-101 (Automation), IFS-101 (Caliber Integration)
**Cross-pollinated from:** Caliber STD-105 (AI Operations — oscillation detection) — elevated from Caliber consumer pattern to Rondo dispatch-level enforcement

---

## 1. Purpose & Scope

**What this spec does:** When Caliber sends fix tasks through Rondo, a fix for finding A can introduce finding B. The fix for B can re-introduce A. This oscillation can loop forever. This spec detects oscillation AT THE DISPATCH LEVEL (Rondo sees the pattern before Caliber does) and halts after 3 cycles.

**Why Rondo, not Caliber:** Caliber sees one round at a time. Rondo sees ALL dispatches and can detect cross-round patterns. Oscillation is a dispatch-level phenomenon.

**Users:** Mark (primary). Claude AI agents dispatching to other models. Future: teams needing multi-model AI orchestration, batch processing, cost optimization across AI providers.

---

<!-- convergence: allow(category_deep) reason: 3-AI consensus verified STD correct (Session 86) -->

## 2. The Problem

AI fix loops can oscillate: fix A breaks B, fix B breaks A, fix A breaks B again. Without detection, this loops forever — burning API budget, producing no net improvement, and potentially degrading the codebase. Rondo sees the full dispatch history and can detect the pattern before Caliber (which sees one iteration at a time).

---

## 3. Requirements


*All requirements use MUST/SHOULD priority per CORE-STD-012.*

| ID | Requirement | Priority | Verified By |
|----|-------------|----------|-------------|
| 001 | Track finding fingerprints across fix iterations: which findings appear, disappear, and reappear | MUST | Track test |
| 002 | Oscillation = finding A appears, disappears after fix, reappears after another fix. A→gone→A = 1 cycle. | MUST | Detect test |
| 003 | Threshold: 3 oscillation cycles for the same finding = HALT the fix loop | MUST | Halt test |
| 004 | On halt: mark finding as `OSCILLATING` (severity: block), include oscillation history in result | MUST | Mark test |
| 005 | Log oscillation chain: iteration 1 (A found) → iteration 2 (A fixed, B found) → iteration 3 (B fixed, A found again) | MUST | Chain test |
| 006 | Multi-model oscillation: if Claude's fix breaks what Gemini verified, detect across model boundaries | SHOULD | Cross-model test |
| 007 | Pessimistic consensus: if ANY model's review finds a BLOCK issue with a fix, the fix is rejected. From Caliber STD-105. | MUST | Consensus test |
| 008 | `rondo oscillations` CLI: show detected oscillation patterns | SHOULD | CLI test |
| 009 | Oscillation data feeds CORE-STD-011 self-correction: record_guess("fix_resolves_finding") + record_outcome(was_corrected=True if oscillating) | SHOULD | Learning test |
| 010 | When OB-connected: oscillation events included in OAResult for OB's convergence tracking | SHOULD | Integration test |


---

## 4. Architecture / Design

```
Iteration 1: Caliber finds A, B       Rondo dispatches fix(A)
Iteration 2: Caliber finds B, C       A fixed! But C appeared.    Rondo dispatches fix(B), fix(C)
Iteration 3: Caliber finds A, C       B fixed! But A is BACK.     ← A oscillated (cycle 1)
Iteration 4: Caliber finds B, C       A fixed again! B is BACK.   ← B oscillated (cycle 1), A (cycle 2)
Iteration 5: Caliber finds A, B       Both back!                  ← A (cycle 3) → HALT
                                                                      B (cycle 2) → continue watching
```

**Detection algorithm:**
```python
def detect_oscillation(finding_history: list[set[str]]) -> dict[str, int]:
    """Track finding fingerprints across iterations. Return oscillation count per finding."""
    cycles = defaultdict(int)
    for finding in all_unique_findings(finding_history):
        present = [finding in iteration for iteration in finding_history]
        # Count transitions: present→absent→present = 1 cycle
        for i in range(2, len(present)):
            if present[i] and not present[i-1] and present[i-2]:
                cycles[finding] += 1
    return cycles
```

---

## 5. Data Model

Finding fingerprint: `{finding_id: str, file: str, rule: str, message_hash: str}`. Oscillation record: `{finding_id, cycle_count: int, first_seen_iteration: int, last_seen_iteration: int, iterations_present: list[int]}`. Stored in dispatch metadata, accessible via `rondo oscillations` CLI.

---

## 6. Data Boundary

Oscillation detection is internal to Rondo's fix loop management. Oscillation records are included in RoundResult metadata. When OB-connected, oscillation events are embedded in OAResult for convergence tracking. The boundary is the oscillation metadata field in results.

---

## 7. MCP / API Interface

No MCP interface for oscillation detection. Oscillation data is embedded in dispatch results. CORE-STD-021 MCP tools in OB may query oscillation history from ingested results. The `rondo oscillations` CLI is the local query interface.

---

## 8. States & Modes

Each tracked finding has an oscillation state: `STABLE` (no oscillation detected), `WATCHING` (1-2 cycles, monitoring), `OSCILLATING` (3+ cycles, halted). The `OSCILLATING` state triggers a block finding that requires human review. No auto-resolution for oscillating findings.

**State Machine Type:** FORWARD-ONLY
**Rationale:** Oscillation detection progresses STABLE → WATCHING → OSCILLATING as cycles accumulate. OSCILLATING is terminal (requires human review). A finding does not return to STABLE automatically — human intervention creates a new tracking instance.
**Rollback:** Human review resolves the OSCILLATING state. The finding restarts tracking from STABLE.

---

## 9. Configuration

```toml
[oscillation]
enabled = true
cycle_threshold = 3               # Cycles before halt (default: 3)
pessimistic_consensus = true      # Any model's BLOCK = rejected
max_iterations = 10               # Max fix iterations per finding
```

---

## 10. Rules & Constraints

1. **3 cycles = halt.** Generous enough for legitimate convergence. Strict enough to catch real oscillation. Violation ID: `STD116-THREE-CYCLES`
2. **Pessimistic consensus.** Any model says BLOCK = rejected. Don't let one model override another. Violation ID: `STD116-PESSIMISTIC`
3. **Oscillation is a dispatch pattern.** Rondo detects it because Rondo sees the full iteration history. Caliber sees one iteration at a time. Violation ID: `STD116-DISPATCH-LEVEL`
4. **OSCILLATING findings need human review.** The fix loop can't resolve them. Mark decides. Violation ID: `STD116-HUMAN-REVIEW`

---

## 11. Quality Attributes

- **Budget protection:** Oscillation detection prevents unbounded API spend on unresolvable fix loops.
- **Human escalation:** OSCILLATING findings are escalated to Mark, not auto-resolved.
- **Cross-model awareness:** Detection works across model boundaries (Claude fix, Gemini review).

---

## 12. Shared Patterns

- **Fingerprint tracking:** Same pattern as Caliber's finding deduplication.
- **Pessimistic consensus:** Any reviewer's BLOCK = rejected. Same pattern across all multi-model interactions.
- **Self-correction feedback:** Oscillation data feeds CORE-STD-011 record_guess/record_outcome loop.

---

## 13. Integration Points

| Integration | What Crosses | Standard Enforced |
|-------------|-------------|-------------------|
| STD-116 → Caliber | Caliber findings feed oscillation tracking | IFS-101 finding format |
| STD-116 → OB | Oscillation events in OAResult | IFS-102 integration contract |
| STD-116 → CORE-STD-011 | Oscillation feeds self-correction learning | record_outcome pattern |
| STD-116 → CORE-STD-013 | Oscillation events as TrackerData | Append-only tracking |

---

## 14. Standards Applied

| Standard | How It Applies |
|----------|---------------|
| Caliber STD-105 | Origin pattern — oscillation detection elevated from consumer to dispatch level |
| CORE-STD-011 | Self-correction — oscillation data teaches the system about fix quality |
| CORE-STD-012 | Requirement readiness — oscillating findings block READY state |
| CORE-STD-013 | TrackerData — oscillation events are trackable for trend analysis |
| CORE-STD-021 | MCP standard — oscillation data queryable from OB's MCP tools |

---

## 15. Self-Correction

Oscillation detection IS self-correction for fix loops. The system detects that its fixes are not converging and halts. CORE-STD-011 integration: `record_guess("fix_resolves_finding")` at dispatch, `record_outcome(was_corrected=True)` when oscillation detected. Over time, the system learns which fix patterns oscillate.

---

## 16. Assumptions

1. Finding fingerprints are stable across iterations (same finding produces same fingerprint).
2. 3 cycles is generous enough for legitimate convergence but catches real oscillation.
3. Cross-model oscillation is detectable via finding fingerprints (model-agnostic).
4. Human review can resolve oscillating findings that AI cannot.

---

## 17. Success Criteria

| # | Criterion | How to Verify |
|---|-----------|---------------|
| 1 | Finding A oscillates 3 times → fix loop halted → "OSCILLATING" finding created | Oscillation test |
| 2 | Claude fix breaks Gemini verification → cross-model oscillation detected | Cross-model test |
| 3 | Pessimistic consensus: 1 BLOCK from any reviewer = fix rejected | Consensus test |

---

## 18. Build Notes / Estimate

Finding tracker (fingerprint across iterations): 3 hours. Oscillation detector (cycle counting): 2 hours. Pessimistic consensus logic: 2 hours. CLI (`rondo oscillations`): 2 hours. OB integration (OAResult embedding): 1 hour. Total: ~10 hours.

---

## 19. Test Categories

| Category | What It Tests |
|----------|--------------|
| Fingerprint tests | Same finding produces same fingerprint across iterations |
| Cycle detection tests | Present→absent→present counted correctly |
| Halt tests | 3 cycles triggers OSCILLATING state and block finding |
| Cross-model tests | Oscillation detected across Claude fix / Gemini review boundary |
| Consensus tests | Any BLOCK from any model = fix rejected |

---

## 20. Failure Modes

| Failure | Impact | Mitigation |
|---------|--------|------------|
| Fingerprint instability | Same finding gets different fingerprints | Use stable components (file, rule, not message text) |
| False oscillation | Legitimate convergence mistaken for oscillation | 3-cycle threshold is generous; manual override available |
| Single-model blind spot | One model always approves what another rejects | Pessimistic consensus catches this |

---

## 21. Dependencies + Used By

| Direction | Spec | Relationship |
|-----------|------|-------------|
| Depends on | REQ-100 | Core dispatch provides iteration history |
| Depends on | STD-108 | Error resilience for oscillation tracking |
| Depends on | CORE-STD-011 | Self-correction — oscillation feeds learning |
| Depends on | CORE-STD-012 | Readiness — oscillating findings block READY |
| Used by | REQ-101 | Overnight automation halts on oscillation |
| Used by | IFS-101 | Caliber integration provides findings to track |
| Used by | IFS-102 | OB receives oscillation events in results |

---

## 22. Decisions

| Decision | Rationale | Date |
|----------|-----------|------|
| D1: 3 cycles, not 2 | 2 is too aggressive — legitimate fixes sometimes take a second try | 2026-03-20 |
| D2: Rondo detects, not Caliber | Rondo sees full iteration history; Caliber sees one at a time | 2026-03-20 |
| D3: Pessimistic consensus | One model's approval cannot override another's block | 2026-03-20 |

---

## 23. Open Questions

1. Should oscillation history persist across rounds (long-term pattern learning)?
2. Should there be a "force continue" override for Mark to push past oscillation halt?

---

## 24. Glossary

| Term | Definition |
|------|-----------|
| **Oscillation** | Finding that repeatedly appears, disappears, and reappears across fix iterations |
| **Cycle** | One occurrence of present→absent→present for a finding |
| **Pessimistic consensus** | Any reviewer's BLOCK = fix rejected, regardless of other reviews |
| **Finding fingerprint** | Stable identifier for a finding across iterations (file + rule + hash) |

---

## 25. Risk / Criticality

**HIGH.** Undetected oscillation burns API budget and degrades code quality. An overnight run that oscillates for 10 iterations costs money and produces nothing useful. Oscillation detection is a critical safety mechanism for automated fix loops.

---

## 26. External Scan

Compiler optimization has "oscillation detection" for register allocation and instruction scheduling — same concept, different domain. Control theory's "limit cycle detection" is the formal equivalent. No existing AI development tool implements finding oscillation detection — this is novel for the domain.

---

## 27. Security Considerations

Oscillation can be induced by adversarial prompt injection: a crafted prompt that always produces a finding that triggers a fix that introduces another finding. Oscillation detection limits the damage to 3 cycles + halt. See STD-107 for broader threat model.

---

## 28. Performance / Resource

Fingerprint computation: ~1ms per finding. Oscillation check: ~1ms per iteration (set comparison). Total overhead per fix iteration: <5ms. Memory: finding history for current round (<1KB per finding). No significant performance impact.

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

CORE-STD-012 (Requirement Readiness) treats oscillating findings as blockers — a requirement with oscillating findings cannot reach READY. CORE-STD-013 (TrackerData) records oscillation events for cross-session analysis (which findings oscillate most?). CORE-STD-021 MCP tools in OB may display oscillation history in quality dashboards.

---

### Feature Maturity

| Feature | Maturity | Evidence | Retest |
|---------|----------|----------|--------|
| Oscillation detection | THEORY | Specced for detecting fix-break-fix loops | Phase 2 build |
| Loop breaking strategy | THEORY | Specced for automatic escalation on oscillation | Phase 2 build |
| Oscillation metrics | THEORY | Specced for tracking oscillation frequency | Phase 2 build |


## 35. Change History

| Version | Date | What Changed |
|---------|------|-------------|
| 1.0 | 2026-03-20 | Initial. Cross-pollinated from Caliber STD-105. 10 requirements. Elevated to dispatch level. |
| 1.1 | 2026-03-22 | Filled to 35 sections. Added CORE-STD-012, CORE-STD-013, CORE-STD-021 refs. Approval record (Mark, Session 84). |
