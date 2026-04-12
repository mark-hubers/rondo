# rondo-meta: mode=subprocess provider=anthropic category=observability value="Recovery of failed dispatches using retry tools"

# 11 — Retry Failed Dispatch

Recover only failed tasks from a prior background run.

```text
rondo_retry(
    dispatch_id="mcp-abc123",
    model="sonnet"
)
```

Expected:
- `retried` count,
- `skipped` count,
- retry result list.

Why useful:
- Prevents re-running already-successful tasks.
- Fast recovery after intermittent provider/subprocess failures.
