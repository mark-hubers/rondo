# STD-100: Data Standards

*How Rondo handles time, identifiers, status values, naming, and null semantics. The foundation every dataclass and result file follows.*

**Created:** 2026-03-18 | **Status:** DESIGNED
**Classification:** open
**Version:** 0.1
**Owner:** Mark G. Hubers
**Reviewed:** not-yet
**Supersedes:** none
**Universal standard** — same topic number across all products (DEC-017)
**Product:** Rondo
**Matches:** CORE-STD-001, STD-100 (Caliber)
**Depends on:** CORE-STD-012, CORE-STD-021, STD-102

---

## 1. Purpose & Scope

Defines the data conventions that every Rondo dataclass, JSON result file, CLI output, and integration boundary must follow. Five domains in one spec: time handling, identifiers, null/empty semantics, naming conventions, and status vocabularies.

Rondo is stateless (no database). These rules apply to Python dataclasses, JSON spool files, and the RoundResult/TaskResult/DispatchUsage objects returned to consumers.

**Users:** Mark (primary). Claude AI agents dispatching to other models. Future: teams needing multi-model AI orchestration, batch processing, cost optimization across AI providers.

---

## 2. The Problem

Without consistent data conventions, every integration boundary becomes a translation layer. Field names drift (`cost` vs `cost_usd`), timestamp formats diverge (epoch vs ISO), and null semantics become ambiguous. Rondo's stateless design means every consumer (OB, Caliber, ACE) parses Rondo output independently — inconsistency here multiplies across the ecosystem.

---

## 3. Requirements

*All requirements use MUST/SHOULD priority per CORE-STD-012.*

### Time
| ID | Requirement | Priority |
|----|-------------|----------|
| 001 | All timestamps MUST be ISO 8601 UTC with timezone: `2026-03-18T12:00:00+00:00`. No bare datetimes without timezone | MUST |
| 002 | System SHALL timestamps in dataclasses use `str` type (ISO 8601). Timestamps in JSON result files use the same format | MUST |
| 003 | Every result object MUST include `started_at` and `completed_at` fields. RoundResult, TaskResult, and spool files all carry both | MUST |
| 004 | System SHALL round-level duration uses `duration_sec: float` (seconds with decimal precision). Task-level duration uses `duration_sec: float` for wall-clock. DispatchUsage uses `duration_ms: int` and `duration_api_ms: int` for stream-json precision | MUST |
| 005 | System SHALL never store or display local time in result objects. All times are UTC. Convert to local time only at display in consumer code | MUST |

### Identifiers
| ID | Requirement | Priority |
|----|-------------|----------|
| 006 | System SHALL round names are kebab-case strings: `health-check`, `spec-review`, `overnight-batch`. No spaces, no underscores, no camelCase | MUST |
| 007 | System SHALL task names are human-readable strings, unique within their round. Used as the primary identifier in result files and logs | MUST |
| 008 | System SHALL result file naming uses the round timestamp as the directory and task sequence as the prefix: `2026-03-14T03-00-00Z/task-01-spec-health.json` | MUST |
| 009 | System SHALL spool file naming follows the pattern: `{round_name}_{ISO-timestamp}_{task-seq}.json`. Timestamps in filenames use hyphens instead of colons for filesystem safety | MUST |
| 010 | System SHALL identifiers are never reused. Each round execution gets a unique timestamp directory. Each task result file is distinct | MUST |

### Null Handling
| ID | Requirement | Priority |
|----|-------------|----------|
| 011 | System SHALL nULL (Python `None`) means "not yet known." Empty string (`""`) means "explicitly empty." These are different and must not be confused | MUST |
| 012 | System SHALL boolean fields use Python `bool` (`True`/`False`), never `None`. Default to `False`. No three-valued logic | MUST |
| 013 | System SHALL optional fields default to `""` (empty string) for text, `0` for integers, `0.0` for floats, `[]` for lists — unless "not yet known" is genuinely different from "empty." | MUST |
| 014 | System SHALL `parsed_result` in TaskResult: `None` means "Claude returned non-JSON output" (valid state, not an error). This is one of the few valid uses of None | MUST |
| 015 | System SHALL jSON output files use `null` for Python `None`. Consumers can distinguish "not parsed" from "empty result." | MUST |

