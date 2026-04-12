# Error Envelope Contract

Rondo dispatch paths use one canonical envelope contract for result and error payloads.

Authoritative spec: `specs/Rondo-REQ-112-error-envelope.md`.

---

## Canonical fields

Dispatch result payloads expose:

- `schema_version`
- `status`
- `tasks`
- `done_count`
- `error_count`
- `partial_count`
- `pending_count`
- `total_cost_usd`
- `duration_sec`
- `dry_run`

When `status="error"`, payloads also include:

- `error_code`
- `error_message`

Backward-compatible aliases may still appear:

- `error` (alias of `error_message`)
- `code` (alias of `error_code`)

---

## Status semantics

- `done`: all completed/skipped successfully
- `partial`: at least one task partially succeeded (for example malformed JSON parse with usable raw output)
- `error`: hard-failure terminal state (no successful/partial tasks)
- `running`: in-progress background dispatch
- `dispatched`: accepted and queued in background
- `plan`: host plan payload (`inline`/`agent` routing)

### Why `partial` matters

`partial` means Rondo executed real work and captured output, but strict contract completion did not fully succeed.
Treat it as **success-with-caveat**, not the same as hard failure.

---

## Envelope examples

### done

```json
{
  "schema_version": "2",
  "status": "done",
  "tasks": [{"name": "t1", "status": "done"}],
  "done_count": 1,
  "error_count": 0,
  "partial_count": 0,
  "pending_count": 0,
  "total_cost_usd": 0.01,
  "duration_sec": 1.2,
  "dry_run": false
}
```

### partial

```json
{
  "schema_version": "2",
  "status": "partial",
  "tasks": [{"name": "t1", "status": "partial", "error_code": "ERR_MALFORMED_JSON"}],
  "done_count": 0,
  "error_count": 0,
  "partial_count": 1,
  "pending_count": 0,
  "total_cost_usd": 0.0,
  "duration_sec": 2.0,
  "dry_run": false
}
```

### error

```json
{
  "schema_version": "2",
  "status": "error",
  "error_code": "ERR_INVALID_INPUT",
  "error_message": "Provide file_path or prompt",
  "tasks": [],
  "done_count": 0,
  "error_count": 0,
  "partial_count": 0,
  "pending_count": 0,
  "total_cost_usd": 0.0,
  "duration_sec": 0.0,
  "dry_run": false
}
```

---

## Troubleshooting by `error_code`

| error_code | Meaning | Typical action |
|---|---|---|
| `ERR_INPUT_TOO_LARGE` | Prompt/context exceeded input limits | Trim input, chunk context, or summarize first |
| `ERR_FILE_NOT_FOUND` | Round or target file path missing | Verify absolute/relative path and current working directory |
| `ERR_PROJECT_NOT_FOUND` | `project` directory path invalid | Pass an existing directory |
| `ERR_INVALID_INPUT` | Required args missing or invalid | Re-check required parameters (`prompt` or `file_path`) |
| `ERR_INVALID_EXECUTION` | Unsupported `execution` mode value | Use `inline`, `subprocess`, `agent`, or empty for auto |
| `ERR_INVALID_EXECUTION_MODEL` | `execution="agent"` with non-Claude model | Use Claude model (`sonnet`, `opus`, `haiku`) for agent mode |
| `ERR_PROVIDER_DOWN` | Target provider unavailable | Retry later or route to healthy provider |
| `ERR_PROVIDER` | Provider adapter/transport exception | Check API keys, network, provider status |
| `ERR_BUDGET_EXCEEDED` | Budget gate blocked task | Increase budget or reduce task count |
| `ERR_MALFORMED_JSON` | Model output not parseable as strict JSON | Treat as partial, inspect `raw_output`, tighten prompt/return schema |
| `ERR_DISPATCH_EXCEPTION` | Internal dispatch exception wrapper | Inspect `error_message`, then retry or report bug with payload |
| `ERR_UNKNOWN_DISPATCH_ID` | Background dispatch id not found | Verify id spelling, TTL, or whether process was restarted |

---

## Interface notes

- MCP `rondo_run` and API `rondo_run_file` return canonical envelopes for dispatch payloads.
- `rondo_run_status` full mode returns canonical envelopes for background results.
- CLI inline prompt mode returns normalized smart-return JSON, not the full dispatch envelope.
