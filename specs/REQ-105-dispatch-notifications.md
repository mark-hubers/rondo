# REQ-105: Dispatch Notifications

*Tell Mark when things finish, fail, or cost too much. No silent overnight surprises.*

**Product:** Rondo
**Category:** REQ
**Created:** 2026-03-20 | **Updated:** 2026-03-22 | **Status:** DESIGNED
**Classification:** open
**Version:** 1.1
**Owner:** Mark G. Hubers
**Reviewed:** not-yet
**Depends on:** REQ-100 (Core), REQ-101 (Automation), STD-113 (Audit Trail), REQ-104, Rondo-IFS-100 | **Used by:** Rondo-IFS-102 (OB Integration)
**Cross-pollinated from:** OB-REQ-118 (Notifications) — adapted from methodology notifications to dispatch notifications
**References:** CORE-STD-012 (Requirement Readiness), CORE-STD-013 (TrackerData), CORE-STD-021 (MCP Standard)

---

## 1. Purpose & Scope

**What this spec does:** Defines how Rondo notifies Mark about dispatch outcomes — completions, failures, budget thresholds, and rate limit events. The core principle: overnight runs must never fail silently. Every significant event reaches Mark through at least one channel.

**IN scope:**
- Notification triggers (completion, failure, budget, rate limit)
- Notification channels (terminal, file log, macOS notification center)
- Channel configuration and quiet mode
- Deduplication logic
- Morning report as primary overnight notification

**OUT scope:**
- Audit trail storage (STD-113 owns that)
- Trend alerting logic (REQ-106 owns that)
- Email/SMS notifications (not in v1 scope)

**Users:** Mark (primary). Claude AI agents dispatching to other models. Future: teams needing multi-model AI orchestration, batch processing, cost optimization across AI providers.

---

## 2. The Problem

Without notifications, overnight runs are silent. A batch that fails at 2am isn't discovered
until 8am when Mark checks manually. A rate limit that blocks 10 dispatches wastes time
silently. A budget overrun accumulates unnoticed. Notifications close the feedback loop
between Rondo's execution and Mark's awareness.

---

## 3. Requirements


*All requirements use MUST/SHOULD priority per CORE-STD-012.*

| ID | Requirement | Priority | Verified By |
|----|-------------|----------|-------------|
| 001 | Notify on round completion: round_name, status (done/partial/error), duration, cost, finding count | MUST | Notify test |
| 002 | Notify on dispatch failure: task_name, error_code, error_message | MUST | Failure test |
| 003 | Notify on budget threshold: "Spent $X of $Y monthly budget (Z%)" when crossing 50%, 75%, 90% | MUST | Budget test |
| 004 | Notify on rate limit: "Rate limited. Resets at: {time}. Pausing dispatches." | SHOULD | Rate test |
| 005 | Notification channels: terminal (stdout), file (notification log), macOS notification center (osascript) | MUST | Channel test |
| 006 | Channel selection configurable: `[notifications] channels = ["terminal", "macos"]` | SHOULD | Config test |
| 007 | Quiet mode: `--quiet` suppresses terminal notifications. File + macOS still fire. | SHOULD | Quiet test |
| 008 | Morning report = the primary notification for overnight runs. Always generated (CORE-STD-010). | MUST | Report test |
| 009 | Notification deduplication: don't send "rate limited" 50 times in a row. Once per state change. | SHOULD | Dedup test |
| 010 | When OB-connected: OB may subscribe to notifications via OAResult event metadata | SHOULD | Integration test |


---

## 4. Architecture / Design

```
Dispatch Event (completion, failure, rate limit, budget)
    │
    ▼
Notification Engine
    ├── Dedup filter (same state → skip)
    ├── Channel router
    │   ├── Terminal (stdout)
    │   ├── File (notification.log)
    │   └── macOS (osascript display notification)
    └── OAResult metadata (when OB-connected)
```

The notification engine is a thin layer between dispatch events and output channels.
It does not store state beyond the dedup window (last notification per event type).

---

## 5. Data Model

Notifications are ephemeral — not persisted to a database. The notification log file
is a simple append-only text log for overnight debugging. Dedup state is in-memory only
(reset between `rondo run` invocations, preserved within an overnight batch).

| Field | Type | Purpose |
|-------|------|---------|
| `event_type` | str | completion/failure/budget/rate_limit |
| `message` | str | Human-readable notification text |
| `timestamp` | datetime | When the event occurred |
| `channel` | str | Where it was sent (terminal/file/macos) |

---

## 6. Data Boundary

**What this produces:**

| Output | Format | Consumer |
|--------|--------|----------|
| Terminal notifications | Formatted text on stdout | Mark (interactive) |
| File log | Append-only text | Mark (post-mortem debugging) |
| macOS notifications | System notification center | Mark (visual alert) |
| OAResult event metadata | JSON | OB (when connected) |

**What this consumes:**

| Input | Format | Producer |
|-------|--------|----------|
| Dispatch events | Internal Python events | REQ-100 core engine |
| Budget data | Aggregated from audit trail | STD-113 / REQ-104 |
| Rate limit events | Stream-JSON from Claude | Rondo-IFS-100 |
| Config | TOML | `.rondo/config.toml` |

