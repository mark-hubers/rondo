# REQ-104: Dispatch History

*Every dispatch tracked: which tasks, which models, how long, how much. "Overnight runs are 20% slower this week" — now provable.*

**Product:** Rondo
**Category:** REQ
**Created:** 2026-03-20 | **Updated:** 2026-03-22 | **Status:** DESIGNED
**Classification:** open
**Version:** 1.1
**Owner:** Mark G. Hubers
**Reviewed:** not-yet
**Depends on:** REQ-100 (Core), STD-113 (Dispatch Audit Trail), OB-REQ-115 | **Used by:** REQ-106 (Trend Alerting), REQ-107 (Flakiness), IFS-102 (OB Integration)
**Cross-pollinated from:** OB-REQ-115 (Test Build History) — adapted from sprint telemetry to dispatch telemetry
**References:** CORE-STD-012 (Requirement Readiness), CORE-STD-013 (TrackerData), CORE-STD-021 (MCP Standard)

---

## 1. Purpose & Scope

**What this spec does:** Provides queryable dispatch telemetry so Rondo users can answer questions like "how much did last night cost?", "is Opus getting slower?", and "which task types are most expensive?" All data is derived from the STD-113 audit trail — no separate storage needed.

**IN scope:**
- Per-round and per-task telemetry views
- Per-model aggregate statistics
- History querying by date, model, task, status
- CLI interface for history inspection
- OB integration (history summary in OAResult)

**OUT scope:**
- Audit trail storage (STD-113 owns that)
- Trend alerting logic (REQ-106 owns that)
- Flakiness detection (REQ-107 owns that)

**Users:** Mark (primary). Claude AI agents dispatching to other models. Future: teams needing multi-model AI orchestration, batch processing, cost optimization across AI providers.

---

## 2. The Problem

Without dispatch history, Rondo is a black box after execution completes. Questions like
"how much did the overnight run cost?" require manual log parsing. Trend detection is
impossible without historical data. Cost optimization is guesswork without per-model
telemetry. This spec turns the audit trail into actionable intelligence.

---

## 3. Requirements


*All requirements use MUST/SHOULD priority per CORE-STD-012.*

| ID | Requirement | Priority | Verified By |
|----|-------------|----------|-------------|
| 001 | Per-round telemetry: round_name, total_duration_sec, task_count, passed, failed, partial, total_cost_usd | MUST | Record test |
| 002 | Per-task telemetry: task_name, model, duration_sec, api_duration_ms, tokens_in, tokens_out, cost_usd, status, confidence | MUST | Task test |
| 003 | Per-model aggregate: average cost, average duration, success rate, total dispatches — over rolling window | MUST | Model test |
| 004 | History queryable: by date range, model, task_name, round_name, status | MUST | Query test |
| 005 | `rondo history` CLI: show recent rounds with cost/duration summary | SHOULD | CLI test |
| 006 | `rondo history --model opus` CLI: show Opus-specific performance over time | SHOULD | Filter test |
| 007 | `rondo history --expensive` CLI: show most expensive rounds (cost optimization targets) | SHOULD | Cost test |
| 008 | `rondo history --json` for machine-readable output | SHOULD | JSON test |
| 009 | Calculated from STD-113 audit trail data — no separate storage needed | MUST | Source test |
| 010 | When OB-connected: dispatch history summary included in OAResult for OB's build intelligence | SHOULD | Integration test |


---

## 4. Architecture / Design

History is a query layer over the STD-113 audit trail, not a separate data store.

```
STD-113 Audit Trail (rondo_audit.jsonl)
    │
    ▼
History Query Engine
    ├── Per-round aggregation
    ├── Per-task detail
    ├── Per-model statistics
    └── Rolling window calculations
    │
    ▼
CLI output / JSON / OAResult metadata
```

The query engine reads JSONL, filters by criteria, and computes aggregates on the fly.
For large audit trails (10K+ entries), an index file may accelerate date-range queries.

