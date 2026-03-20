# REQ-107: Task Flakiness Detection

*Same task, same input, different results = flaky dispatch. Find it. Fix the prompt or switch the model.*

**Product:** Rondo
**Category:** REQ
**Created:** 2026-03-20 | **Updated:** 2026-03-20 | **Status:** DESIGNED
**Classification:** open
**Version:** 1.0
**Owner:** Mark G. Hubers
**Reviewed:** not-yet
**Supersedes:** none
**Depends on:** REQ-100 (Core), STD-113 (Dispatch Audit Trail) | **Used by:** REQ-106 (Trend Alerting), IFS-102 (OB Integration)
**Cross-pollinated from:** OB-REQ-122 (Flakiness Detection) — adapted from test flakiness to dispatch flakiness

---

## 1. Purpose & Scope

**What this spec does:** AI dispatches are non-deterministic. The same prompt can produce different results — one run succeeds, the next fails, the third partially succeeds. Some variation is expected, but HIGH variation means the prompt is poorly defined, the model is unreliable for this task type, or the context is insufficient. This spec detects tasks with unacceptable flip rates.

**IN scope:**
- Per-task-template result consistency tracking
- Flakiness scoring (flip rate on semantically-identical inputs)
- Prompt-hash matching (same prompt = comparable results)
- Root cause categorization (prompt/model/context/temperature)
- Flaky task alerting

**OUT of scope:**
- Prompt improvement (product-specific tuning)
- Model selection logic (REQ-100)
- Audit trail storage (STD-113 provides the data)

---

## 3. Requirements

| # | Requirement | Priority | Verified By |
|---|------------|----------|-------------|
| 1 | Track per-task-template results: task_name, prompt_hash, model, status (done/partial/error), confidence, run_at | MUST | Tracking test |
| 2 | Group by (task_name + prompt_hash): same prompt = comparable results. Different prompts aren't comparable. | MUST | Grouping test |
| 3 | Flakiness score = status flips / total runs within group, over rolling 14-day window | MUST | Score test |
| 4 | Flip = status change between consecutive runs of same prompt_hash (done→error, error→done, done→partial) | MUST | Flip test |
| 5 | Threshold: flakiness score >20% = flagged flaky (higher than Caliber's 10% because AI is inherently more variable) | MUST | Threshold test |
| 6 | Root cause categories: `PROMPT` (ambiguous instruction), `MODEL` (model inconsistency), `CONTEXT` (missing/changing context files), `TEMPERATURE` (non-deterministic sampling), `UNKNOWN` | SHOULD | Category test |
| 7 | `rondo flaky` CLI: show flaky task templates with scores, model, root cause | SHOULD | CLI test |
| 8 | `rondo flaky --json` for machine-readable output | SHOULD | JSON test |
| 9 | Flaky task alert in morning report: "3 task templates have >20% flip rate — consider prompt refinement" | SHOULD | Report test |
| 10 | Per-model flakiness: track which models are more flaky for which task types. Feed into model routing. | SHOULD | Model test |
| 11 | Confidence variance: if same prompt produces confidence scores ranging 0.3-0.9, the task definition is unstable | SHOULD | Variance test |
| 12 | When OB-connected: flakiness data included in OAResult metadata | SHOULD | Integration test |

---

## 5. Data Model

Uses `rondo_audit.jsonl` from STD-113. Flakiness calculated from audit data — no separate storage needed.

**Flakiness query pattern:**
```sql
-- Group dispatches by task_name + prompt_hash
-- Count status transitions (flips) within rolling window
-- Score = flips / total
```

---

## 10. Rules & Constraints

1. **Same prompt only.** Only compare results where prompt_hash matches. Different prompts are different experiments. Violation ID: `REQ107-SAME-PROMPT`
2. **20% threshold for AI.** AI is inherently non-deterministic. 10% would flag everything. 20% means genuinely unreliable. Violation ID: `REQ107-THRESHOLD`
3. **Model matters.** The same prompt on Opus vs Sonnet vs Haiku will have different flakiness profiles. Track per-model. Violation ID: `REQ107-PER-MODEL`
4. **Flaky ≠ broken.** A task that fails 100% is broken (fix the prompt). A task that fails 25% is flaky (harder — needs investigation). Violation ID: `REQ107-DISTINGUISH`

---

## 17. Success Criteria

| # | Criterion | How to Verify |
|---|-----------|---------------|
| 1 | Task passes 3/5 runs with same prompt → flakiness score = 40% → flagged | Flip test |
| 2 | Morning report lists flaky tasks | Report test |
| 3 | Different prompts for same task_name → separate flakiness tracking | Grouping test |

---

## 35. Change History

| Version | Date | What Changed |
|---------|------|-------------|
| 1.0 | 2026-03-20 | Initial. Cross-pollinated from OB-REQ-122. 12 requirements. Adapted threshold (20% vs 10%) for AI non-determinism. |
