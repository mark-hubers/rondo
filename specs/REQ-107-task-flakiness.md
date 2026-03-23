# REQ-107: Task Flakiness Detection

*Same task, same input, different results = flaky dispatch. Find it. Fix the prompt or switch the model.*

**Product:** Rondo
**Category:** REQ
**Created:** 2026-03-20 | **Updated:** 2026-03-22 | **Status:** DESIGNED
**Classification:** open
**Version:** 1.1
**Owner:** Mark G. Hubers
**Reviewed:** not-yet
**Supersedes:** none
**Depends on:** REQ-100 (Core), STD-113 (Dispatch Audit Trail) | **Used by:** REQ-106 (Trend Alerting), IFS-102 (OB Integration)
**Cross-pollinated from:** OB-REQ-122 (Flakiness Detection) — adapted from test flakiness to dispatch flakiness
**References:** CORE-STD-012 (Requirement Readiness), CORE-STD-013 (TrackerData), CORE-IFS-005 (MCP Standard)

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

**Users:** Mark (primary). Claude AI agents dispatching to other models. Future: teams needing multi-model AI orchestration, batch processing, cost optimization across AI providers.

---

## 2. The Problem

A task that fails 100% of the time is easy to diagnose — the prompt is wrong or the model
can't handle it. A task that fails 25% of the time is far more insidious: it passes often
enough to seem reliable but fails unpredictably. Overnight runs depend on task reliability.
Flaky tasks waste money (repeated retries), time (inconsistent results), and trust
(can't depend on the output). This spec makes flakiness visible and trackable.

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

## 4. Architecture / Design

```
STD-113 Audit Trail (rondo_audit.jsonl)
    │
    ▼
Flakiness Engine
    ├── Group by (task_name + prompt_hash + model)
    ├── Sort by run_at (chronological)
    ├── Count status flips between consecutive runs
    ├── Calculate flakiness score (flips / total)
    ├── Categorize root cause (heuristic)
    └── Flag groups exceeding 20% threshold
    │
    ▼
Flaky task report → CLI / morning report / OAResult
```

Root cause heuristic: if flakiness varies by model (same prompt, different flakiness on
different models) → MODEL. If context_files changed between runs → CONTEXT. If neither
model nor context changed → PROMPT or TEMPERATURE (needs investigation).

---

## 5. Data Model

Uses `rondo_audit.jsonl` from STD-113. Flakiness calculated from audit data — no separate storage needed.

**Flakiness query pattern:**
```sql
-- Group dispatches by task_name + prompt_hash
-- Count status transitions (flips) within rolling window
-- Score = flips / total
```

| Derived Metric | Calculation | Window |
|---------------|-------------|--------|
| Flakiness score | flips / total_runs per (task_name, prompt_hash, model) | 14 days |
| Confidence variance | stddev(confidence) per group | 14 days |
| Per-model flakiness | flakiness score grouped by model | 14 days |

---

## 6. Data Boundary

**What this produces:**

| Output | Format | Consumer |
|--------|--------|----------|
| Flaky task list | Terminal table / JSON | Mark (CLI), morning report |
| Per-model flakiness scores | JSON | REQ-109 (routing suggestions) |
| Root cause categories | String per flaky group | Mark (investigation guide) |

**What this consumes:**

| Input | Format | Producer |
|-------|--------|----------|
| Dispatch audit trail | JSONL | STD-113 |
| Flakiness threshold | TOML config | `.rondo/config.toml` |

---

## 7. MCP / API Interface

Future: an MCP tool per CORE-IFS-005 could expose flakiness data for AI agents to query.
Example: "Which of my task templates are flaky?" The MCP tool would return flaky groups
with scores and root cause categories.

---

## 8. States & Modes

Per-task-template flakiness states:

| State | Condition | Meaning |
|-------|-----------|---------|
| **stable** | Flakiness score <10% | Reliable, consistent results |
| **noisy** | 10-20% flakiness | Some variation, monitor |
| **flaky** | >20% flakiness | Unreliable, investigate |
| **broken** | 100% failure rate | Not flaky — just broken |
| **insufficient_data** | <5 runs in window | Not enough data to score |

---

## 9. Configuration

```toml
[flakiness]
threshold_pct = 20                 # Score above this = flaky
window_days = 14                   # Rolling window (longer than trends — need more data)
min_runs = 5                       # Minimum runs to calculate score
confidence_variance_threshold = 0.3 # Flag if stddev(confidence) > this
```

---

## 10. Rules & Constraints

1. **Same prompt only.** Only compare results where prompt_hash matches. Different prompts are different experiments. Violation ID: `REQ107-SAME-PROMPT`
2. **20% threshold for AI.** AI is inherently non-deterministic. 10% would flag everything. 20% means genuinely unreliable. Violation ID: `REQ107-THRESHOLD`
3. **Model matters.** The same prompt on Opus vs Sonnet vs Haiku will have different flakiness profiles. Track per-model. Violation ID: `REQ107-PER-MODEL`
4. **Flaky ≠ broken.** A task that fails 100% is broken (fix the prompt). A task that fails 25% is flaky (harder — needs investigation). Violation ID: `REQ107-DISTINGUISH`

---

## 11. Quality Attributes

| Attribute | Target | Rationale |
|-----------|--------|-----------|
| Detection speed | Flagged within 5 runs | Don't wait for 50 runs to detect flakiness |
| Accuracy | <5% false positive rate | Too many false flaky flags → ignored |
| Actionability | Root cause category guides investigation | "PROMPT" → fix the instruction, "MODEL" → switch |
| Per-model granularity | Same prompt flagged per model independently | Model A may be flaky where Model B is stable |

---

## 12. Shared Patterns

- **Prompt-hash grouping:** SHA-256 of the prompt text after template expansion. Same hash
  = semantically identical prompt. This is the key that enables comparison.
- **Rolling window:** 14-day window (longer than REQ-106's 7-day) because flakiness needs
  more data points to be statistically meaningful.
- **Root cause heuristic:** Automated categorization is a first guess, not a diagnosis.
  Mark makes the final determination.

---

## 13. Integration Points

| Integration | Spec | Direction | Contract |
|-------------|------|-----------|----------|
| Audit trail | STD-113 | Inbound | JSONL audit records with prompt_hash |
| Trend alerting | REQ-106 | Outbound | Flakiness feeds trend health status |
| Morning report | REQ-101 | Outbound | Flaky task summary section |
| Provider routing | REQ-109 | Advisory | Per-model flakiness feeds routing suggestions |
| OB integration | IFS-102 | Outbound | Flakiness data in OAResult metadata |

---

## 14. Standards Applied

| Standard | How Applied |
|----------|-------------|
| CORE-STD-011 (Self-Correction) | Flakiness detection is self-correction — detect unreliable tasks, improve them |
| CORE-STD-012 (Requirement Readiness) | Each requirement tagged with readiness state |
| CORE-STD-013 (TrackerData) | Flakiness scores logged as trackerdata entries |
| CORE-IFS-005 (MCP Standard) | Future MCP tool for flakiness queries |

---

## 15. Self-Correction

- If a prompt is modified (new prompt_hash), the old flakiness score is archived and
  tracking restarts for the new hash. This detects whether the fix actually reduced flakiness.
- If root cause heuristic consistently misclassifies (Mark overrides the category), the
  heuristic rules are logged for future refinement.
- If flakiness threshold of 20% flags too many tasks (>50% of active templates), the
  morning report suggests increasing the threshold — the current value may be too sensitive
  for the workload.

---

## 16. Assumptions

| # | Assumption | If Wrong |
|---|-----------|----------|
| A1 | Prompt hash is stable (same prompt → same hash) | Template expansion must be deterministic |
| A2 | 5 runs is enough for initial flakiness detection | May need more for low-volume tasks |
| A3 | Status is the primary flakiness signal | Output quality variation (same status, different quality) is invisible |
| A4 | Root cause categories are actionable | May need finer-grained categories |

---

## 17. Success Criteria

| # | Criterion | How to Verify |
|---|-----------|---------------|
| 1 | Task passes 3/5 runs with same prompt → flakiness score = 40% → flagged | Flip test |
| 2 | Morning report lists flaky tasks | Report test |
| 3 | Different prompts for same task_name → separate flakiness tracking | Grouping test |
| 4 | Root cause category assigned to each flaky group | Category test |
| 5 | Per-model flakiness shows which model is more reliable | Model comparison test |

---

## 18. Build Notes / Estimate

| Item | Estimate |
|------|----------|
| Prompt hash computation + audit integration | 0.5 day |
| Flakiness engine (grouping, flip counting, scoring) | 1.5 days |
| Root cause heuristic | 1 day |
| CLI (`rondo flaky`) | 0.5 day |
| Morning report integration | 0.5 day |
| Tests | 1.5 days |
| Total | ~5.5 days |

---

## 19. Test Categories

| Category | What | Count (est.) |
|----------|------|-------------|
| Unit | Flip counting, score calculation, grouping logic | 10 |
| Integration | Audit → flakiness engine → report | 4 |
| Heuristic | Root cause categorization accuracy | 5 |
| CLI | `rondo flaky` output formatting | 3 |
| Edge case | Insufficient data, all-pass, all-fail, single run | 4 |

---

## 20. Failure Modes

| Failure | Impact | Mitigation |
|---------|--------|------------|
| Prompt hash collision | Different prompts grouped together | Use SHA-256 (collision probability negligible) |
| Template expansion non-deterministic | Same logical prompt → different hashes | Normalize prompt before hashing |
| Too few runs for reliable scoring | Noisy scores | Require min_runs (default 5) |
| Root cause heuristic wrong | Misleading investigation direction | Label as heuristic, Mark decides |

---

## 21. Dependencies + Used By

| Depends On | Why |
|------------|-----|
| REQ-100 | Core dispatch framework (defines prompt_hash field) |
| STD-113 | Audit trail (data source for all flakiness analysis) |

| Used By | Why |
|---------|-----|
| REQ-106 | Trend alerting includes flakiness in model health |
| REQ-109 | Provider routing uses per-model flakiness for affinity suggestions |
| IFS-102 | OB integration includes flakiness data |

---

## 22. Decisions

| # | Decision | Date | Why |
|---|----------|------|-----|
| D1 | 20% threshold (not 10%) | 2026-03-20 | AI is inherently non-deterministic; 10% would flag everything |
| D2 | 14-day window (not 7-day) | 2026-03-20 | Flakiness needs more data points than trend alerting |
| D3 | Root cause is heuristic, not definitive | 2026-03-20 | Automated diagnosis is a guide, not a verdict |
| D4 | Per-model tracking required | 2026-03-20 | Same prompt may be flaky on one model but stable on another |

---

## 23. Open Questions

| # | Question | Impact | Status |
|---|----------|--------|--------|
| Q1 | Should Rondo auto-retry flaky tasks with a different model? | Automation vs cost | OPEN |
| Q2 | Should output quality be a flakiness signal (not just status)? | Harder to measure but more meaningful | OPEN |
| Q3 | Should historical flakiness data be archived when a prompt changes? | Data retention vs clean slate | OPEN — currently archived |

---

## 24. Glossary

| Term | Definition |
|------|-----------|
| **Flakiness** | Inconsistent results from the same prompt — sometimes passes, sometimes fails |
| **Flip** | Status change between consecutive runs of the same prompt_hash |
| **Prompt hash** | SHA-256 of the normalized prompt text, used to group comparable runs |
| **Root cause** | Heuristic categorization of why a task is flaky (PROMPT/MODEL/CONTEXT/TEMPERATURE) |

---

## 25. Risk / Criticality

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Too many flaky tasks flagged | Medium | Alert fatigue | Tune threshold after first month |
| Root cause heuristic misleads | Medium | Wasted investigation time | Label as "suggested" not "confirmed" |
| Flakiness hides model quality degradation | Low | Trend alerting (REQ-106) catches degradation separately | Multiple detection layers |

---

## 26. External Scan

Cross-pollinated from OB-REQ-122 (Flakiness Detection). In testing: flakiness detection
is a solved problem (Google's DeFlaker, Spotify's FlakyBot). For AI dispatches: no known
tooling exists. This is novel — applying test flakiness concepts to AI prompt reliability.
The 20% threshold is adapted from industry (typical test flakiness threshold is 10-15%),
raised for AI's inherent non-determinism.

---

## 27. Security Considerations

- Flakiness data contains prompt hashes, not raw prompts. Low sensitivity.
- Root cause analysis may reference context file names — keep reports local.
- No network exposure of flakiness data in v1.

---

## 28. Performance / Resource

| Metric | Target | Notes |
|--------|--------|-------|
| Flakiness calculation (14-day, <10K entries) | <1s | JSONL scan + grouping |
| Prompt hash computation | <1ms per prompt | SHA-256 is fast |
| CLI output | <2s total | Includes calculation + formatting |
| Memory | <50MB | Stream audit entries |

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

Not yet populated. Will be filled during first build sprint implementing flakiness detection.

---

## 32. AI Assumptions

Not yet populated. Will capture model assumptions made during build.

---

## 33. AI Cost

Not yet populated. Will track token/cost data from build sprints referencing this spec.

---

## 34. Notes

- The distinction between "flaky" and "broken" is critical. A broken task (100% failure)
  has a clear fix: change the prompt. A flaky task (25% failure) may need deeper
  investigation: is it the model? The context? Temperature? This is why root cause
  categorization matters even if it's heuristic.
- The 20% threshold was chosen because AI non-determinism means some variation is EXPECTED.
  Testing flakiness thresholds (10%) would flag nearly every AI dispatch as flaky.

---

## 35. Change History

| Version | Date | What Changed |
|---------|------|-------------|
| 1.0 | 2026-03-20 | Initial. Cross-pollinated from OB-REQ-122. 12 requirements. Adapted threshold (20% vs 10%) for AI non-determinism. |
| 1.1 | 2026-03-22 | Filled to 35 sections. Added CORE-STD-012, CORE-STD-013, CORE-IFS-005 refs. Approval (Mark, Session 84). |
