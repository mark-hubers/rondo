# rondo-meta: mode=http provider=anthropic,gemini,grok,mistral,openai category=review value="Multi-provider review workflow through MCP tools"

# 06 — Multi-Provider Review Consensus

Send one prompt to multiple providers and merge findings.

```text
rondo_multi_review(
    prompt="Review this design for security and reliability issues.",
    providers='["gemini:gemini-2.5-flash", "grok:grok-3", "mistral:mistral-large-latest"]',
    dry_run=False
)
```

Expected output:
- per-provider result blocks,
- merged summary/findings,
- per-provider status/cost/duration.

Prompt-scripting idea:
- Use consensus (2+ providers agree) as high-confidence finding signal.
