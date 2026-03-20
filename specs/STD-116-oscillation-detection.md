# STD-116: Oscillation Detection

*Fix for A breaks B. Fix for B breaks A. Three cycles = halt. Don't loop forever.*

**Product:** Rondo
**Category:** STD
**Created:** 2026-03-20 | **Updated:** 2026-03-20 | **Status:** DESIGNED
**Classification:** open
**Version:** 1.0
**Owner:** Mark G. Hubers
**Reviewed:** not-yet
**Depends on:** REQ-100 (Core), STD-108 (Error Resilience) | **Used by:** REQ-101 (Automation), IFS-101 (Caliber Integration)
**Cross-pollinated from:** Caliber STD-105 (AI Operations — oscillation detection) — elevated from Caliber consumer pattern to Rondo dispatch-level enforcement

---

## 1. Purpose & Scope

**What this spec does:** When Caliber sends fix tasks through Rondo, a fix for finding A can introduce finding B. The fix for B can re-introduce A. This oscillation can loop forever. This spec detects oscillation AT THE DISPATCH LEVEL (Rondo sees the pattern before Caliber does) and halts after 3 cycles.

**Why Rondo, not Caliber:** Caliber sees one round at a time. Rondo sees ALL dispatches and can detect cross-round patterns. Oscillation is a dispatch-level phenomenon.

---

## 3. Requirements

| # | Requirement | Priority | Verified By |
|---|------------|----------|-------------|
| 1 | Track finding fingerprints across fix iterations: which findings appear, disappear, and reappear | MUST | Track test |
| 2 | Oscillation = finding A appears, disappears after fix, reappears after another fix. A→gone→A = 1 cycle. | MUST | Detect test |
| 3 | Threshold: 3 oscillation cycles for the same finding = HALT the fix loop | MUST | Halt test |
| 4 | On halt: mark finding as `OSCILLATING` (severity: block), include oscillation history in result | MUST | Mark test |
| 5 | Log oscillation chain: iteration 1 (A found) → iteration 2 (A fixed, B found) → iteration 3 (B fixed, A found again) | MUST | Chain test |
| 6 | Multi-model oscillation: if Claude's fix breaks what Gemini verified, detect across model boundaries | SHOULD | Cross-model test |
| 7 | Pessimistic consensus: if ANY model's review finds a BLOCK issue with a fix, the fix is rejected. From Caliber STD-105. | MUST | Consensus test |
| 8 | `rondo oscillations` CLI: show detected oscillation patterns | SHOULD | CLI test |
| 9 | Oscillation data feeds CORE-STD-011 self-correction: record_guess("fix_resolves_finding") + record_outcome(was_corrected=True if oscillating) | SHOULD | Learning test |
| 10 | When OB-connected: oscillation events included in OAResult for OB's convergence tracking | SHOULD | Integration test |

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

## 10. Rules & Constraints

1. **3 cycles = halt.** Generous enough for legitimate convergence. Strict enough to catch real oscillation. Violation ID: `STD116-THREE-CYCLES`
2. **Pessimistic consensus.** Any model says BLOCK = rejected. Don't let one model override another. Violation ID: `STD116-PESSIMISTIC`
3. **Oscillation is a dispatch pattern.** Rondo detects it because Rondo sees the full iteration history. Caliber sees one iteration at a time. Violation ID: `STD116-DISPATCH-LEVEL`
4. **OSCILLATING findings need human review.** The fix loop can't resolve them. Mark decides. Violation ID: `STD116-HUMAN-REVIEW`

---

## 17. Success Criteria

| # | Criterion | How to Verify |
|---|-----------|---------------|
| 1 | Finding A oscillates 3 times → fix loop halted → "OSCILLATING" finding created | Oscillation test |
| 2 | Claude fix breaks Gemini verification → cross-model oscillation detected | Cross-model test |
| 3 | Pessimistic consensus: 1 BLOCK from any reviewer = fix rejected | Consensus test |

---

## 35. Change History

| Version | Date | What Changed |
|---------|------|-------------|
| 1.0 | 2026-03-20 | Initial. Cross-pollinated from Caliber STD-105. 10 requirements. Elevated to dispatch level. |
