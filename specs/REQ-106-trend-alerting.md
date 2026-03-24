# REQ-106: Dispatch Trend Alerting

*Detect when dispatches are getting slower, costlier, or less reliable. Catch API degradation before it ruins an overnight run.*

**Product:** Rondo
**Category:** REQ
**Created:** 2026-03-20 | **Updated:** 2026-03-22 | **Status:** DESIGNED
**Classification:** open
**Version:** 1.1
**Owner:** Mark G. Hubers
**Reviewed:** not-yet
**Supersedes:** none
**Depends on:** REQ-100 (Core), STD-113 (Dispatch Audit Trail), CORE-STD-011 (Self-Correction) | **Used by:** REQ-101 (Automation), IFS-102 (OB Integration)
**Cross-pollinated from:** OB-REQ-121 (Trend & Regression Alerting) — adapted from methodology trends to dispatch execution trends
**References:** CORE-STD-012 (Requirement Readiness), CORE-STD-013 (TrackerData), CORE-IFS-005 (MCP Standard)

---

## 1. Purpose & Scope

**What this spec does:** Rondo dispatches tasks to AI models that can degrade silently: response times creep up, costs increase, success rates drop, models start returning lower-quality results. Without trend tracking, you discover the problem AFTER an overnight run costs $50 instead of $5. This spec adds rolling-window trend analysis to dispatch metrics.

**IN scope:**
- Per-model success rate trends
- Per-model cost trends (cost per task, cost per token)
- Per-model latency trends (duration_sec, api_duration_ms)
- Task flakiness detection (same task sometimes passes, sometimes fails)
- Alert thresholds for degradation
- Overnight budget projection ("at current rate, tonight will cost $X")

