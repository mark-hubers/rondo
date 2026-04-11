# 03 — Subprocess Fresh Session

Use when you want execution isolated from current conversation context.

```text
rondo_run(
    prompt="Generate a strict JSON checklist for release readiness.",
    model="sonnet",
    execution="subprocess",
    dry_run=False,
    timeout_sec=180
)
```

Expected shape (result):
- `status` (`done|partial|error`)
- `tasks` array
- `done_count`, `error_count`, `total_cost_usd`

Prompt-scripting idea:
- Reliable for batch scripts where you always want task results, not plans.
