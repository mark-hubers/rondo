# Rondo MCP Examples

7 examples showing how to use Rondo's MCP tools from Claude Code.
These are tool calls — you invoke them from a Claude Code session.

## 1. Single Dispatch (rondo_run)
```
rondo_run(prompt="Review this code for bugs", model="gemini:flash", dry_run=false)
→ Returns JSON with task results, cost, duration
```

## 2. Multi-Provider Review (rondo_multi_review)
```
rondo_multi_review(
    prompt="Review this architecture for scalability issues",
    providers='["gemini:flash", "grok:grok-3", "mistral:large"]'
)
→ Returns per-provider findings (each with status, output, cost, duration)
```

## 3. File Review (rondo_review_file)
```
rondo_review_file(path="/path/to/file.py")
→ Sends file content to multiple providers for independent review
```

## 4. Health Check (rondo_health)
```
rondo_health()
→ {"status": "GREEN", "providers": 5, "dispatches_24h": 47, ...}
```

## 5. Metrics Dashboard (rondo_metrics)
```
rondo_metrics()
→ Full metrics: cost, reliability, latency, tokens, health per provider
```

## 6. Second Opinion (rondo_explain)
```
rondo_explain(output="AI said X", question="Is this correct?")
→ Local model gives second opinion on another AI's output ($0)
```

## 7. Cloud Dispatch with Tier (rondo_cloud)
```
rondo_cloud(prompt="Deep analysis of this codebase", tier="high")
→ Uses best_model tier for premium providers (opus-level quality)
```

## Output Format

All MCP tools return JSON. The per_provider array contains each
provider's response with status, output, cost, and duration.

Smart return templates are automatically injected — every provider
returns structured JSON with passed, confidence, issues, suggestions,
metadata, and _meta (self-rating).