**OUT of scope:**
- Audit record storage (STD-113)
- Model routing decisions (REQ-100)
- Caliber-side quality trends (Caliber's trend-alerting spec)

**Users:** Mark (primary). Claude AI agents dispatching to other models. Future: teams needing multi-model AI orchestration, batch processing, cost optimization across AI providers.

---

## 2. The Problem

AI providers degrade silently. Anthropic rate limits tighten, API latency creeps up, model
quality shifts between versions. Without trend tracking, you see individual dispatch results
but miss the slow drift. A model that was 95% reliable last week is now 80% — you won't
notice until an overnight batch fails badly. Trend alerting catches the drift early.

---

## 3. Requirements

### Success Rate Trends


*All requirements use MUST/SHOULD priority per CORE-STD-012.*

| ID | Requirement | Priority | Verified By |
|----|-------------|----------|-------------|
| 001 | Track per-model success rate: (done tasks / total tasks) over rolling 7-day window | MUST | Rate test |
| 002 | Alert if any model's success rate drops >10% from 7-day baseline | MUST | Alert test |
| 003 | Track per-task-type success rate: review tasks vs fix tasks vs generation tasks | SHOULD | Type test |
| 004 | Flakiness detection: if same task definition succeeds >60% and fails >20% of the time, flag as flaky | SHOULD | Flaky test |


### Cost Trends

| ID | Requirement | Priority | Verified By |
|----|-------------|----------|-------------|
| 005 | Track per-model cost: average cost_usd per task over rolling 7-day window | MUST | Cost test |
| 006 | Alert if per-model cost increases >25% from 7-day baseline | MUST | Cost alert test |
| 007 | Overnight budget projection: "At current rate, tonight's batch will cost ~$X" shown before overnight starts | SHOULD | Projection test |
| 008 | Track cost efficiency: cost per output token (are we paying more for less?) | SHOULD | Efficiency test |


### Latency Trends

| ID | Requirement | Priority | Verified By |
|----|-------------|----------|-------------|
| 009 | Track per-model latency: average duration_sec per task over rolling 7-day window | MUST | Latency test |
| 010 | Alert if per-model latency increases >50% from baseline (API degradation signal) | MUST | Latency alert test |
| 011 | Track queue wait time separately from API time (infrastructure vs model) | SHOULD | Breakdown test |


### Alerting

| ID | Requirement | Priority | Verified By |
|----|-------------|----------|-------------|
| 012 | Trends calculated from dispatch audit trail (STD-113 data) | MUST | Source test |
| 013 | `rondo trends` CLI: show per-model trends for success rate, cost, latency | SHOULD | CLI test |
| 014 | `rondo trends --json` for machine-readable output | SHOULD | JSON test |
| 015 | Alert thresholds configurable in `.rondo/config.toml [trends]` section | SHOULD | Config test |
| 016 | Trend status per model: `healthy` (within baseline), `degrading` (metric worsening), `critical` (>2x threshold breach) | MUST | Status test |


---

## 4. Architecture / Design

```
STD-113 Audit Trail (rondo_audit.jsonl)
    │
    ▼
Trend Engine
    ├── Rolling window calculator (7-day default)
    ├── Per-model success rate tracker
    ├── Per-model cost tracker
    ├── Per-model latency tracker
    └── Threshold comparator
    │
    ▼
Alerts → Notifications (REQ-105)
       → Morning report (REQ-101)
       → CLI output (rondo trends)
       → OAResult metadata (IFS-102)
```

Trends are computed on demand from audit data — no separate trend database.
The trend engine reads the audit trail, groups by model, calculates rolling-window
averages, and compares against baseline thresholds.

---

## 5. Data Model

**Concurrency:** File-level append locking on JSONL spool files (STD-113).

No new storage. Trends are derived from STD-113 audit trail entries.

| Derived Metric | Calculation | Window |
|---------------|-------------|--------|
| Success rate | count(status=done) / count(all) per model | 7 days |
| Avg cost | sum(cost_usd) / count(dispatches) per model | 7 days |
| Avg latency | sum(duration_ms) / count(dispatches) per model | 7 days |
| Cost efficiency | sum(cost_usd) / sum(output_tokens) per model | 7 days |
| Flakiness score | status_flips / total_runs per prompt_hash | 14 days |

---

## 6. Data Boundary

**What this produces:**

| Output | Format | Consumer |
|--------|--------|----------|
| Trend alerts | Notifications | REQ-105 (notification channels) |
| Trend report | Terminal table / JSON | `rondo trends` CLI |
| Budget projection | One-liner estimate | Pre-overnight display |
| Per-model health status | healthy/degrading/critical | OAResult metadata |

**What this consumes:**

| Input | Format | Producer |
|-------|--------|----------|
| Dispatch audit trail | JSONL | STD-113 |
| Alert thresholds | TOML config | `.rondo/config.toml` |

---

## 7. MCP / API Interface

Future: an MCP tool per CORE-IFS-005 could expose trend data for AI agents to query.
Example: "Is Claude Opus degrading?" The MCP tool would return per-model health status
and trend direction, enabling automated model-switching decisions.

---

## 8. States & Modes

Per-model health states:

| State | Condition | Meaning |
|-------|-----------|---------|
| **healthy** | All metrics within baseline thresholds | Normal operation |
| **degrading** | One or more metrics exceed threshold | Warning, investigate |
| **critical** | Metric exceeds 2x threshold | Immediate attention needed |
| **insufficient_data** | <10 dispatches in window | Not enough data to trend |

State transitions happen on every trend calculation. No hysteresis (a single good
window can move from critical back to healthy). Hysteresis may be added if noisy.

**State Machine Type:** BIDIRECTIONAL
**Rationale:** Health states transition freely: healthy ↔ degrading ↔ critical based on metric calculations. No hysteresis — a single good window can move from critical back to healthy. Insufficient_data is an initial state that transitions to any other on data accumulation.
**Rollback:** Automatic — states are recalculated on every trend window. No manual intervention needed.

---

## 9. Configuration

```toml
[trends]
success_rate_drop_pct = 10         # Alert if success rate drops >10%
cost_increase_pct = 25             # Alert if cost increases >25%
latency_increase_pct = 50          # Alert if latency increases >50%
flaky_threshold_pct = 20           # Flag task as flaky if >20% failure rate with >60% success
baseline_window_days = 7           # Rolling window for baselines
```

---

## 10. Rules & Constraints

1. **Trend over point.** Single slow dispatch isn't a trend. 7-day window smooths noise. Violation ID: `REQ106-WINDOW`
2. **Per-model, not aggregate.** Model A degrading while Model B is fine looks "stable" in aggregate. Per-model catches it. Violation ID: `REQ106-PER-MODEL`
3. **Project overnight budget.** Before committing to an overnight run, tell Mark what it will likely cost. No surprises. Violation ID: `REQ106-PROJECT-COST`
4. **Flaky ≠ failing.** A task that fails 100% is broken. A task that fails 25% is FLAKY — harder to detect, harder to trust. Violation ID: `REQ106-FLAKY`

---

## 11. Quality Attributes

| Attribute | Target | Rationale |
|-----------|--------|-----------|
| Accuracy | Trends match manual audit trail analysis | Must be trustworthy |
| Timeliness | Degradation detected within 24 hours | Don't discover problems a week late |
| Noise | <2 false alerts per week | Too many alerts → ignored |
| Actionability | Every alert includes model name + metric + direction | Mark knows what to investigate |

---

## 12. Shared Patterns

- **Rolling window aggregation:** Same pattern as REQ-104 (history) and REQ-107 (flakiness).
  7-day window is the standard time horizon across all Rondo analytics specs.
- **Threshold-based alerting:** Same approach as monitoring systems (Datadog, Prometheus).
  Percentage-based thresholds relative to baseline, not absolute values.
- **Per-dimension breakdown:** Every metric tracked per model, not just globally. Same
  principle as REQ-104 (per-model history) and REQ-109 (per-model affinity).

---

## 13. Integration Points

| Integration | Spec | Direction | Contract |
|-------------|------|-----------|----------|
| Audit trail | STD-113 | Inbound | JSONL audit records |
| Notifications | REQ-105 | Outbound | Trend alerts as notifications |
| Morning report | REQ-101 | Outbound | Trend summary section |
| Flakiness | REQ-107 | Outbound | Flakiness score feeds trend health |
| OB integration | IFS-102 | Outbound | Per-model health in OAResult |
| Provider routing | REQ-109 | Advisory | Degrading model → suggest routing change |

---

## 14. Standards Applied

| Standard | How Applied |
|----------|-------------|
| CORE-STD-011 (Self-Correction) | Trend data is self-correction fuel — detect and adapt |
| CORE-STD-012 (Requirement Readiness) | Each requirement tagged with readiness state |
| CORE-STD-013 (TrackerData) | Trend calculations logged as trackerdata entries |
| CORE-IFS-005 (MCP Standard) | Future MCP tool for trend queries |

---

## 15. Self-Correction

- If a model is marked "degrading" for 3 consecutive days, the morning report escalates
  to "suggest switching to alternate model for this task type."
- If overnight budget projection is >30% wrong (predicted $10, actual $15), the projection
  algorithm is recalibrated using the last 3 overnight runs instead of 7-day average.
- If trend alerts fire but the model recovers within 24 hours (temporary API degradation),
  the trend engine notes this as a "transient event" and raises the alert threshold by 5%
  to reduce noise on future transient events.

---

## 16. Assumptions

| # | Assumption | If Wrong |
|---|-----------|----------|
| A1 | 7-day window provides meaningful baselines | May need longer window for infrequent tasks |
| A2 | 10 dispatches minimum for reliable trends | High-volume tasks may need higher minimum |
| A3 | AI provider degradation is detectable via latency/cost/success rate | Quality degradation (worse output, same metrics) is invisible |
| A4 | Budget projection based on recent average is accurate enough | Workload variation makes projection unreliable |

---

## 17. Success Criteria

| # | Criterion | How to Verify |
|---|-----------|---------------|
| 1 | Model API degradation → latency alert within 24 hours | Latency test |
| 2 | Cost per task doubles → cost alert fires | Cost test |
| 3 | Overnight projection: predicted cost within ±30% of actual | Projection test |
| 4 | Flaky task detected after 5+ runs with mixed results | Flaky test |

---

## 18. Build Notes / Estimate

| Item | Estimate |
|------|----------|
| Rolling window calculator | 1 day |
| Per-model metric trackers (3 metrics) | 1.5 days |
| Threshold comparator + alert generation | 1 day |
| Budget projection | 0.5 day |
| CLI (`rondo trends`) | 1 day |
| Tests | 1.5 days |
| Total | ~6.5 days |

---

## 19. Test Categories

| Category | What | Count (est.) |
|----------|------|-------------|
| Unit | Rolling window calculation, threshold comparison | 10 |
| Integration | Full audit → trend → alert flow | 4 |
| Alerting | Each metric type triggers correct alert | 6 |
| CLI | `rondo trends` output formatting | 4 |
| Edge case | Insufficient data, single-model, empty window | 4 |

---

## 20. Failure Modes

| Failure | Impact | Mitigation |
|---------|--------|------------|
| Insufficient dispatch data | Can't compute meaningful trends | Report "insufficient_data" status |
| Audit trail corrupted | Inaccurate baselines | Skip corrupted entries, warn |
| All models degrading simultaneously | No healthy baseline for comparison | Alert on absolute thresholds, not just relative |
| Budget projection wildly wrong | Unexpected overnight cost | Post-overnight comparison in morning report |

**Emergency Bypass:** BREAK_GLASS override via `break_glass_events` table audit trail (CORE-STD-015). Dispatch trend alerting and budget projection guards can be suspended under DR mode with human approval to allow emergency overnight runs.

---

## 21. Dependencies + Used By

| Depends On | Why |
|------------|-----|
| REQ-100 | Core dispatch framework |
| STD-113 | Audit trail (data source for all trends) |
| CORE-STD-011 | Self-correction patterns |

| Used By | Why |
|---------|-----|
| REQ-101 | Morning report includes trend summary |
| REQ-105 | Trend alerts flow through notification channels |
| REQ-107 | Flakiness detection shares trend data |
| IFS-102 | OB integration includes per-model health |

---

## 22. Decisions

| # | Decision | Date | Why |
|---|----------|------|-----|
| D1 | 7-day rolling window | 2026-03-20 | Balances noise reduction with sensitivity |
| D2 | Percentage thresholds, not absolute | 2026-03-20 | What's "slow" varies by model — percentage is universal |
| D3 | Three health states (healthy/degrading/critical) | 2026-03-20 | Simple traffic light, easy to act on |
| D4 | Budget projection before overnight | 2026-03-20 | No surprises — Mark decides go/no-go with cost estimate |

---

## 23. Open Questions

| # | Question | Impact | Status |
|---|----------|--------|--------|
| Q1 | Should trend alerts auto-switch routing (degrading model → fallback)? | Automation vs manual control | OPEN — advisory only for now |
| Q2 | Should quality degradation be tracked (output analysis, not just metrics)? | Much harder to measure | OPEN — out of v1 scope |
| Q3 | Should trend data be visualized (ASCII chart in terminal)? | Better comprehension | OPEN — nice-to-have |

---

## 24. Glossary

| Term | Definition |
|------|-----------|
| **Trend** | Direction of a metric over a rolling window (improving, stable, degrading) |
| **Baseline** | Average value of a metric over the rolling window |
| **Threshold** | Percentage deviation from baseline that triggers an alert |
| **Flakiness** | Inconsistent results from the same prompt (passes sometimes, fails sometimes) |
| **Budget projection** | Estimated cost of tonight's batch based on recent per-task costs |

---

## 25. Risk / Criticality

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Alert fatigue from noisy thresholds | Medium | Alerts ignored | Tune thresholds based on first month of data |
| Provider pricing change breaks cost trends | Low | False cost alerts | Note pricing changes in morning report |
| Model name change invalidates history | Low | Trend resets | Config-based model aliases (REQ-104 D4) |

---

## 26. External Scan

Cross-pollinated from OB-REQ-121 (Trend & Regression Alerting). Industry patterns:
Datadog APM (per-service latency trends), New Relic (error rate trending), Honeycomb
(query-driven observability). Budget projection is similar to AWS Cost Explorer forecasting.

---

## 27. Security Considerations

- Trend data contains cost information — local only, no network exposure in v1.
- Per-model performance data could reveal AI usage patterns. Keep trend reports
  permission-restricted alongside the audit trail.
- Budget projections are estimates, not guarantees — ensure morning report labels them
  clearly as projections, not commitments.

---

## 28. Performance / Resource

| Metric | Target | Notes |
|--------|--------|-------|
| Trend calculation (7-day, <10K entries) | <1s | JSONL scan + aggregation |
| Alert evaluation | <100ms | Compare computed averages against thresholds |
| CLI output | <2s total | Includes trend calculation + formatting |
| Memory | <50MB during calculation | Stream audit entries, don't load all |

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

Not yet populated. Will be filled during first build sprint implementing trend alerting.

---

## 32. AI Assumptions

Not yet populated. Will capture model assumptions made during build.

---

## 33. AI Cost

Not yet populated. Will track token/cost data from build sprints referencing this spec.

---

## 34. Notes

- The budget projection feature (req 7) is Mark's top ask — "tell me what tonight will
  cost BEFORE I commit to the overnight run." This is the most operationally valuable
  feature in this spec.
- Flakiness detection (req 4) overlaps with REQ-107 (Task Flakiness). REQ-106 detects it;
  REQ-107 analyzes root causes and tracks it long-term. The threshold is shared (20%).

---

### Feature Maturity

| Feature | Maturity | Evidence | Retest |
|---------|----------|----------|--------|
| Dispatch trend detection | THEORY | Specced for multi-dispatch trend analysis | Phase 2 build |
| Cost trend alerting | THEORY | Specced for budget overrun warnings | Phase 2 build |
| Success rate tracking | THEORY | Specced for per-model success rates | Phase 2 build |


## 35. Change History

| Version | Date | What Changed |
|---------|------|-------------|
| 1.0 | 2026-03-20 | Initial. Cross-pollinated from OB-REQ-121. 16 requirements. |
| 1.1 | 2026-03-22 | Filled to 35 sections. Added CORE-STD-012, CORE-STD-013, CORE-IFS-005 refs. Approval (Mark, Session 84). |
