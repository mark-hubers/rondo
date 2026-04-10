# Rondo-STD-101: Observability

*How Rondo logs, handles errors, and tracks performance. Every dispatch leaves a trace.*

**Created:** 2026-03-18 | **Status:** DESIGNED
**Classification:** open
**Version:** 0.2
**Owner:** Mark G. Hubers
**Reviewed:** not-yet
**Supersedes:** none
**Universal standard** — same topic number across all products (DEC-017)
**Product:** Rondo
**Matches:** CORE-STD-002, Rondo-STD-101 (Caliber)
**Depends on:** Rondo-STD-104, Rondo-STD-100, Rondo-STD-102, CORE-STD-012, ACE-STD-020, CORE-STD-021, CORE-STD-013

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
- Data format conventions (Rondo-STD-100: Data Standards)
- Configuration loading (Rondo-STD-102: Configuration)
- Consumer-side storage of results (OB's concern, not Rondo's)

**Users:** Mark (primary). Claude AI agents dispatching to other models. Future: teams needing multi-model AI orchestration, batch processing, cost optimization across AI providers.

---

## 2. The Problem

Without structured observability, overnight failures are black boxes. A task fails at 3 AM — what was the prompt? What did Claude return? How long did it take? Without per-dispatch capture, debugging requires re-running the task and hoping the failure reproduces. Rondo's subprocess model means standard application logging misses the critical data: it lives inside the child process.

---

## 3. Requirements

*All requirements use MUST/SHOULD priority per CORE-STD-012.*

