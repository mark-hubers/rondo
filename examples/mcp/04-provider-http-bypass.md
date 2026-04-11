# 04 — Provider HTTP Bypass

Provider-prefixed models bypass execution mode and route HTTP adapters.

```text
rondo_run(
    prompt="Summarize this architecture in 6 bullets with tradeoffs.",
    model="gemini:gemini-2.5-flash",
    execution="inline",
    dry_run=False
)
```

Expected behavior:
- No host plan JSON.
- Returns dispatch result (`tasks`, `cost`, `duration`) from HTTP path.

Why useful:
- You can keep one call shape and still force external-provider execution.
