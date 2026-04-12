# API Examples — Real Rondo Usage

These examples are not mock demos. They run real `rondo_run_file` dispatch.

## Purpose

Each file is designed to do three jobs at once:
- Teach how to use Rondo from Python.
- Prove the pattern works in real execution.
- Act as living documentation and integration safety net.

`rondo/tests/integration/test_api_examples.py` imports each example and runs `main()`.
If an example breaks, the integration suite fails.

## Quick Run

From the `rondo/` directory:

```bash
uv run python examples/api/01_simple_dispatch.py
uv run python examples/api/03_execution_mode_triptych.py
uv run python examples/api/background_polling_workflow.py
```

Fast living-suite smoke (high-signal subset):

```bash
rondo-test --examples-api-fast
```

Full living-suite regression (all API examples):

```bash
rondo-test --examples-api
```

## New High-Signal Examples

- `03_execution_mode_triptych.py`
  - Shows `execution="inline"`, `execution="agent"`, and `execution="subprocess"` in one run.
  - Teaches host-plan vs real-result behavior directly.

- `background_polling_workflow.py`
  - Starts background dispatch (`background=True`) and polls heartbeat/brief/full status.
  - Teaches real async automation pattern for long-running tasks.

- `idempotency_cache_demo.py`
  - Runs the same live request twice and compares time + payload.
  - Teaches how idempotency dedupe behaves in real usage.

- `error_recovery_patterns.py`
  - Forces a deterministic error envelope, then recovers with a real dispatch.
  - Teaches retry/recovery with actionable `error_code` + `error_help`.

- `partial_status_handling.py`
  - Demonstrates non-JSON/partial-style handling while preserving `raw_output`.
  - Teaches safe fallback parsing when strict JSON is not available.

- `provider_fallback_chain.py`
  - Intentionally fails a primary provider path, then falls back to subprocess dispatch.
  - Teaches practical fallback behavior for production scripts.

- `timeout_and_backoff.py`
  - Implements timeout-oriented retries with exponential backoff.
  - Teaches deterministic error-path probing plus live retry loops.

- `envelope_validation.py`
  - Validates canonical top-level envelope keys from a live run.
  - Teaches contract checks and unknown dispatch-id error handling.

## Expected Environment

These are live examples. You need a working dispatch environment:
- Claude CLI available for `model="sonnet"` subprocess runs, or
- API keys configured for provider-prefixed models.

Examples exit `0` on success and `1` on handled runtime errors.

## Related Example Sets

- `examples/mcp/`: MCP-first workflows for Claude Code (13 examples).
- `examples/cli/`: shell automation and scripted prompting patterns.
- See also: `../INDEX.md` for the cross-directory 76-example map.
- Envelope semantics and `error_code` troubleshooting: `../../docs/ERROR-ENVELOPE-CONTRACT.md`.
