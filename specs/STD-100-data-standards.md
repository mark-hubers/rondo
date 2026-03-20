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
**Matches:** CORE-STD-001, Caliber-STD-100

---

## 1. Purpose & Scope

Defines the data conventions that every Rondo dataclass, JSON result file, CLI output, and integration boundary must follow. Five domains in one spec: time handling, identifiers, null/empty semantics, naming conventions, and status vocabularies.

Rondo is stateless (no database). These rules apply to Python dataclasses, JSON spool files, and the RoundResult/TaskResult/DispatchUsage objects returned to consumers.

---

## 3. Requirements

### Time

1. All timestamps MUST be ISO 8601 UTC with timezone: `2026-03-18T12:00:00+00:00`. No bare datetimes without timezone.
2. Timestamps in dataclasses use `str` type (ISO 8601). Timestamps in JSON result files use the same format.
3. Every result object MUST include `started_at` and `completed_at` fields. RoundResult, TaskResult, and spool files all carry both.
4. Round-level duration uses `duration_sec: float` (seconds with decimal precision). Task-level duration uses `duration_sec: float` for wall-clock. DispatchUsage uses `duration_ms: int` and `duration_api_ms: int` for stream-json precision.
5. Never store or display local time in result objects. All times are UTC. Convert to local time only at display in consumer code.

### Identifiers

6. Round names are kebab-case strings: `health-check`, `spec-review`, `overnight-batch`. No spaces, no underscores, no camelCase.
7. Task names are human-readable strings, unique within their round. Used as the primary identifier in result files and logs.
8. Result file naming uses the round timestamp as the directory and task sequence as the prefix: `2026-03-14T03-00-00Z/task-01-spec-health.json`.
9. Spool file naming follows the pattern: `{round_name}_{ISO-timestamp}_{task-seq}.json`. Timestamps in filenames use hyphens instead of colons for filesystem safety.
10. Identifiers are never reused. Each round execution gets a unique timestamp directory. Each task result file is distinct.

### Null Handling

11. NULL (Python `None`) means "not yet known." Empty string (`""`) means "explicitly empty." These are different and must not be confused.
12. Boolean fields use Python `bool` (`True`/`False`), never `None`. Default to `False`. No three-valued logic.
13. Optional fields default to `""` (empty string) for text, `0` for integers, `0.0` for floats, `[]` for lists — unless "not yet known" is genuinely different from "empty."
14. `parsed_result` in TaskResult: `None` means "Claude returned non-JSON output" (valid state, not an error). This is one of the few valid uses of None.
15. JSON output files use `null` for Python `None`. Consumers can distinguish "not parsed" from "empty result."

### Naming

16. Python dataclass names: `PascalCase`. Examples: `RoundResult`, `TaskResult`, `DispatchUsage`, `GateResult`.
17. Python field names: `snake_case`. Examples: `started_at`, `task_name`, `cost_usd`, `duration_ms`. Match NAMING-MAP.md field conventions exactly.
18. Python functions: `snake_case`. Examples: `run_round`, `dispatch_task`, `load_config`.
19. CLI commands: `kebab-case`. Examples: `rondo run`, `rondo overnight`, `rondo report`.
20. JSON keys: `snake_case`, matching the Python field names exactly. No camelCase, no abbreviations. `TaskResult.duration_sec` serializes to `"duration_sec"`.

### Status Values

21. RoundResult.status uses exactly 4 values: `done`, `partial`, `error`, `skipped`. No `blocked` at round level (blocked tasks contribute to `partial` or `error`). No `pending` or `in_progress` in results — those are transient engine states.
22. TaskResult.status uses exactly 5 values: `done`, `blocked`, `partial`, `error`, `skipped`. These match the task state machine terminal states.
23. Status values are always lowercase strings. Never `DONE`, `Done`, or `IN_PROGRESS`.
24. The shared status vocabulary (per NAMING-MAP.md) is: `done`, `partial`, `error`, `skipped`, `blocked`. Rondo uses a subset — it does not use `pending`, `in_progress`, or `blocked` in output (those are internal engine states only).
25. Every status in a result object MUST have a corresponding `detail` or `summary` field explaining why that status was assigned.

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

## 35. Change History

| Version | Date | What Changed |
|---------|------|-------------|
| 0.1 | 2026-03-18 | Initial draft. Matches CORE-STD-001 topics (time, IDs, nulls, naming, status) adapted for Rondo's stateless context. 25 requirements. Duration split: sec for wall-clock, ms for stream-json. NAMING-MAP.md cross-reference table. |