---

## 5. Data Model

**Concurrency:** File-level append locking on JSONL spool files (STD-113).

No new tables or files. History views are computed from `rondo_audit.jsonl` (STD-113).

| View | Source Fields | Aggregation |
|------|-------------|-------------|
| Round summary | round_name, duration, tasks, cost | Group by round_name |
| Task detail | task_name, model, status, tokens, cost | No grouping |
| Model stats | model, duration, cost, status | Group by model, rolling window |

---

## 6. Data Boundary

**What this produces:**

| Output | Format | Consumer |
|--------|--------|----------|
| Round history | Terminal table / JSON | Mark (CLI), OB (OAResult) |
| Model statistics | Terminal table / JSON | Mark (CLI), REQ-106 (trends) |
| Expensive rounds list | Terminal table / JSON | Mark (cost optimization) |

**What this consumes:**

| Input | Format | Producer |
|-------|--------|----------|
| Dispatch audit trail | JSONL | STD-113 |

---

## 7. MCP / API Interface

Future: an MCP tool per CORE-STD-021 could expose dispatch history for AI agents to
query. Example: "What was the average cost of overnight runs this week?" The MCP tool
would accept a query (date range, model filter) and return aggregated history JSON.

---

## 8. States & Modes

History query engine is stateless — it reads the audit trail on demand. No persistent
state, no caching between queries (audit trail is append-only, so queries are always fresh).

| Mode | Trigger | Behavior |
|------|---------|----------|
| Interactive | `rondo history` CLI | Read audit, display table |
| JSON | `rondo history --json` | Read audit, output JSON |
| OB-embedded | OB-connected dispatch | Include summary in OAResult |

---

## 9. Configuration

```toml
[history]
default_window_days = 7           # Default rolling window for aggregates
max_results = 50                  # Default limit for CLI output
audit_path = "rondo_audit.jsonl"  # Path to audit trail (relative to config dir)
```

---

## 10. Rules & Constraints

1. **Derived from audit.** STD-113 is the source of truth. History = aggregated views of audit data. Violation ID: `REQ104-FROM-AUDIT`
2. **Per-model, not aggregate.** "Average cost" across all models hides that Opus is 10x Haiku. Per-model analysis required. Violation ID: `REQ104-PER-MODEL`
3. **No separate storage.** History is a view, not a table. Don't duplicate audit data. Violation ID: `REQ104-NO-DUPE`
4. **Immutable audit source.** History never modifies the audit trail. Read-only access. Violation ID: `REQ104-READ-ONLY`

---

## 11. Quality Attributes

| Attribute | Target | Rationale |
|-----------|--------|-----------|
| Query speed | <1s for 7-day window over 10K entries | CLI must feel responsive |
| Accuracy | Exact match to audit trail data | No rounding or sampling errors |
| Freshness | Always current (reads live audit file) | No stale cache |
| Readability | Formatted tables with aligned columns | Mark reads this in terminal |

---

## 12. Shared Patterns

- **Query-over-append-log:** Same pattern as OB's sprint telemetry — read an append-only
  log, compute aggregates on demand. No ETL pipeline needed at Rondo's scale.
- **Rolling window:** 7-day default window smooths noise while catching trends. Same
  window used by REQ-106 (trend alerting) and REQ-107 (flakiness).
- **Per-model breakdown:** Every aggregate includes model dimension. Inherited from
  OB-REQ-115 which tracks per-spec-type build metrics.

---

## 13. Integration Points

| Integration | Spec | Direction | Contract |
|-------------|------|-----------|----------|
| Audit trail | STD-113 | Inbound | JSONL audit records |
| Trend alerting | REQ-106 | Outbound | Per-model aggregates feed trend detection |
| Flakiness | REQ-107 | Outbound | Per-task history feeds flakiness scoring |
| OB integration | IFS-102 | Outbound | History summary in OAResult metadata |
| Morning report | REQ-101 | Outbound | Overnight cost summary |

