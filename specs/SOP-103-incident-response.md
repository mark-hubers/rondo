# SOP-103: Incident Response

*What to do when Rondo breaks in production — dispatch failures, cost overruns, data loss, provider outages.*

**Created:** 2026-03-18 | **Updated:** 2026-03-22 | **Status:** DESIGNED
**Classification:** open
**Version:** 0.2
**Owner:** Mark G. Hubers
**Reviewed:** not-yet
**Supersedes:** none
**Universal procedure** — same topic number across all products (DEC-017)
**Product:** Rondo
**Matches:** CORE-SOP-004, Caliber-SOP-103, Rondo-SOP-103
**References:** CORE-STD-012 (Requirement Readiness), CORE-STD-013 (TrackerData), CORE-IFS-005 (MCP Standard)

---

## 1. Purpose & Scope

**What this SOP does:** Defines how to detect, triage, respond to, and recover from
incidents affecting Rondo's dispatch operations. Covers provider outages, cost overruns,
data loss, overnight batch failures, and configuration errors.

**IN scope:**
- Incident severity classification
- Detection and alerting
- Triage and response steps
- Recovery procedures
- Post-incident review

**OUT scope:**
- Build/test failures (SOP-101 covers that)
- Release rollback (SOP-102 covers that)
- OB or Caliber incidents (their own SOP-103)

**Users:** Mark (primary). Claude AI agents dispatching to other models. Future: teams needing multi-model AI orchestration, batch processing, cost optimization across AI providers.

---

## 2. The Problem

Rondo dispatches to AI providers that cost money and run unattended overnight. When
something breaks — a provider goes down, costs spike, results are corrupted, or the
overnight batch hangs — there's no documented response procedure. Without one, Mark
discovers problems hours late, wastes money on failing dispatches, and loses overnight
build time. This SOP defines the response playbook.

---

## 3. Requirements

| # | Requirement | Priority |
|---|------------|----------|
| 1 | Severity classification (SEV-1 to SEV-3) for all incident types | MUST |
| 2 | Detection within 5 minutes for SEV-1 (cost overrun, total failure) | MUST |
| 3 | Automated alerting via REQ-105 notification channels | MUST |
| 4 | Documented response steps per incident type | MUST |
| 5 | Post-incident review (PIR) within 24 hours of resolution | SHOULD |
| 6 | Incident log in morning report | MUST |
| 7 | Recovery time target: <15 min for SEV-1, <1 hour for SEV-2 | SHOULD |

---

## 4. Architecture / Design

### Severity Classification

| Severity | Criteria | Example | Response Time |
|----------|----------|---------|---------------|
| **SEV-1** | Total dispatch failure or uncontrolled cost | All providers down, budget exceeded by 2x | Immediate (within 5 min) |
| **SEV-2** | Degraded operation or partial failure | One provider down, overnight batch 50% failed | Within 30 min |
| **SEV-3** | Minor issue, no immediate impact | Slow responses, single task failure | Next business day |

### Detection → Response Flow

```
Event detected (REQ-105 notification OR manual observation)
    │
    ▼
Classify severity (SEV-1/2/3)
    │
    ▼
Execute response playbook (per incident type)
    │
    ▼
Verify recovery
    │
    ▼
Log incident in morning report
    │
    ▼
Post-incident review (within 24h for SEV-1/2)
```

---

## 5. Data Model

Incidents are logged in the audit trail (STD-113) and summarized in the morning report.
No separate incident database in v1.

| Field | Type | Purpose |
|-------|------|---------|
| `incident_type` | str | provider_outage/cost_overrun/data_loss/batch_failure/config_error |
| `severity` | str | SEV-1/SEV-2/SEV-3 |
| `detected_at` | datetime | When the incident was detected |
| `resolved_at` | datetime | When normal operation resumed |
| `impact` | str | What was affected (tasks, cost, data) |

---

## 6. Data Boundary

**What this produces:**

