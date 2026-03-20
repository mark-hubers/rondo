# REQ-105: Dispatch Notifications

*Tell Mark when things finish, fail, or cost too much. No silent overnight surprises.*

**Product:** Rondo
**Category:** REQ
**Created:** 2026-03-20 | **Updated:** 2026-03-20 | **Status:** DESIGNED
**Classification:** open
**Version:** 1.0
**Owner:** Mark G. Hubers
**Reviewed:** not-yet
**Depends on:** REQ-100 (Core), REQ-101 (Automation), STD-113 (Audit Trail) | **Used by:** IFS-102 (OB Integration)
**Cross-pollinated from:** OB-REQ-118 (Notifications) — adapted from methodology notifications to dispatch notifications

---

## 3. Requirements

| # | Requirement | Priority | Verified By |
|---|------------|----------|-------------|
| 1 | Notify on round completion: round_name, status (done/partial/error), duration, cost, finding count | MUST | Notify test |
| 2 | Notify on dispatch failure: task_name, error_code, error_message | MUST | Failure test |
| 3 | Notify on budget threshold: "Spent $X of $Y monthly budget (Z%)" when crossing 50%, 75%, 90% | MUST | Budget test |
| 4 | Notify on rate limit: "Rate limited. Resets at: {time}. Pausing dispatches." | SHOULD | Rate test |
| 5 | Notification channels: terminal (stdout), file (notification log), macOS notification center (osascript) | MUST | Channel test |
| 6 | Channel selection configurable: `[notifications] channels = ["terminal", "macos"]` | SHOULD | Config test |
| 7 | Quiet mode: `--quiet` suppresses terminal notifications. File + macOS still fire. | SHOULD | Quiet test |
| 8 | Morning report = the primary notification for overnight runs. Always generated (CORE-STD-010). | MUST | Report test |
| 9 | Notification deduplication: don't send "rate limited" 50 times in a row. Once per state change. | SHOULD | Dedup test |
| 10 | When OB-connected: OB may subscribe to notifications via OAResult event metadata | SHOULD | Integration test |

---

## 9. Configuration

```toml
[notifications]
channels = ["terminal", "macos"]
budget_thresholds = [50, 75, 90]      # Percent of monthly budget
on_completion = true
on_failure = true
on_rate_limit = true
deduplicate_interval_sec = 300        # Don't repeat same notification within 5 min
```

---

## 10. Rules & Constraints

1. **Deduplicate.** Same notification state → one notification, not N. Violation ID: `REQ105-DEDUP`
2. **Morning report is mandatory.** Even if all other notifications are off, overnight runs get a report. Violation ID: `REQ105-MORNING`
3. **Budget alerts always on.** Budget threshold notifications cannot be disabled. Spending money deserves visibility. Violation ID: `REQ105-BUDGET-ALWAYS`

---

## 35. Change History

| Version | Date | What Changed |
|---------|------|-------------|
| 1.0 | 2026-03-20 | Initial. Cross-pollinated from OB-REQ-118. 10 requirements. |