---

## 14. Standards Applied

| Standard | How Applied |
|----------|-------------|
| CORE-STD-012 (Requirement Readiness) | Each requirement tagged with readiness state |
| CORE-STD-013 (TrackerData) | Audit trail entries follow trackerdata format |
| CORE-STD-021 (MCP Standard) | Future MCP tool for history queries |
| STD-113 (Audit Trail) | Single source of truth for all dispatch data |

---

## 15. Self-Correction

- If per-model cost averages diverge significantly from provider billing, the morning
  report flags "cost tracking may be inaccurate — verify with provider dashboard."
- If the audit trail file grows beyond 100MB, history queries log a performance warning
  and suggest archiving old entries per STD-113's rotation policy.
- Stale or corrupted audit entries (malformed JSON lines) are skipped with a warning
  count shown at the end of query output.

---

## 16. Assumptions

| # | Assumption | If Wrong |
|---|-----------|----------|
| A1 | Audit trail is small enough for on-demand queries (<100MB) | May need index or DB backend |
| A2 | JSONL format is parseable line-by-line | Corrupted lines may break mid-file |
| A3 | 7-day rolling window is sufficient for meaningful trends | May need configurable window |
| A4 | Per-model breakdown is the most useful dimension | May need per-task-type or per-provider views |

---

## 17. Success Criteria

| # | Criterion | How to Verify |
|---|-----------|---------------|
| 1 | `rondo history` shows last 7 days of rounds with cost totals | CLI test |
| 2 | `rondo history --model opus` shows Opus-only metrics | Filter test |
| 3 | `rondo history --expensive` ranks rounds by cost | Sort test |
| 4 | History data matches raw audit trail exactly | Audit comparison test |
| 5 | OB-connected: history summary appears in OAResult | Integration test |

---

## 18. Build Notes / Estimate

| Item | Estimate |
|------|----------|
| JSONL query engine | 1 day — read, parse, filter |
| Aggregation functions (round, task, model) | 1 day |
| CLI commands and formatters | 1 day |
| JSON output mode | 0.5 day |
| OAResult integration | 0.5 day |
| Tests | 1 day |
| Total | ~5 days |

---

## 19. Test Categories

| Category | What | Count (est.) |
|----------|------|-------------|
| Unit | Query functions, aggregation, filtering | 10 |
| CLI | `rondo history` variants with different flags | 6 |
| Integration | History from real audit trail data | 4 |
| Edge case | Empty audit, corrupted lines, large files | 4 |
| Format | JSON output matches expected schema | 2 |

---

## 20. Failure Modes

| Failure | Impact | Mitigation |
|---------|--------|------------|
| Audit trail missing | No history available | Clear error: "No dispatch history — run a task first" |
| Corrupted JSONL line | Inaccurate aggregates | Skip bad lines, report count |
| Very large audit file | Slow queries | Performance warning + archive suggestion |
| Model name changed by provider | Historical model stats split | Alias table in config |

**Emergency Bypass:** BREAK_GLASS override via `break_glass_events` table audit trail (CORE-STD-015). Dispatch history guards (read-only audit enforcement, per-model breakdown requirement) can be suspended under DR mode with human approval.

---

## 21. Dependencies + Used By

| Depends On | Why |
|------------|-----|
| REQ-100 | Core dispatch framework (defines what gets audited) |
| STD-113 | Audit trail (single source of truth) |

| Used By | Why |
|---------|-----|
| REQ-106 | Trend alerting reads history for baseline calculations |
| REQ-107 | Flakiness detection reads per-task history |
| IFS-102 | OB integration includes history summary |
| REQ-101 | Morning report includes overnight cost summary |

---

## 22. Decisions