---

## 7. MCP / API Interface

Not applicable for initial release. Future: an MCP tool per CORE-STD-021 could push
notifications to AI agents, enabling automated response to dispatch failures (e.g., AI
agent retries failed task with different model after receiving failure notification).

---

## 8. States & Modes

| Mode | Trigger | Behavior |
|------|---------|----------|
| **Normal** | Default | All configured channels active |
| **Quiet** | `--quiet` flag | Terminal suppressed, file + macOS active |
| **Batch** | Overnight mode | Dedup active, morning report is primary output |

Dedup state per event type: last_sent_at + last_message. If same event type + same
message within deduplicate_interval_sec → skip.

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
4. **Accessible.** macOS notifications use `display notification` (no blue links, no popups that require mouse interaction). Violation ID: `REQ105-ACCESSIBLE`

---

## 11. Quality Attributes

| Attribute | Target | Rationale |
|-----------|--------|-----------|
| Reliability | Every failure notification is delivered to at least one channel | Silent failures are the worst kind |
| Latency | <100ms from event to notification | Notifications must not slow dispatch |
| Dedup effectiveness | <3 duplicate notifications per overnight batch | Noise reduction |
| Accessibility | macOS notifications compatible with VoiceOver | Mark's accessibility needs |

---

## 12. Shared Patterns

- **Dedup-by-state-change:** Only notify when state changes (rate_limited → not_limited),
  not on every check. Same pattern as monitoring systems (PagerDuty, Datadog).
- **Channel multiplexing:** Same event → multiple channels. Terminal for interactive,
  macOS for overnight, file for debugging. Similar to logging levels but for humans.
- **Mandatory floor:** Budget alerts cannot be disabled. Borrowing from financial
  compliance — spending notifications are always on.

---

## 13. Integration Points

| Integration | Spec | Direction | Contract |
|-------------|------|-----------|----------|
| Dispatch engine | REQ-100 | Inbound | Completion/failure events |
| Budget tracking | REQ-104 / STD-113 | Inbound | Cost threshold crossings |
| Rate limit | Rondo-IFS-100 | Inbound | Rate limit state changes |
| Morning report | REQ-101 | Outbound | Notification summary section |
| OB integration | Rondo-IFS-102 | Outbound | Event metadata in OAResult |

---

## 14. Standards Applied

| Standard | How Applied |
|----------|-------------|
| CORE-STD-010 (Error Resilience) | Notification channel failure → fall back to file log |
| CORE-STD-012 (Requirement Readiness) | Each requirement tagged with readiness state |
| CORE-STD-013 (TrackerData) | Notification events logged as trackerdata entries |
| CORE-STD-021 (MCP Standard) | Future MCP tool for push notifications to AI agents |

---

## 15. Self-Correction

- If macOS notification channel fails (osascript error), Rondo falls back to file + terminal
  and logs a warning: "macOS notifications unavailable — using terminal + file only."
- If dedup interval is too aggressive (notifications missed), the morning report includes
  ALL events regardless of dedup — ensuring nothing is lost.
- Budget threshold crossings are recalculated on every dispatch, not cached. If cost
  tracking was inaccurate, the next dispatch self-corrects the threshold check.

---

## 16. Assumptions

| # | Assumption | If Wrong |
|---|-----------|----------|
| A1 | macOS notification center is available | Need fallback (terminal only) on Linux |
| A2 | File log is writable | If permissions fail, fall back to terminal only |
| A3 | Dedup interval of 5 minutes is appropriate | May need per-event-type intervals |
| A4 | Three channels (terminal, file, macOS) are sufficient | May need email/Slack for team use |

---

## 17. Success Criteria

| # | Criterion | How to Verify |
|---|-----------|---------------|
| 1 | Round completion → terminal + macOS notification | Channel test |
| 2 | Dispatch failure → failure notification with error details | Failure test |
| 3 | Budget at 75% → budget alert fires | Threshold test |
| 4 | 10 rate limit events → only 1 notification (dedup) | Dedup test |
| 5 | Overnight batch → morning report generated with all events | Report test |

---

## 18. Build Notes / Estimate

| Item | Estimate |
|------|----------|
| Notification engine (event → channels) | 1 day |
| Channel implementations (terminal, file, macOS) | 1 day |
| Dedup filter | 0.5 day |
| Budget threshold checking | 0.5 day |
| Config integration | 0.5 day |
| Tests | 1 day |
| Total | ~4.5 days |

---

## 19. Test Categories

| Category | What | Count (est.) |
|----------|------|-------------|
| Unit | Channel routing, dedup filter, threshold calculation | 8 |
| Integration | Full dispatch → notification flow | 4 |
| Channel | Each channel (terminal, file, macOS) independently | 6 |
| Dedup | Same event repeated → single notification | 3 |
| Config | Enable/disable channels, quiet mode | 4 |

---

## 20. Failure Modes

