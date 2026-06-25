# Rondo Examples — Test All Checklist

Use this file to validate that MCP, CLI, and API examples are real and working.

## Scope

This checklist verifies:
- API examples (living pytest coverage),
- CLI example scripts,
- MCP example playbooks (tool-call workflows).

Run from the repo root unless noted.

---

## 1) Fast Validation (2-5 minutes)

### API examples (targeted, automated)

```bash
.venv/bin/python -m pytest tests/integration/test_api_examples.py -k "execution_mode_triptych or background_polling_workflow or idempotency_cache_demo" -q
```

Expected: passing tests.

### CLI scripts (syntax checks)

```bash
bash -n examples/cli/01-execution-modes.sh
bash -n examples/cli/02-background-polling.sh
bash -n examples/cli/03-consensus-review.sh
```

Expected: no output, exit code `0`.

---

## 2) Standard Validation (10-20 minutes)

### Full API examples living test suite

```bash
.venv/bin/python -m pytest tests/integration/test_api_examples.py -q
```

This imports/runs all API examples through `main()`.

### Real-run CLI examples

```bash
bash examples/cli/01-execution-modes.sh
bash examples/cli/03-consensus-review.sh src/rondo/mcp_dispatch.py
```

Note:
- These perform real model calls depending on provider/model availability.
- `03-consensus-review.sh` needs a valid target file path.

---

## 3) MCP Validation (Manual, in Claude Code)

Open:
- `examples/mcp/README.md`
- `examples/mcp/01-inline-host-plan.md` ... `13-observability-suite.md`

Copy/paste each tool call into Claude Code with Rondo MCP enabled.

Key behavior checks:
- `execution=""` with MCP context -> inline plan behavior.
- `execution="agent"` -> agent plan behavior.
- `execution="subprocess"` -> task result payload.
- provider-prefixed model -> HTTP route behavior.
- background + status polling returns heartbeat/brief/full shapes.

---

## 4) Optional Regression Pack

```bash
.venv/bin/python -m pytest tests/unit/test_mcp_router.py tests/integration/test_integration_flow.py tests/pat/test_mcp_integration.py -q
```

Use this when changing dispatch/execution contracts.

---

## Troubleshooting

- `ModuleNotFoundError: yaml`:
  - install project deps in the active environment and rerun.
- Provider/auth failures:
  - check `~/.rondo/config.toml`,
  - verify keys/environment,
  - run `rondo preflight`.
- CLI subprocess issues inside Claude session:
  - use MCP tool flows for in-session host-plan workflows.

---

## Recommended Review Order

1. `examples/mcp/README.md` (workflow map)
2. `examples/cli/README.md` (shell patterns)
3. `examples/api/README.md` (library patterns)
4. Run fast validation commands above
5. Run standard validation if preparing release/review handoff
