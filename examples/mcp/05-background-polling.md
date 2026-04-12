# rondo-meta: mode=subprocess provider=anthropic category=observability value="Background run lifecycle and polling tiers from MCP"

# 05 — Background + Polling Tiers

Run long tasks asynchronously and poll cheaply.

Start:

```text
rondo_run(
    prompt="Perform a deep review and return structured findings.",
    model="sonnet",
    execution="subprocess",
    background=True,
    dry_run=False
)
```

Poll:

```text
rondo_run_status(dispatch_id="mcp-abc123", heartbeat=True)  # ~10 tokens
rondo_run_status(dispatch_id="mcp-abc123", brief=True)      # ~40 tokens
rondo_run_status(dispatch_id="mcp-abc123")                  # full payload
```

Use in automation loops:
- heartbeat until near-complete,
- brief for normal checks,
- full only when done.