### Naming
| ID | Requirement | Priority |
|----|-------------|----------|
| 016 | System SHALL python dataclass names: `PascalCase`. Examples: `RoundResult`, `TaskResult`, `DispatchUsage`, `GateResult` | MUST |
| 017 | System SHALL python field names: `snake_case`. Examples: `started_at`, `task_name`, `cost_usd`, `duration_ms`. Match NAMING-MAP.md field conventions exactly | MUST |
| 018 | System SHALL python functions: `snake_case`. Examples: `run_round`, `dispatch_task`, `load_config` | MUST |
| 019 | System SHALL cLI commands: `kebab-case`. Examples: `rondo run`, `rondo overnight`, `rondo report` | MUST |
| 020 | System SHALL jSON keys: `snake_case`, matching the Python field names exactly. No camelCase, no abbreviations. `TaskResult.duration_sec` serializes to `"duration_sec"` | MUST |

### Status Values
| ID | Requirement | Priority |
|----|-------------|----------|
| 021 | System SHALL roundResult.status uses exactly 4 values: `done`, `partial`, `error`, `skipped`. No `blocked` at round level (blocked tasks contribute to `partial` or `error`). No `pending` or `in_progress` in results — those are transient engine states | MUST |
| 022 | System SHALL taskResult.status uses exactly 5 values: `done`, `blocked`, `partial`, `error`, `skipped`. These match the task state machine terminal states | MUST |
| 023 | System SHALL status values are always lowercase strings. Never `DONE`, `Done`, or `IN_PROGRESS` | MUST |
| 024 | System SHALL the shared status vocabulary (per NAMING-MAP.md) is: `done`, `partial`, `error`, `skipped`, `blocked`. Rondo uses a subset — it does not use `pending`, `in_progress`, or `blocked` in output (those are internal engine states only) | MUST |
| 025 | Every status in a result object MUST have a corresponding `detail` or `summary` field explaining why that status was assigned | MUST |

---
## 4. Architecture / Design

Rondo data standards are enforced at two layers: Python dataclass definitions (compile-time shape) and JSON serialization (runtime output). Dataclasses define field names, types, and defaults. The `to_json()` method on each dataclass enforces naming and null conventions at the serialization boundary.

---

## 5. Data Model

Rondo has no database. The data model is defined by Python dataclasses: `RoundResult`, `TaskResult`, `DispatchUsage`, `GateResult`. These are the canonical shapes. JSON spool files are serialized copies of these dataclasses, not a separate schema.

---

## 6. Data Boundary

Rondo produces data (spool files, RoundResult objects). Consumers (OB, Caliber, ACE) ingest it. The boundary is the spool directory and the returned Python objects. Field names in NAMING-MAP.md define the contract — Rondo owns the producer side, consumers own the ingestion side.

---

## 7. MCP / API Interface

Rondo does not expose data standards via MCP. Data conventions are enforced in code (dataclass definitions) and verified by convention tests. MCP tools (CORE-STD-021) that query Rondo results rely on these conventions being stable.

---

## 8. States & Modes

Not applicable. Data standards are static conventions, not stateful. Status values (`done`, `partial`, `error`, `skipped`, `blocked`) are defined in section 3 and do not change based on mode or configuration.

---

## 9. Configuration

Data standards are not configurable. Timestamp format, naming conventions, status vocabularies, and null semantics are fixed. This is intentional — configurability in data formats creates integration fragility. The only configurable aspect is `results_dir` path (STD-102).

---

## 10. Rules & Constraints

### Status Vocabulary (Rondo Output)

| Value | RoundResult | TaskResult | Meaning |
|-------|:-----------:|:----------:|---------|
| `done` | Yes | Yes | All tasks/this task completed successfully |
| `partial` | Yes | Yes | Some succeeded, some failed / got output but unparseable JSON |
| `error` | Yes | Yes | All failed / dispatch-level failure |
| `skipped` | Yes | Yes | Pre-gate blocked round / precondition not met |
| `blocked` | No | Yes | Claude reported it cannot proceed (task-level only) |

### Duration Field Reference

| Field | Type | Unit | Used In | Source |
|-------|------|------|---------|--------|
| `duration_sec` | float | seconds | RoundResult, TaskResult | `time.perf_counter()` wall-clock |
| `duration_ms` | int | milliseconds | DispatchUsage | stream-json `result` event |
| `duration_api_ms` | int | milliseconds | DispatchUsage | stream-json API timing |

### Naming Convention Reference