### Logging
| ID | Requirement | Priority |
|----|-------------|----------|
| 001 | Every log entry MUST include four fields: `timestamp` (ISO 8601 UTC per Rondo-STD-100 rule 1), `level`, `source` (module name: `dispatch`, `runner`, `config`, etc.), and `message` | MUST |
| 002 | System SHALL log levels use standard Python logging: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`. No custom levels | MUST |
| 003 | System SHALL cLI output uses status prefixes for machine-parseable results: `-PASS-`, `-FAIL-`, `-ERROR-`, `-WARNING-`. These prefixes appear at the start of the line | MUST |
| 004 | System SHALL log to stderr, not stdout. Stdout is reserved for structured output (JSON result objects, round summaries). This separation allows piping Rondo output | MUST |
| 005 | Every dispatch MUST be logged with: task name, model, auth mode, and duration. On completion, add status and token counts | MUST |
| 006 | Dry-run mode MUST log the prompt that would be sent without invoking Claude, prefixed with `-DRYRUN-` | MUST |

### Subprocess Capture
| ID | Requirement | Priority |
|----|-------------|----------|
| 007 | Dispatch MUST capture stdout and stderr from each `claude -p` subprocess as separate streams. Both are preserved in the TaskResult | MUST |
| 008 | Dispatch MUST use `--output-format stream-json` to capture real token counts, cost, cache stats, and API timing. Text mode does not provide these (ACE-STD-020 lesson) | MUST |
| 009 | System SHALL from stream-json events, dispatch extracts: `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_create_tokens`, `cost_usd`, `duration_ms`, `duration_api_ms`, `num_turns`, `context_window`. These populate DispatchUsage | MUST |
| 010 | Raw stdout (full stream-json output) MUST be preserved in the TaskResult for debugging. The parsed fields are convenience — the raw data is the source of truth | MUST |
| 011 | System SHALL if stream-json parsing fails, fall back to raw text capture. Log at WARNING. Set status to `partial`. Never discard output because parsing failed | MUST |

### Error Handling
| ID | Requirement | Priority |
|----|-------------|----------|
| 012 | System SHALL no bare `except` clauses. Catch specific exceptions. `except Exception` only at system boundaries (CLI entry point, runner top-level) | MUST |
| 013 | Every error MUST carry: an `error_code` (uppercase with prefix, e.g., `DISPATCH_TIMEOUT`, `PARSE_MALFORMED`), a human-readable `message`, and `context` describing what task was being dispatched | MUST |
| 014 | Subprocess failures (non-zero exit code) MUST record: exit code, stderr content, task name, model, duration. Status becomes `error` | MUST |
| 015 | Malformed JSON from Claude (stdout is not valid JSON matching the result contract) MUST record: raw output preserved, status becomes `partial`, log at WARNING | MUST |
| 016 | Empty stdout from subprocess MUST be treated as `error`, not silently ignored. Log at ERROR with stderr content | MUST |

### Retry Policy
| ID | Requirement | Priority |
|----|-------------|----------|
| 017 | System SHALL rondo does NOT retry dispatches by default. A failed task stays failed for this round. Retries are the consumer's responsibility (run the round again) | MUST |
| 018 | System SHALL rate limit detection: if stream-json includes a `rate_limit_event` indicating blocked status, log at WARNING with `rate_limit_resets_at`. Do not retry — record the rate limit in DispatchUsage and let the consumer decide | MUST |
| 019 | System SHALL subprocess timeout: configurable via `task_timeout_sec` in config. Default: 300 seconds. On timeout, kill the process, record status `error` with error_code `DISPATCH_TIMEOUT` | MUST |

### Performance
| ID | Requirement | Priority |
|----|-------------|----------|
| 020 | Every task dispatch MUST track wall-clock `duration_sec` using `time.perf_counter()` (start to finish including subprocess overhead) | MUST |
| 021 | System SHALL stream-json provides `duration_ms` (API wall-clock) and per-turn timing. These go into DispatchUsage, separate from the Python-measured wall-clock | MUST |
| 022 | Per-dispatch cost tracking MUST capture: `input_tokens`, `output_tokens`, `cost_usd`, `cache_read_tokens`, `cache_create_tokens`. Source: stream-json `result` event | MUST |
| 023 | Round-level summary MUST aggregate: total `duration_sec`, total `cost_usd`, total tasks, pass/fail counts. This is the `RoundResult.summary` field | MUST |
| 024 | All performance data MUST be available in the returned RoundResult object AND in spool files. Consumers should not need to parse logs for metrics | MUST |

### Spool Files
| ID | Requirement | Priority |
|----|-------------|----------|
| 025 | Every task result MUST be written to a JSON file in the results directory immediately after dispatch completes. Files persist across crashes | MUST |
| 026 | System SHALL spool directory structure: `{results_dir}/{round-name}_{ISO-timestamp}/task-{NN}-{task-name}.json`. One directory per round execution | MUST |
| 027 | Round summary MUST be written as `round-summary.json` in the same directory after all tasks complete | MUST |
| 028 | System SHALL spool files have a configurable TTL (default: 30 days). Cleanup is the consumer's responsibility — Rondo writes, consumers prune | MUST |

### Metrics: Store Everything, Prune Later
**GOLDEN RULE: Don't decide what's noise at capture time. Decide at query time.**
| ID | Requirement | Priority |
|----|-------------|----------|
| 029 | System SHALL default is KEEP ALL. Every measurement stored in spool files. What looks like noise today is the pattern ACE discovers tomorrow | MUST |
| 030 | System SHALL spool-based metrics: each TaskResult includes a `metrics` dict with `metric_name`, `metric_value`, `metric_unit`, `context`, `captured_at`. Consumers (OB, ACE) ingest into their DBs | MUST |
| 031 | System SHALL store per-dispatch: task name, model, auth_mode, pass/fail, duration_ms, output_length, prompt_length | MUST |
| 032 | System SHALL store per-API-call (from stream-json): endpoint, tokens_in, tokens_out, cost_usd, response_time_ms, model, cache_read_tokens, cache_create_tokens | MUST |
| 033 | System SHALL store per-file (when dispatching file-scoped tasks): line_count, function_count, complexity score, findings count | MUST |
| 034 | System SHALL store per-round (via DispatchUsage fields): duration, working_time, findings, files_changed, total_cost_usd, total_tokens | MUST |
| 035 | System SHALL cost: ~200 bytes per metric entry in spool JSON. Store everything for years | MUST |
| 036 | System SHALL monthly prune job: flag metrics with zero variance or zero queries. Mark approves deletion. NEVER auto-delete. Rondo spool TTL (28 days default) is separate — metrics survive in consumer DBs | MUST |
| 037 | System SHALL cross-project mining via ACE: noise in one project = pattern across five | MUST |

---
## 4. Architecture / Design

Three observability layers: (1) Python `logging` for Rondo's own operations (config loading, runner decisions), (2) subprocess stdout/stderr capture for each `claude -p` dispatch, (3) stream-json parsing for structured metrics (tokens, cost, timing). All three converge into the TaskResult and spool file for each dispatch.

---

## 5. Data Model

Observability data lives in two places: the `TaskResult` dataclass (per-dispatch metrics, stdout, stderr, parsed result) and the `RoundResult` (aggregated summary). No separate observability schema — metrics are fields on the result objects, not a parallel data store.

---

## 6. Data Boundary

Rondo captures and stores observability data in spool files. Consumers (OB, ACE) ingest from spool. The boundary is the spool directory. Rondo never pushes metrics — consumers pull from the filesystem. This keeps Rondo stateless and decoupled.

---

## 7. MCP / API Interface

Rondo does not expose observability via MCP directly. Consumers query spool files or use CORE-STD-021 MCP tools to access ingested metrics from their own stores. Future: `rondo_query_batch_status` (Rondo-IFS-104) provides dispatch status over MCP.

---

## 8. States & Modes

Logging verbosity is mode-dependent: `--verbose` enables DEBUG-level logging to stderr. Default is INFO. Dry-run mode (`--dry-run`) logs prompts with `-DRYRUN-` prefix without dispatching. These modes affect log volume, not log structure.

---

## 9. Configuration

Logging configuration follows COALESCE: `RONDO_LOG_LEVEL` env var > `rondo.toml [logging] level` > default `INFO`. Spool directory is configured via Rondo-STD-102 `paths.results_dir`. Log format is not configurable — structured format is mandatory for machine parsing.

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

## 11. Quality Attributes

- **Completeness:** Every dispatch produces a full metrics record, even on failure.
- **Traceability:** Any result can be traced to its raw stdout via the spool file.
- **Non-intrusiveness:** Observability never alters dispatch behavior — it captures, never modifies.

---

## 12. Shared Patterns

- **Stream-json extraction:** Same parsing logic for all dispatch backends (Claude today, Gemini/Ollama future).
- **Status prefix convention:** `-PASS-`, `-FAIL-`, `-ERROR-` shared with ACE build gates and Caliber output.
- **Spool mailbox pattern:** Write-once, read-many — shared with Rondo-STD-104 persistence model.

---

## 13. Integration Points

| Integration | What Crosses | Standard Enforced |
|-------------|-------------|-------------------|
| Rondo → OB | DispatchUsage metrics | Rondo-STD-100 field names |
| Rondo → Caliber | Task pass/fail status | Status prefix convention |
| Rondo → ACE | Cost and timing aggregates | NAMING-MAP.md alignment |
| Rondo → CORE-STD-013 | Dispatch events as TrackerData entries | Append-only event format |

---

## 14. Standards Applied

| Standard | How It Applies |
|----------|---------------|
| CORE-STD-002 | Parent observability standard — Rondo adapts logging, errors, performance for dispatch context |
| CORE-STD-012 | Requirement readiness — dispatch metrics feed readiness assessments |
| CORE-STD-013 | TrackerData — dispatch events are trackable data points |
| CORE-STD-021 | MCP standard — future observability queries via MCP tools |

---

## 15. Self-Correction

Observability enables self-correction in consumers, not in Rondo itself. Rondo captures the data; OB's CORE-STD-011 loop uses it to detect patterns (e.g., "sonnet fails this task 80% of the time — switch to opus"). Rondo's role is to capture faithfully, not to act on the patterns.

---

## 16. Assumptions

1. Claude CLI `--output-format stream-json` remains stable across versions.
2. Stream-json `result` event always contains token counts and cost fields.
3. Filesystem writes to spool directory complete atomically (same-filesystem rename).
4. Consumers poll spool directories — Rondo does not notify on write.

---

## 17. Success Criteria

| # | Criterion | How to Verify |
|---|-----------|---------------|
| 1 | Every dispatch produces a spool file with complete DispatchUsage | Spool test |
| 2 | Failed dispatches have stderr content preserved in TaskResult | Error test |
| 3 | Stream-json parse failure falls back gracefully with zeroed metrics | Fallback test |
| 4 | Morning report shows cost, duration, pass/fail for overnight run | Report test |

---

## 18. Build Notes / Estimate

Stream-json parser: 4 hours (event parsing, field extraction, fallback). Logging setup: 2 hours (structured format, stderr routing). Spool writer: covered by Rondo-STD-104. Total observability-specific: ~6 hours.

---

## 19. Test Categories

| Category | What It Tests |
|----------|--------------|
| Stream-json parsing | Real fixture files → correct DispatchUsage extraction |
| Error capture | Subprocess failures → stderr preserved, status correct |
| Log format | Structured log entries have all required fields |
| Spool completeness | Every dispatch → spool file exists with metrics |

---

## 20. Failure Modes

| Failure | Impact | Mitigation |
|---------|--------|------------|
| Stream-json format change | Zeroed metrics (graceful fallback) | Version-pinned fixtures, fallback path |
| Spool write failure | Metrics lost for that dispatch | Atomic write + temp file recovery (Rondo-STD-104) |
| Stderr truncation | Incomplete error context | Capture limit configurable, default 10KB |

---

## 21. Dependencies + Used By

| Direction | Spec | Relationship |
|-----------|------|-------------|
| Depends on | CORE-STD-002 | Parent observability standard |
| Depends on | Rondo-STD-100 | Field naming conventions |
| Depends on | CORE-STD-013 | TrackerData event format |
| Used by | Rondo-STD-105 | AI operations cost tracking uses these metrics |
| Used by | Rondo-STD-113 | Audit trail stores observability data |
| Used by | Rondo-IFS-102 | OB ingests metrics from spool |

---

## 22. Decisions

| Decision | Rationale | Date |
|----------|-----------|------|
| D1: Stream-json over text mode | Text mode estimates costs — stream-json gives actuals (ACE-STD-020 lesson) | 2026-03-18 |
| D2: No retry in Rondo | Retry is consumer responsibility — Rondo captures, consumers decide | 2026-03-18 |
| D3: Stderr for logs, stdout for data | Clean separation enables piping Rondo output to consumers | 2026-03-18 |

---

## 23. Open Questions

None currently. Metric storage depth (how many fields per dispatch) settled in v0.2 with "Store Everything, Prune Later."

---

## 24. Glossary

| Term | Definition |
|------|-----------|
| **Stream-json** | Claude CLI output format providing structured event stream with metrics |
| **Spool file** | JSON result file written per dispatch to the results directory |
| **DispatchUsage** | Dataclass capturing per-dispatch metrics (tokens, cost, timing) |

---

## 25. Risk / Criticality

**HIGH.** Observability is the only way to debug overnight failures. If spool files are incomplete or metrics are zeroed, post-mortem analysis is impossible. Stream-json parsing is the critical path — any Claude CLI format change breaks metric capture.

---

## 26. External Scan

Python `logging` module is the standard. No external observability frameworks (Prometheus, OpenTelemetry) needed — Rondo is local-first. If remote observability is needed later, consumers export from spool files.

---

## 27. Security Considerations

Log entries must not contain API keys or prompt content. Stderr capture may include sensitive error messages — scrub per Rondo-STD-114 before writing to spool. Spool file permissions: 0600 (owner-read-write only, per Rondo-STD-104).

---

## 28. Performance / Resource

Spool writes add ~5ms per dispatch (atomic write + fsync). Stream-json parsing adds ~2ms per dispatch. Negligible compared to the 10-300 second dispatch duration. Log volume: ~1KB per dispatch at INFO level, ~10KB at DEBUG.

---

## 29. Approval Record

| Reviewer | Role | Date | Verdict |
|----------|------|------|---------|
| Mark Hubers | Owner | 2026-03-22 | Approved (Session 84) |

---

## 30. AI Review

Reviewed by Cold Witness panel. Results in `reports/ai-reviews/`. Fix-review-fix cycle applied.

---

## 31. AI Went Wrong

No implementation yet — tracks AI-generated code deviations during build.

---

## 32. AI Assumptions

During spec design, AI assumed: Postgres target DB, YAML schemas as source of truth, MCP as query interface.

---

## 33. AI Cost

Spec review cost tracked in `reports/ai-reviews/`. ~$0.10/review/body.

---

## 34. Notes

CORE-STD-012 readiness tracking depends on accurate dispatch metrics to assess whether requirements are testable. CORE-STD-013 TrackerData format aligns with the append-only spool pattern. CORE-STD-021 MCP tools may expose observability queries in future versions.

---

### Feature Maturity

| Feature | Maturity | Evidence | Retest |
|---------|----------|----------|--------|
| Structured logging | WORKING | Python logging configured | After logging changes |
| Log level standards | WORKING | DEBUG/INFO/WARNING/ERROR used consistently | After level changes |
| Metric emission | THEORY | Specced for structured metric output | Phase 2 build |




---

## Decision Trace — Interactive Dispatch Debugging (Session 100 — merged from addendum)

## Requirements

### CLI Debug Mode

| Req # | Requirement | Priority | Test |
|-------|-------------|----------|------|
| 200 | `rondo run --debug` MUST print each routing decision to stderr as it happens: provider selection, fallback triggers, budget checks, circuit breaker state. | MUST | CLI test |
| 201 | Debug output MUST use structured format: `[DECIDE] provider=gemini reason="tier:default, health:UP, cost_est:$0.003"` | MUST | Format test |
| 202 | Debug output MUST NOT include prompt content, API keys, or raw_output. Only metadata: provider, model, reason, cost estimate, latency estimate. | MUST | Security test |
| 203 | Debug mode MUST NOT change dispatch behavior — same routing, same results, just with visibility. | MUST | Behavior test |
| 204 | Debug output MUST include timing: `[DECIDE +0.3s]` elapsed since dispatch start. | SHOULD | Timing test |

### MCP Decision Trace

| Req # | Requirement | Priority | Test |
|-------|-------------|----------|------|
| 210 | `rondo_run` MCP tool MUST accept optional `trace=True` parameter. When set, the response JSON includes a `decisions` array with each routing decision. | MUST | MCP test |
| 211 | Decision trace in MCP response: `[{"step": "provider_select", "chose": "gemini:flash", "reason": "tier:default", "alternatives": ["grok:grok-3"], "elapsed_ms": 12}]` | MUST | Schema test |
| 212 | Decision trace MUST include budget state: `{"step": "budget_check", "running_cost": 0.05, "cap": 0.10, "action": "proceed"}` | MUST | Budget test |
| 213 | Decision trace MUST include circuit breaker state: `{"step": "breaker_check", "provider": "openai", "state": "CLOSED", "consecutive_errors": 0}` | SHOULD | Breaker test |

### Post-Hoc Explain

| Req # | Requirement | Priority | Test |
|-------|-------------|----------|------|
| 220 | `rondo explain <dispatch_id>` CLI command MUST reconstruct the decision trace from the audit trail (STD-113 INTENT + OUTCOME records). | SHOULD | CLI test |
| 221 | `rondo_explain` MCP tool (existing) SHOULD be extended to include decision trace when audit records contain trace data. | SHOULD | MCP test |

### Audit Trail Extension

| Req # | Requirement | Priority | Test |
|-------|-------------|----------|------|
| 230 | INTENT audit records (STD-113 req 003) MUST include a `decisions` field when trace is enabled. This persists the decision trace for post-hoc explain. | MUST | Audit test |
| 231 | Decision trace data MUST NOT increase INTENT record size by more than 500 bytes (typical: 200-300 bytes for 3-5 decisions). | SHOULD | Size test |

---

## Architecture

Decision trace is implemented as a lightweight collector passed through the
dispatch pipeline:

```
  resolve_dispatch_engine()  →  [DECIDE: engine=http, provider=gemini]
         |
  get_provider_with_fallback()  →  [DECIDE: primary=gemini UP, no fallback needed]
         |
  budget_check()  →  [DECIDE: running=$0.05, cap=$0.10, action=proceed]
         |
  dispatch()  →  [DECIDE: dispatched to gemini:flash, timeout=300s]
         |
  finalize_dispatch()  →  [DECIDE: cost=$0.003, status=done, audit=recorded]