| Output | Format | Consumer |
|--------|--------|----------|
| Incident log entries | Audit trail (STD-113) | Morning report, post-incident review |
| Incident summary | Morning report section | Mark |
| Post-incident review | Markdown file | Future reference |

**What this consumes:**

| Input | Format | Producer |
|-------|--------|----------|
| Notifications | REQ-105 channels | Dispatch events |
| Provider health | REQ-109 health checks | Provider adapters |
| Cost data | STD-113 audit trail | Dispatch results |

---

## 7. MCP / API Interface

Future: an MCP tool per CORE-IFS-005 could accept incident reports and trigger automated
response actions (e.g., pause all dispatches, switch to fallback provider).

---

## 8. States & Modes

### Incident Lifecycle

| State | Meaning | Transitions To |
|-------|---------|---------------|
| **DETECTED** | Problem identified | TRIAGED |
| **TRIAGED** | Severity assigned | RESPONDING |
| **RESPONDING** | Active response underway | RESOLVED or ESCALATED |
| **ESCALATED** | Beyond automated fix, needs Mark | RESOLVED |
| **RESOLVED** | Normal operation restored | REVIEWED |
| **REVIEWED** | Post-incident review complete | CLOSED |

---

## 9. Configuration

```toml
[incident]
auto_pause_on_sev1 = true         # Auto-pause dispatches on SEV-1
cost_overrun_multiplier = 2.0     # SEV-1 if actual > budget * multiplier
batch_failure_threshold_pct = 50  # SEV-2 if >50% of overnight tasks fail
pir_required_for = ["SEV-1", "SEV-2"]  # Post-incident review required for these
```

---

## 10. Rules & Constraints

1. **SEV-1 pauses dispatches.** Automatic. Don't keep spending money on failing dispatches. Violation ID: `SOP103-PAUSE-SEV1`
2. **Never ignore cost overruns.** Budget exceeded by 2x is always SEV-1 regardless of dispatch success. Violation ID: `SOP103-COST-SEV1`
3. **PIR is not blame.** Post-incident reviews focus on systemic fixes, not individual fault. Violation ID: `SOP103-NO-BLAME`
4. **Morning report includes all incidents.** Even resolved ones. Mark needs full visibility. Violation ID: `SOP103-REPORT-ALL`

---

## 11. Quality Attributes

| Attribute | Target | Rationale |
|-----------|--------|-----------|
| Detection speed | <5 min for SEV-1 | Money is being wasted every minute |
| Recovery speed | <15 min for SEV-1 | Overnight batch has limited time |
| Documentation | Every incident logged | Enables pattern detection over time |
| Prevention | PIR produces at least 1 actionable improvement | Learn from every incident |

---

## 12. Shared Patterns

### Response Playbooks

**Provider Outage:**
1. Confirm provider is down (not just slow): `ai-keys.py test`
2. Check provider status page
3. Switch to fallback provider if available
4. If no fallback, pause dispatches
5. Resume when provider recovers, re-run failed tasks

**Cost Overrun:**
1. Pause all dispatches immediately
2. Check audit trail: which tasks caused the overrun?
3. Check for runaway loops (task retrying indefinitely)
4. Adjust budget or batch size
5. Resume with corrected configuration

**Overnight Batch Failure:**
1. Check morning report for failure details
2. Identify failed tasks vs passed tasks
3. Check if failure is systemic (all tasks) or isolated (specific tasks)
4. Re-run failed tasks individually if isolated
5. If systemic, check preflight (REQ-103) and provider health

**Data Loss (results not saved):**
1. Check if OAResult files exist in configured results directory
2. Check if audit trail has the dispatch records
3. If OB-connected, check if `ob store-result` can recover from files
4. Re-run affected tasks if no recovery possible

**Configuration Error:**
1. Identify the misconfigured value from error messages
2. Fix config file (`.rondo/config.toml` or `rondo.toml`)
3. Run `rondo preflight` to verify fix
4. Resume dispatches