| Context | Convention | Example | Anti-Pattern |
|---------|------------|---------|-------------|
| Dataclass | PascalCase | `RoundResult` | `round_result`, `roundResult` |
| Field name | snake_case | `cost_usd` | `costUsd`, `cost_USD` |
| Function | snake_case | `run_round` | `runRound`, `RunRound` |
| Constant | UPPER_SNAKE | `MAX_RETRIES` | `maxRetries`, `max_retries` |
| CLI command | kebab-case | `rondo run` | `rondo_run`, `rondoRun` |
| Round name | kebab-case | `health-check` | `health_check`, `HealthCheck` |
| Status value | lowercase | `done` | `DONE`, `Done` |
| JSON key | snake_case | `"input_tokens"` | `"inputTokens"` |

### NAMING-MAP.md Cross-Reference

These Rondo fields MUST match NAMING-MAP.md exactly for cross-product compatibility:

| Rondo Field | OB Table.Column | Why |
|------------|----------------|-----|
| `RoundResult.status` | `round_states.status` | Same vocabulary |
| `RoundResult.duration_sec` | `round_states.duration_sec` | Same unit, same name |
| `TaskResult.status` | `sprint_results.status` | Same vocabulary |
| `DispatchUsage.cost_usd` | `sprint_intelligence.cost_usd` | Same precision, same name |
| `DispatchUsage.input_tokens` | `sprint_intelligence.input_tokens` | Same name |
| `DispatchUsage.model` | `sprint_intelligence.model` | Same name |
| `GateResult.passed` | `gate_checks.passed` | Same boolean semantics |

---

## 11. Quality Attributes

- **Consistency:** Same field name means the same thing in every Rondo output and every consumer.
- **Predictability:** Consumers can parse Rondo output without checking which version produced it.
- **Debuggability:** JSON files use `indent=2` and human-readable timestamps for manual inspection.

---

## 12. Shared Patterns

- **COALESCE null handling:** `COALESCE(override, learned, default)` — same idiom used in STD-102 config resolution.
- **Snake_case everywhere:** Python fields, JSON keys, CLI output. One convention, zero translation.
- **Duration split:** `duration_sec` for wall-clock summaries, `duration_ms` for API-level precision. Shared with STD-101, STD-105.

---

## 13. Integration Points

| Integration | What Crosses | Standard Enforced |
|-------------|-------------|-------------------|
| Rondo → OB | DispatchUsage fields | NAMING-MAP.md field names |
| Rondo → Caliber | TaskResult status values | Status vocabulary (section 3) |
| Rondo → Spool | JSON serialization | Timestamp, naming, null rules |
| Rondo → CORE-STD-012 | Requirement readiness states | Status vocabulary alignment |

---

## 14. Standards Applied

| Standard | How It Applies |
|----------|---------------|
| CORE-STD-001 | Parent standard — Rondo adapts time, IDs, nulls, naming, status for stateless context |
| CORE-STD-012 | Requirement readiness tracking — status values align with Rondo's vocabulary |
| CORE-STD-013 | TrackerData — field naming conventions shared for cross-product data exchange |
| CORE-STD-021 | MCP standard — query results from MCP tools follow these data conventions |

---

## 15. Self-Correction

Not directly applicable. Data standards are fixed conventions, not learned behaviors. However, NAMING-MAP.md drift detection (STD-106 check 11) catches cases where Rondo output drifts from the agreed field names. Convention lock tests prevent regression.

---

## 16. Assumptions

1. NAMING-MAP.md is the single source of truth for cross-product field names.
2. All consumers parse JSON with a schema-aware parser, not ad-hoc string matching.
3. Stream-json output format from Claude CLI remains stable across Claude Code versions.
4. UTC is sufficient — no consumer needs Rondo to produce local time.

---

## 17. Success Criteria

| # | Criterion | How to Verify |
|---|-----------|---------------|
| 1 | Every Rondo JSON output parses without field-name translation in OB | Integration test |
| 2 | Convention tests catch any new field that violates snake_case | AST test |
| 3 | NAMING-MAP.md cross-reference table has zero DRIFT entries | Golden number check |

---

## 18. Build Notes / Estimate

Data standards are enforced via dataclass definitions and convention tests. No separate "build" — the conventions are embedded in the codebase from day one. Estimated effort: convention tests (2 hours), NAMING-MAP.md cross-reference validation (1 hour).

---

## 19. Test Categories