| # | Decision | Date | Why |
|---|----------|------|-----|
| D1 | Query over audit, not separate store | 2026-03-20 | One source of truth, no sync issues |
| D2 | Per-model breakdown mandatory | 2026-03-20 | Aggregate hides model-specific problems |
| D3 | 7-day rolling window default | 2026-03-20 | Balances noise reduction with recency |
| D4 | CLI with --json for machine use | 2026-03-20 | Supports scripting and OB consumption |

---

## 23. Open Questions

| # | Question | Impact | Status |
|---|----------|--------|--------|
| Q1 | Should history support export to CSV for external analysis? | Nice-to-have for spreadsheet users | OPEN |
| Q2 | At what audit trail size should we switch to an indexed backend? | Performance scaling decision | OPEN |
| Q3 | Should per-provider history be separate from per-model history? | Same provider, different models vs different providers | OPEN |

---

## 24. Glossary

| Term | Definition |
|------|-----------|
| **Dispatch history** | Aggregated view of past AI dispatches from the audit trail |
| **Rolling window** | Sliding time window (default 7 days) for computing averages and trends |
| **Per-model aggregate** | Statistics (cost, duration, success rate) grouped by AI model |
| **Audit trail** | Append-only JSONL log of every dispatch event (STD-113) |

---

## 25. Risk / Criticality

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Audit trail grows unbounded | Medium | Slow queries | STD-113 rotation policy + archive |
| Inaccurate cost data from provider | Low | Misleading history | Cross-check with provider dashboard |
| Model name changes break historical continuity | Low | Split statistics | Config-based model aliases |

---

## 26. External Scan

Cross-pollinated from OB-REQ-115 (Test Build History). Similar patterns in industry:
Datadog APM (per-service latency/cost tracking), GitHub Actions usage reports (per-workflow
cost), AWS Cost Explorer (per-service cost breakdown). All use rolling-window aggregation
over append-only event logs.

---

## 27. Security Considerations

- History queries expose cost data — not sensitive but useful for competitive intelligence.
  Local-only access (CLI, no network exposure) mitigates this.
- Audit trail may contain task names that hint at project content. Keep audit files
  permission-restricted (0600).
- JSON output mode should not include raw prompts or API keys — only metadata.

---

## 28. Performance / Resource

| Metric | Target | Notes |
|--------|--------|-------|
| Query time (7-day, <10K entries) | <500ms | JSONL sequential scan |
| Query time (30-day, <50K entries) | <2s | May need date-range index |
| Memory | <50MB during query | Stream JSONL, don't load all at once |
| Disk | Zero additional (reads audit trail) | No separate storage |

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

Not yet populated. Will be filled during first build sprint implementing dispatch history.

---

## 32. AI Assumptions

Not yet populated. Will capture model assumptions made during build.

---

## 33. AI Cost

Not yet populated. Will track token/cost data from build sprints referencing this spec.

---

## 34. Notes

- This spec is intentionally lightweight — it's a query layer, not a data store. The
  complexity lives in STD-113 (audit trail) and REQ-106 (trend alerting). History is
  the bridge between raw audit data and actionable insights.
- The `--expensive` flag was inspired by Mark's question: "Which overnight round cost
  the most?" That's a cost optimization trigger.

---

### Feature Maturity

| Feature | Maturity | Evidence | Retest |
|---------|----------|----------|--------|
| Dispatch history storage | THEORY | Specced for recording every task dispatch | Phase 1 build |
| Cost tracking per dispatch | THEORY | Specced for token/dollar cost recording | Phase 1 build |
| Historical queries | THEORY | Specced for finding past dispatches | Phase 2 build |


## 35. Change History

| Version | Date | What Changed |
|---------|------|-------------|
| 1.0 | 2026-03-20 | Initial. Cross-pollinated from OB-REQ-115. 10 requirements. |
| 1.1 | 2026-03-22 | Filled to 35 sections. Added CORE-STD-012, CORE-STD-013, CORE-IFS-005 refs. Approval (Mark, Session 84). |