---

## 13. Integration Points

| Integration | Spec | Direction | Contract |
|-------------|------|-----------|----------|
| Notifications | REQ-105 | Inbound | Incident detection via alerts |
| Provider health | REQ-109 | Inbound | Provider outage detection |
| Preflight | REQ-103 | Internal | Post-recovery verification |
| Morning report | REQ-101 | Outbound | Incident summary |
| Audit trail | STD-113 | Outbound | Incident log entries |

---

## 14. Standards Applied

| Standard | How Applied |
|----------|-------------|
| CORE-STD-010 (Error Resilience) | Dispatch failures don't cascade to other tasks |
| CORE-STD-012 (Requirement Readiness) | Each requirement tagged with readiness state |
| CORE-STD-013 (TrackerData) | Incident events logged as trackerdata entries |
| CORE-IFS-005 (MCP Standard) | Future MCP tool for incident management |

---

## 15. Self-Correction

- If the same incident type recurs 3 times within 30 days, the PIR must include a
  systemic fix (automated detection, config change, or code fix) — not just "we'll watch it."
- If auto-pause fires but the incident is a false alarm (provider was actually fine),
  adjust the detection threshold and log the false positive for calibration.
- If recovery takes >15 min for SEV-1, the PIR must analyze why and produce a faster
  recovery procedure for next time.

---

## 16. Assumptions

| # | Assumption | If Wrong |
|---|-----------|----------|
| A1 | REQ-105 notifications reliably detect incidents | May need external monitoring |
| A2 | Provider status pages are accurate | May need independent health checks |
| A3 | Single operator (Mark) can respond to all incidents | May need on-call rotation for team use |
| A4 | Overnight incidents can wait until morning for non-SEV-1 | If batch is time-sensitive, may need immediate response |

---

## 17. Success Criteria

| # | Criterion | How to Verify |
|---|-----------|---------------|
| 1 | SEV-1 detected within 5 minutes | Simulated provider outage |
| 2 | Auto-pause stops dispatches on SEV-1 | Cost overrun simulation |
| 3 | Recovery from provider outage in <15 min | Timed drill |
| 4 | PIR produced within 24h of SEV-1/2 | Process check |
| 5 | Incident appears in morning report | Report test |

---

## 18. Build Notes / Estimate

| Item | Estimate |
|------|----------|
| Auto-pause mechanism | 1 day |
| Severity classifier | 0.5 day |
| Incident logging to audit trail | 0.5 day |
| Morning report incident section | 0.5 day |
| PIR template | 0.5 day |
| Tests | 1 day |
| Total | ~4 days |

---

## 19. Test Categories

| Category | What | Count (est.) |
|----------|------|-------------|
| Unit | Severity classification logic | 4 |
| Integration | Detection → pause → recovery flow | 3 |
| Simulation | Provider outage, cost overrun, batch failure | 3 |
| Reporting | Incident in morning report | 2 |

---

## 20. Failure Modes

| Failure | Impact | Mitigation |
|---------|--------|------------|
| Detection fails (silent incident) | Uncontrolled cost/failure | Morning report catches next day |
| Auto-pause too aggressive | False stops | Configurable thresholds |
| PIR not done (skipped) | No learning | Automated reminder 24h after resolution |
| Recovery steps wrong | Prolonged incident | Test playbooks regularly |

---

## 21. Dependencies + Used By

| Depends On | Why |
|------------|-----|
| REQ-105 | Notification channels for incident detection |
| REQ-109 | Provider health monitoring |
| REQ-103 | Preflight for post-recovery verification |
| STD-113 | Audit trail for incident logging |

| Used By | Why |
|---------|-----|
| REQ-101 | Morning report includes incident summary |
| All Rondo operators | Entry point for incident handling |

---

## 22. Decisions