| Failure | Impact | Mitigation |
|---------|--------|------------|
| macOS osascript fails | No visual notification | Fall back to terminal + file |
| File log unwritable | No persistent log | Fall back to terminal, warn |
| All channels fail | Silent operation | Morning report is the last resort |
| Dedup too aggressive | Missed notifications | Morning report includes all events |

**Emergency Bypass:** BREAK_GLASS override via `break_glass_events` table audit trail (CORE-STD-015). Notification guards (mandatory budget alerts, morning report requirement) can be suspended under DR mode with human approval for silent batch operations.

---

## 21. Dependencies + Used By

| Depends On | Why |
|------------|-----|
| REQ-100 | Core dispatch events (completion, failure) |
| REQ-101 | Morning report generation |
| STD-113 | Budget data from audit trail |
| Rondo-IFS-100 | Rate limit events from Claude CLI |

| Used By | Why |
|---------|-----|
| Rondo-IFS-102 | OB integration reads notification events from OAResult |

---

## 22. Decisions

| # | Decision | Date | Why |
|---|----------|------|-----|
| D1 | Three channels: terminal, file, macOS | 2026-03-20 | Covers interactive, debugging, and overnight use |
| D2 | Budget alerts always on, cannot disable | 2026-03-20 | Money visibility is non-negotiable |
| D3 | Dedup by state change, not by timer | 2026-03-20 | Timer-based dedup misses real state changes |
| D4 | Morning report as mandatory fallback | 2026-03-20 | If all channels fail, morning report is the safety net |

---

## 23. Open Questions

| # | Question | Impact | Status |
|---|----------|--------|--------|
| Q1 | Should Rondo support email/Slack channels for team use? | Scope expansion | OPEN — not in v1 |
| Q2 | Should budget alerts include projected end-of-month cost? | More actionable alerts | OPEN |
| Q3 | Should there be a "critical only" quiet mode (failures + budget, no completions)? | Noise reduction for overnight | OPEN |

---

## 24. Glossary

| Term | Definition |
|------|-----------|
| **Notification** | Human-directed alert about a dispatch event |
| **Channel** | Delivery mechanism for notifications (terminal, file, macOS) |
| **Deduplication** | Suppressing repeated notifications for the same state |
| **Budget threshold** | Percentage of monthly budget that triggers an alert |
| **Morning report** | Comprehensive overnight summary — mandatory notification |

---

## 25. Risk / Criticality

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Notification fatigue (too many alerts) | Medium | Mark ignores important ones | Dedup + quiet mode + morning report summary |
| macOS notifications blocked by DND | Medium | Missed alerts | File log + morning report as fallback |
| Budget alert fires too late | Low | Overrun already happened | Check on EVERY dispatch, not just periodically |

---

## 26. External Scan

Cross-pollinated from OB-REQ-118 (Notifications). Industry patterns: Datadog monitors
(multi-channel alerting), PagerDuty (dedup + escalation), GitHub Actions notifications
(per-workflow completion). Rondo's approach is simpler — local channels only, no
escalation chains.

---

## 27. Security Considerations

- Notifications may contain cost data and task names. Terminal and macOS channels are
  local-only. File log should be permission-restricted (0600).
- macOS notification center content is visible on lock screen — consider sensitivity of
  task names. Budget amounts are not sensitive.
- No network transmission of notification content in v1 (all local channels).

---

## 28. Performance / Resource

| Metric | Target | Notes |
|--------|--------|-------|
| Notification delivery | <100ms per channel | Must not delay dispatch |
| Dedup check | <1ms | In-memory dict lookup |
| File log write | <10ms | Append-only, buffered |
| macOS notification | <500ms | osascript subprocess |

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

Not yet populated. Will be filled during first build sprint implementing notifications.

---

## 32. AI Assumptions

Not yet populated. Will capture model assumptions made during build.

---

## 33. AI Cost

Not yet populated. Will track token/cost data from build sprints referencing this spec.

---

## 34. Notes

- macOS notifications use `osascript -e 'display notification "msg" with title "Rondo"'`.
  This is accessible and doesn't require any GUI interaction to dismiss.
- Budget alerts at 50/75/90% mirror AWS billing alerts. The thresholds are configurable
  but the feature cannot be disabled.
- The morning report is both a notification and a report — it serves as the catch-all for
  everything that happened overnight, even if individual notifications were deduped.

---

### Feature Maturity

| Feature | Maturity | Evidence | Retest |
|---------|----------|----------|--------|
| Dispatch notifications | THEORY | Specced for alerting on task completion | Phase 2 build |
| Failure alerting | THEORY | Specced for immediate alert on task failure | Phase 2 build |
| Summary reports | THEORY | Specced for batch completion summaries | Phase 2 build |


## 35. Change History

| Version | Date | What Changed |
|---------|------|-------------|
| 1.0 | 2026-03-20 | Initial. Cross-pollinated from OB-REQ-118. 10 requirements. |
| 1.1 | 2026-03-22 | Filled to 35 sections. Added CORE-STD-012, CORE-STD-013, CORE-STD-021 refs. Approval (Mark, Session 84). |
