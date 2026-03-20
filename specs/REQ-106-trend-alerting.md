# REQ-106: Dispatch Trend Alerting

*Detect when dispatches are getting slower, costlier, or less reliable. Catch API degradation before it ruins an overnight run.*

**Product:** Rondo
**Category:** REQ
**Created:** 2026-03-20 | **Updated:** 2026-03-20 | **Status:** DESIGNED
**Classification:** open
**Version:** 1.0
**Owner:** Mark G. Hubers
**Reviewed:** not-yet
**Supersedes:** none
**Depends on:** REQ-100 (Core), STD-113 (Dispatch Audit Trail), CORE-STD-011 (Self-Correction) | **Used by:** REQ-101 (Automation), IFS-102 (OB Integration)
**Cross-pollinated from:** OB-REQ-121 (Trend & Regression Alerting) — adapted from methodology trends to dispatch execution trends

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
- Caliber-side quality trends (Caliber-REQ-102)

---

## 3. Requirements

### Success Rate Trends

| # | Requirement | Priority | Verified By |
|---|------------|----------|-------------|
| 1 | Track per-model success rate: (done tasks / total tasks) over rolling 7-day window | MUST | Rate test |
| 2 | Alert if any model's success rate drops >10% from 7-day baseline | MUST | Alert test |
| 3 | Track per-task-type success rate: review tasks vs fix tasks vs generation tasks | SHOULD | Type test |
| 4 | Flakiness detection: if same task definition succeeds >60% and fails >20% of the time, flag as flaky | SHOULD | Flaky test |

### Cost Trends

| # | Requirement | Priority | Verified By |
|---|------------|----------|-------------|
| 5 | Track per-model cost: average cost_usd per task over rolling 7-day window | MUST | Cost test |
| 6 | Alert if per-model cost increases >25% from 7-day baseline | MUST | Cost alert test |
| 7 | Overnight budget projection: "At current rate, tonight's batch will cost ~$X" shown before overnight starts | SHOULD | Projection test |
| 8 | Track cost efficiency: cost per output token (are we paying more for less?) | SHOULD | Efficiency test |

### Latency Trends

| # | Requirement | Priority | Verified By |
|---|------------|----------|-------------|
| 9 | Track per-model latency: average duration_sec per task over rolling 7-day window | MUST | Latency test |
| 10 | Alert if per-model latency increases >50% from baseline (API degradation signal) | MUST | Latency alert test |
| 11 | Track queue wait time separately from API time (infrastructure vs model) | SHOULD | Breakdown test |

### Alerting

| # | Requirement | Priority | Verified By |
|---|------------|----------|-------------|
| 12 | Trends calculated from dispatch audit trail (STD-113 data) | MUST | Source test |
| 13 | `rondo trends` CLI: show per-model trends for success rate, cost, latency | SHOULD | CLI test |
| 14 | `rondo trends --json` for machine-readable output | SHOULD | JSON test |
| 15 | Alert thresholds configurable in `.rondo/config.toml [trends]` section | SHOULD | Config test |
| 16 | Trend status per model: `healthy` (within baseline), `degrading` (metric worsening), `critical` (>2x threshold breach) | MUST | Status test |

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

## 17. Success Criteria

| # | Criterion | How to Verify |
|---|-----------|---------------|
| 1 | Model API degradation → latency alert within 24 hours | Latency test |
| 2 | Cost per task doubles → cost alert fires | Cost test |
| 3 | Overnight projection: predicted cost within ±30% of actual | Projection test |
| 4 | Flaky task detected after 5+ runs with mixed results | Flaky test |

---

## 35. Change History

| Version | Date | What Changed |
|---------|------|-------------|
| 1.0 | 2026-03-20 | Initial. Cross-pollinated from OB-REQ-121. 16 requirements. |
