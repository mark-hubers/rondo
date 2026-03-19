# STD-002: Observability

*How Rondo logs, handles errors, and tracks performance. Every dispatch leaves a trace.*

**Created:** 2026-03-18 | **Status:** DESIGNED
**Classification:** open
**Version:** 0.2
**Owner:** Mark G. Hubers
**Reviewed:** not-yet
**Supersedes:** none
**Universal standard** — same topic number across all products (DEC-017)
**Product:** Rondo
**Matches:** OB-STD-002, Caliber-STD-002

---

## 1. Purpose & Scope

Defines how every Rondo component logs its activity, handles errors, and tracks performance. Three pillars: structured logging with subprocess capture, error handling for dispatch failures, and per-task timing and cost instrumentation via stream-json.

**IN scope:**
- Structured log format and CLI output conventions
- Subprocess stdout/stderr capture per dispatch
- Error structure and retry policy
- Per-task timing and token tracking (stream-json)
- Spool file naming and structure

**OUT of scope:**
- Data format conventions (STD-001: Data Standards)
- Configuration loading (STD-003: Configuration)
- Consumer-side storage of results (OB's concern, not Rondo's)

---

## 3. Requirements

### Logging

1. Every log entry MUST include four fields: `timestamp` (ISO 8601 UTC per STD-001 rule 1), `level`, `source` (module name: `dispatch`, `runner`, `config`, etc.), and `message`.
2. Log levels use standard Python logging: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`. No custom levels.
3. CLI output uses status prefixes for machine-parseable results: `-PASS-`, `-FAIL-`, `-ERROR-`, `-WARNING-`. These prefixes appear at the start of the line.
4. Log to stderr, not stdout. Stdout is reserved for structured output (JSON result objects, round summaries). This separation allows piping Rondo output.
5. Every dispatch MUST be logged with: task name, model, auth mode, and duration. On completion, add status and token counts.
6. Dry-run mode MUST log the prompt that would be sent without invoking Claude, prefixed with `-DRYRUN-`.

### Subprocess Capture

7. Dispatch MUST capture stdout and stderr from each `claude -p` subprocess as separate streams. Both are preserved in the TaskResult.
8. Dispatch MUST use `--output-format stream-json` to capture real token counts, cost, cache stats, and API timing. Text mode does not provide these (F20 lesson).
9. From stream-json events, dispatch extracts: `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_create_tokens`, `cost_usd`, `duration_ms`, `duration_api_ms`, `num_turns`, `context_window`. These populate DispatchUsage.
10. Raw stdout (full stream-json output) MUST be preserved in the TaskResult for debugging. The parsed fields are convenience — the raw data is the source of truth.
11. If stream-json parsing fails, fall back to raw text capture. Log at WARNING. Set status to `partial`. Never discard output because parsing failed.

### Error Handling

12. No bare `except` clauses. Catch specific exceptions. `except Exception` only at system boundaries (CLI entry point, runner top-level).
13. Every error MUST carry: an `error_code` (uppercase with prefix, e.g., `DISPATCH_TIMEOUT`, `PARSE_MALFORMED`), a human-readable `message`, and `context` describing what task was being dispatched.
14. Subprocess failures (non-zero exit code) MUST record: exit code, stderr content, task name, model, duration. Status becomes `error`.
15. Malformed JSON from Claude (stdout is not valid JSON matching the result contract) MUST record: raw output preserved, status becomes `partial`, log at WARNING.
16. Empty stdout from subprocess MUST be treated as `error`, not silently ignored. Log at ERROR with stderr content.

### Retry Policy

17. Rondo does NOT retry dispatches by default. A failed task stays failed for this round. Retries are the consumer's responsibility (run the round again).
18. Rate limit detection: if stream-json includes a `rate_limit_event` indicating blocked status, log at WARNING with `rate_limit_resets_at`. Do not retry — record the rate limit in DispatchUsage and let the consumer decide.
19. Subprocess timeout: configurable via `task_timeout_sec` in config. Default: 300 seconds. On timeout, kill the process, record status `error` with error_code `DISPATCH_TIMEOUT`.

### Performance

20. Every task dispatch MUST track wall-clock `duration_sec` using `time.perf_counter()` (start to finish including subprocess overhead).
21. Stream-json provides `duration_ms` (API wall-clock) and per-turn timing. These go into DispatchUsage, separate from the Python-measured wall-clock.
22. Per-dispatch cost tracking MUST capture: `input_tokens`, `output_tokens`, `cost_usd`, `cache_read_tokens`, `cache_create_tokens`. Source: stream-json `result` event.
23. Round-level summary MUST aggregate: total `duration_sec`, total `cost_usd`, total tasks, pass/fail counts. This is the `RoundResult.summary` field.
24. All performance data MUST be available in the returned RoundResult object AND in spool files. Consumers should not need to parse logs for metrics.

### Spool Files

25. Every task result MUST be written to a JSON file in the results directory immediately after dispatch completes. Files persist across crashes.
26. Spool directory structure: `{results_dir}/{round-name}_{ISO-timestamp}/task-{NN}-{task-name}.json`. One directory per round execution.
27. Round summary MUST be written as `round-summary.json` in the same directory after all tasks complete.
28. Spool files have a configurable TTL (default: 30 days). Cleanup is the consumer's responsibility — Rondo writes, consumers prune.

### Metrics: Store Everything, Prune Later

**GOLDEN RULE: Don't decide what's noise at capture time. Decide at query time.**

29. Default is KEEP ALL. Every measurement stored in spool files. What looks like noise today is the pattern ACE discovers tomorrow.
30. Spool-based metrics: each TaskResult includes a `metrics` dict with `metric_name`, `metric_value`, `metric_unit`, `context`, `captured_at`. Consumers (OB, ACE) ingest into their DBs.
31. Store per-dispatch: task name, model, auth_mode, pass/fail, duration_ms, output_length, prompt_length.
32. Store per-API-call (from stream-json): endpoint, tokens_in, tokens_out, cost_usd, response_time_ms, model, cache_read_tokens, cache_create_tokens.
33. Store per-file (when dispatching file-scoped tasks): line_count, function_count, complexity score, findings count.
34. Store per-round (via DispatchUsage fields): duration, working_time, findings, files_changed, total_cost_usd, total_tokens.
35. Cost: ~200 bytes per metric entry in spool JSON. Store everything for years.
36. Monthly prune job: flag metrics with zero variance or zero queries. Mark approves deletion. NEVER auto-delete. Rondo spool TTL (28 days default) is separate — metrics survive in consumer DBs.
37. Cross-project mining via ACE: noise in one project = pattern across five.

---

## 10. Rules & Constraints

### CLI Status Prefix Reference

| Prefix | Meaning | Exit Code |
|--------|---------|-----------|
| `-PASS-` | Task/gate completed successfully | 0 |
| `-FAIL-` | Task/gate failed | 1 |
| `-ERROR-` | System error (dispatch failure, timeout) | 2 |
| `-WARNING-` | Completed with advisory notes | 0 |
| `-DRYRUN-` | Dry-run mode, no dispatch | 0 |

Example output:
```
-PASS-  task "spec-health" (sonnet, 23.4s, $0.0031)
-FAIL-  task "convention-check" (opus, 45.1s, $0.0089)
-ERROR- task "digest-refresh" — DISPATCH_TIMEOUT after 300s
-WARNING-  rate limit: resets at 2026-03-18T04:00:00Z
```

### Error Code Categories

| Prefix | Category | Examples |
|--------|----------|---------|
| `DISPATCH_` | Subprocess dispatch | `DISPATCH_TIMEOUT`, `DISPATCH_EXIT_NONZERO`, `DISPATCH_EMPTY` |
| `PARSE_` | Result parsing | `PARSE_MALFORMED`, `PARSE_STREAM_JSON_FAIL` |
| `CONFIG_` | Configuration | `CONFIG_MISSING_KEY`, `CONFIG_INVALID_VALUE` |
| `IO_` | File system | `IO_SPOOL_WRITE_FAIL`, `IO_ROUND_FILE_MISSING` |
| `AUTH_` | Authentication | `AUTH_KEY_MISSING`, `AUTH_MODE_INVALID` |
| `RATE_` | Rate limiting | `RATE_BLOCKED`, `RATE_OVERAGE` |

### Performance Data Flow

```
claude -p --output-format stream-json
         │
         ▼
    stream-json events
         │
    ┌────┴─────────────────────────────┐
    │ Parse: input_tokens,             │
    │   output_tokens, cost_usd,       │
    │   cache_read, cache_create,      │
    │   duration_ms, num_turns,        │
    │   context_window, rate_limit     │
    └────┬─────────────────────────────┘
         │
         ▼
    DispatchUsage (per task)
         │
    ┌────┴───────────┐
    │                │
    ▼                ▼
RoundResult      spool file
(returned)       (persisted)
```

---

## 35. Change History

| Version | Date | What Changed |
|---------|------|-------------|
| 0.2 | 2026-03-19 | Added "Metrics: Store Everything, Prune Later" section (reqs 29-37). Spool-based metrics with consumer ingestion, per-dispatch/per-API/per-file/per-round storage, monthly prune with approval, cross-project ACE mining. Total: 37 requirements. |
| 0.1 | 2026-03-18 | Initial draft. Matches OB-STD-002 topics (logging, errors, performance) adapted for Rondo's dispatch context. 28 requirements. Stream-json capture, spool file naming, no-retry policy, rate limit detection. |