```

The collector is a simple list of dicts. No new classes needed — just
`decisions: list[dict]` threaded through existing functions.

---

## Example Output

```
$ rondo run my_round.py --debug
[DECIDE +0.0s] engine=http provider=gemini reason="tier:default"
[DECIDE +0.0s] health provider=gemini status=UP latency=45ms
[DECIDE +0.0s] budget running=$0.000 cap=$1.000 action=proceed
[DECIDE +0.1s] breaker provider=gemini state=CLOSED errors=0
[DECIDE +2.3s] dispatched model=gemini-2.5-flash tokens_in=1204 tokens_out=856
[DECIDE +2.3s] cost=$0.003 total_running=$0.003
[DECIDE +2.4s] finalized audit=recorded sanitized=yes spooled=yes
  done | analyze | gemini-2.5-flash | $0.003 | 2.3s
```

---

## 35. Change History

| Version | Date | What Changed |
|---------|------|-------------|
| 0.2 | 2026-03-19 | Added "Metrics: Store Everything, Prune Later" section (reqs 29-37). Spool-based metrics with consumer ingestion, per-dispatch/per-API/per-file/per-round storage, monthly prune with approval, cross-project ACE mining. Total: 37 requirements. |
| 0.1 | 2026-03-18 | Initial draft. Matches CORE-STD-002 topics (logging, errors, performance) adapted for Rondo's dispatch context. 28 requirements. Stream-json capture, spool file naming, no-retry policy, rate limit detection. |
| 0.4 | 2026-04-09 | Merged decision trace addendum (reqs 200-231). --debug CLI, trace=True MCP, rondo explain. Session 100. |
| 0.3 | 2026-03-22 | Filled to 35 sections. Added CORE-STD-012, CORE-STD-013, CORE-STD-021 refs. Approval record (Mark, Session 84). |