| # | Decision | Date | Why |
|---|----------|------|-----|
| D1 | 3-level severity (SEV-1/2/3) | 2026-03-22 | Simple, clear, actionable |
| D2 | Auto-pause on SEV-1 | 2026-03-22 | Don't keep wasting money on failing dispatches |
| D3 | PIR required for SEV-1/2, optional for SEV-3 | 2026-03-22 | Proportional effort |
| D4 | No separate incident database in v1 | 2026-03-22 | Audit trail + morning report is sufficient |

---

## 23. Open Questions

| # | Question | Impact | Status |
|---|----------|--------|--------|
| Q1 | Should there be an `rondo incident` CLI command for manual incident logging? | Structured incident tracking | OPEN |
| Q2 | Should auto-pause have a configurable cooldown before auto-resume? | Balance automation vs manual control | OPEN |
| Q3 | Should PIRs be stored in a structured format for trend analysis? | Long-term incident tracking | OPEN — markdown is fine for now |

---

## 24. Glossary

| Term | Definition |
|------|-----------|
| **Incident** | An event that disrupts normal Rondo operation |
| **SEV-1** | Critical incident requiring immediate response |
| **SEV-2** | Significant incident requiring timely response |
| **SEV-3** | Minor incident, next-business-day response |
| **PIR** | Post-Incident Review — structured analysis after resolution |
| **Auto-pause** | Automatic halt of dispatches when SEV-1 is detected |

---

## 25. Risk / Criticality

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Overnight cost overrun undetected | Medium | Hundreds of dollars wasted | Auto-pause + budget alerts |
| Provider outage during critical batch | Low | Lost overnight results | Fallback providers (REQ-109) |
| Incident response procedure not followed | Medium | Prolonged incident | Regular playbook drills |

---

## 26. External Scan

Incident response follows SRE best practices (Google SRE book). Severity classification
matches PagerDuty SEV-1/2/3 standard. Post-incident review follows blameless postmortem
pattern (Etsy, Google). Auto-pause is analogous to circuit breaker pattern in microservices.

---

## 27. Security Considerations

- Incident logs may contain error messages with file paths or config details. Keep
  audit trail permission-restricted.
- PIR documents should not include API keys or credentials, even if they were part
  of the incident (e.g., key rotation after compromise).
- Auto-pause mechanism must not be bypassable by unauthorized parties.

---

## 28. Performance / Resource

| Metric | Target | Notes |
|--------|--------|-------|
| Incident detection | <5 min for SEV-1 | Based on REQ-105 notification latency |
| Auto-pause activation | <1 second after detection | In-process flag, no external calls |
| Recovery verification | <1 min via `rondo preflight` | Quick environment check |

---

## 29. Approval Record

| Reviewer | Date | Verdict | Notes |
|----------|------|---------|-------|
| Mark Hubers | 2026-03-22 | APPROVED | Session 84 — built from stub, full 35 sections |

---

## 30. AI Review

Not yet performed. Scheduled for cross-spec review after all Rondo specs reach 35 sections.

---

## 31. AI Went Wrong

Not yet populated. Will be filled during first real incident.

---

## 32. AI Assumptions

Not yet populated. Will capture assumptions during incident handling.

---

## 33. AI Cost

Not yet populated. Will track cost impact of incidents.

---

## 34. Notes

- This SOP was originally a stub (RESERVED status, Session 79). Session 84 built it out
  to full 35 sections with severity classification, playbooks, and PIR process.
- The auto-pause mechanism is the single most important feature. Without it, a cost
  overrun at 2am accumulates for 6 hours before Mark checks in the morning.
- PIR is "blameless" — focus on systemic improvements, not who caused the incident.

---

## 35. Change History

| Version | Date | What Changed |
|---------|------|-------------|
| 0.1 | 2026-03-18 | Initial stub. Reserved number. Session 79. |
| 0.2 | 2026-03-22 | Full build from stub. 7 requirements, severity classification, 5 response playbooks, PIR process. Added CORE-STD-012, CORE-STD-013, CORE-IFS-005 refs. Approval (Mark, Session 84). |
