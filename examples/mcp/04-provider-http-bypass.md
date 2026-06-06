# rondo-meta: mode=http provider=anthropic,gemini,grok,mistral,openai,ollama category=config value="Provider-prefixed model behavior that bypasses execution routing"

# 04 — Provider HTTP Bypass

Provider-prefixed models bypass execution mode and route HTTP adapters.

```text
rondo_run(
    prompt="Summarize this architecture in 6 bullets with tradeoffs.",
    model="gemini:gemini-flash-latest",
    execution="inline",
    dry_run=False
)
```

Expected behavior:
- No host plan JSON.
- Returns dispatch result (`tasks`, `cost`, `duration`) from HTTP path.

Why useful:
- You can keep one call shape and still force external-provider execution.
