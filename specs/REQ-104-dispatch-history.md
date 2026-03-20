# REQ-104: Dispatch History

*Every dispatch tracked: which tasks, which models, how long, how much. "Overnight runs are 20% slower this week" — now provable.*

**Product:** Rondo
**Category:** REQ
**Created:** 2026-03-20 | **Updated:** 2026-03-20 | **Status:** DESIGNED
**Classification:** open
**Version:** 1.0
**Owner:** Mark G. Hubers
**Reviewed:** not-yet
**Depends on:** REQ-100 (Core), STD-113 (Dispatch Audit Trail) | **Used by:** REQ-106 (Trend Alerting), REQ-107 (Flakiness), IFS-102 (OB Integration)
**Cross-pollinated from:** OB-REQ-115 (Test Build History) — adapted from sprint telemetry to dispatch telemetry

---

## 3. Requirements

| # | Requirement | Priority | Verified By |
|---|------------|----------|-------------|
| 1 | Per-round telemetry: round_name, total_duration_sec, task_count, passed, failed, partial, total_cost_usd | MUST | Record test |
| 2 | Per-task telemetry: task_name, model, duration_sec, api_duration_ms, tokens_in, tokens_out, cost_usd, status, confidence | MUST | Task test |
| 3 | Per-model aggregate: average cost, average duration, success rate, total dispatches — over rolling window | MUST | Model test |
| 4 | History queryable: by date range, model, task_name, round_name, status | MUST | Query test |
| 5 | `rondo history` CLI: show recent rounds with cost/duration summary | SHOULD | CLI test |
| 6 | `rondo history --model opus` CLI: show Opus-specific performance over time | SHOULD | Filter test |
| 7 | `rondo history --expensive` CLI: show most expensive rounds (cost optimization targets) | SHOULD | Cost test |
| 8 | `rondo history --json` for machine-readable output | SHOULD | JSON test |
| 9 | Calculated from STD-113 audit trail data — no separate storage needed | MUST | Source test |
| 10 | When OB-connected: dispatch history summary included in OAResult for OB's build intelligence | SHOULD | Integration test |

---

## 10. Rules & Constraints

1. **Derived from audit.** STD-113 is the source of truth. History = aggregated views of audit data. Violation ID: `REQ104-FROM-AUDIT`
2. **Per-model, not aggregate.** "Average cost" across all models hides that Opus is 10× Haiku. Per-model analysis required. Violation ID: `REQ104-PER-MODEL`

---

## 35. Change History

| Version | Date | What Changed |
|---------|------|-------------|
| 1.0 | 2026-03-20 | Initial. Cross-pollinated from OB-REQ-115. 10 requirements. |