| Category | What It Tests |
|----------|--------------|
| Convention tests | snake_case fields, PascalCase classes, no camelCase in JSON |
| Serialization tests | `to_json()` output matches expected field names and types |
| Cross-reference tests | NAMING-MAP.md fields match actual dataclass field names |

---

## 20. Failure Modes

| Failure | Impact | Mitigation |
|---------|--------|------------|
| Field name drift | OB ingestion breaks silently | Convention lock tests + NAMING-MAP.md check |
| Timestamp without timezone | Ambiguous times across machines | Dataclass default includes `+00:00` |
| Status value typo | Consumer switch/case misses a branch | Enum-like constants, not raw strings |

---

## 21. Dependencies + Used By

| Direction | Spec | Relationship |
|-----------|------|-------------|
| Depends on | CORE-STD-001 | Parent data standard |
| Depends on | CORE-STD-012 | Status vocabulary alignment |
| Used by | STD-101 | Logging field names follow these conventions |
| Used by | STD-105 | DispatchUsage fields defined here |
| Used by | Rondo-IFS-102 | OB integration uses these field names |

---

## 22. Decisions

| Decision | Rationale | Date |
|----------|-----------|------|
| D1: sec/ms duration split | Wall-clock (sec) vs API precision (ms) — different consumers need different granularity | 2026-03-18 |
| D2: snake_case for JSON keys | Matches Python field names — zero translation at serialization boundary | 2026-03-18 |
| D3: No None for booleans | Three-valued logic causes downstream bugs. Default False, never None. | 2026-03-18 |

---

## 23. Open Questions

None currently. Data conventions are stable after cross-spec review (Session 75).

---

## 24. Glossary

| Term | Definition |
|------|-----------|
| **NAMING-MAP.md** | Cross-product field name registry — single source of truth |
| **COALESCE** | First non-null value wins — ACE2 core idiom for defaults |
| **Spool file** | JSON result file written to disk by Rondo after each dispatch |

---

## 25. Risk / Criticality

**HIGH.** Data standards are the foundation. A naming inconsistency here propagates to every consumer. Convention lock tests are the primary mitigation — they make drift impossible without a deliberate code change.

---

## 26. External Scan

No external standards referenced beyond ISO 8601 for timestamps. JSON naming follows Python community convention (snake_case). No industry-specific data format requirements apply.

---

## 27. Security Considerations

Data standards do not directly handle secrets. However, the `prompt_sent` field in TaskResult must be scrubbed before spool writes (STD-114). Field naming conventions ensure no field is ambiguously named in a way that hides sensitive content.

---

## 28. Performance / Resource

No performance impact. Data conventions are enforced at definition time (dataclass fields) and verified at test time (convention tests). Runtime serialization adds negligible overhead — `json.dumps()` with `indent=2`.

---

## 29. Approval Record

| Reviewer | Role | Date | Verdict |
|----------|------|------|---------|
| Mark Hubers | Owner | 2026-03-22 | Approved (Session 84) |

---

## 30. AI Review

— filled after build.

---

## 31. AI Went Wrong

— filled during build.

---

## 32. AI Assumptions

— filled during build.

---

## 33. AI Cost

— filled during build.

---

## 34. Notes

CORE-STD-012 (Requirement Readiness) and CORE-STD-013 (TrackerData) both consume Rondo's data conventions for cross-product compatibility. CORE-STD-021 MCP tools that return Rondo data must follow these same conventions.

---

### Feature Maturity

| Feature | Maturity | Evidence | Retest |
|---------|----------|----------|--------|
| Timestamp standards (ISO 8601) | WORKING | Enforced via CORE-STD-001 | After schema changes |
| Naming conventions (snake_case) | WORKING | Convention tests enforce naming | Every build |
| Status vocabularies | WORKING | Defined and CHECK-constrained | After status additions |


## 35. Change History

| Version | Date | What Changed |
|---------|------|-------------|
| 0.1 | 2026-03-18 | Initial draft. Matches CORE-STD-001 topics (time, IDs, nulls, naming, status) adapted for Rondo's stateless context. 25 requirements. Duration split: sec for wall-clock, ms for stream-json. NAMING-MAP.md cross-reference table. |
| 0.2 | 2026-03-22 | Filled to 35 sections. Added CORE-STD-012, CORE-STD-013, CORE-STD-021 refs. Approval record (Mark, Session 84). |
