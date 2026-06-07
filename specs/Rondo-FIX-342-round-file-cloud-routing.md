# Rondo-FIX-342: Round-file cloud-model routing

**Product:** Rondo | **Category:** FIX | **Sprint:** RONDO-342
**Created:** 2026-06-07 | **Status:** ACTIVE
**Found by:** usher-syndrome 80-vote cloud panel (`rondo run rondo-signal-adjudicate.py`)

---

## 1. The bug

`rondo run <roundfile>` cannot dispatch cloud models. A round whose tasks
carry provider models (`gemini:high`, `grok:high`, …) fails every task with:

```
Invalid model 'grok:high'. Valid: ['haiku','opus','opus[1m]','sonnet','sonnet[1m]']
error: 0/80 tasks done
```

## 2. Root cause

Rondo has **two dispatch front-doors** and only one was wired for cloud:

| Front-door | Entry | Cloud routing |
|------------|-------|---------------|
| Inline CLI | `rondo "x" --model gemini:…` → `_dispatch_with_provider` | ✓ `get_provider_with_fallback` |
| MCP | `rondo_run_file(...)` → `_dispatch_via_provider_or_claude` | ✓ `get_provider_with_fallback` |
| **Round file** | `rondo run f.py` → `run_sequential`/`run_parallel` → `dispatch_task` | ✗ **Claude-only** |

`dispatch_task` calls `resolve_model` (`dispatch.py:322`) which validates
against `VALID_MODELS` (Claude-only) and **raises before any provider
routing**. The `is_claude_model` branch 180 lines later was meant to handle
non-Claude models but is unreachable — dead code behind a gate.

## 3. Why it hid

Every cloud test goes through `rondo_run_file`. **Zero** tests ran
`run_round()` with a cloud-model round file. Test gap hid routing gap.
Pinned now by `tests/integration/test_round_file_cloud_routing.py` (5 tests,
RED before this fix).

## 4. The fix

Add a per-task **router** that both round runners call instead of
`dispatch_task` directly:

```
dispatch_task_routed(task, config, *, cli_model=None, round_name="")
  effective = cli_model or task.model or config.default_model
  if task.is_auto or parse_model(effective)[0] == "":   # Claude / inline / auto
      return dispatch_task(...)                          # unchanged path
  return _dispatch_task_via_provider(task, config, effective, round_name)
```

`_dispatch_task_via_provider` reuses the EXISTING proven seams:
- `get_provider_with_fallback(model)` — same router the CLI/MCP paths use
- `dry_run=True` → skipped preview (free, no dispatch)
- provider down → `ERR_PROVIDER_DOWN` through the pipeline (REQ-109 req 016)
- else → `provider.dispatch(bare_model)` + `_finalize_dispatch` (audit,
  sanitize, spool, history, metrics — the ALWAYS-ON pipeline)
- bare-model strip via `parse_model` (RONDO-328: adapters get the bare id)

### Touch list

| File | Change |
|------|--------|
| `src/rondo/dispatch.py` | + `dispatch_task_routed`, + `_dispatch_task_via_provider` |
| `src/rondo/runner.py` | `_dispatch_with_safety_net` → call `dispatch_task_routed` |
| `src/rondo/parallel.py` | thread worker → call `dispatch_task_routed` |
| `tests/integration/test_round_file_cloud_routing.py` | the detection suite (done, RED) |

## 5. Non-goals / invariants

- Claude dispatch path unchanged (regression-guarded).
- Real cloud dispatch (non-dry-run) still needs keys — dry-run must not.
- No new dependency; reuses `get_provider_with_fallback` + `_finalize_dispatch`.

## 6. Verification

1. RED: 4/5 detection tests fail with "Invalid model" (captured 2026-06-07).
2. GREEN after fix: all 5 pass.
3. `bin/build` green (6 gates).
4. Linux container re-run (RONDO-341 harness) stays green.
5. Live canary (Mark's terminal, ~$0.01): `rondo run` a 2-task gemini+grok
   round, confirm real votes return — the unmocked end-to-end proof.

## 7. Change history

| Version | Date | Change |
|---------|------|--------|
| 0.1 | 2026-06-07 | Initial: bug, root cause (two front-doors), router fix, detection suite. |
