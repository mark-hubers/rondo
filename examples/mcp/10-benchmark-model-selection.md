# rondo-meta: mode=subprocess,http provider=anthropic,gemini,grok,mistral,openai category=observability value="Benchmarking model options before choosing defaults"

# 10 — Benchmark Before Standardizing

Benchmark several models on the same task before picking defaults.

```text
rondo_benchmark(
    prompt="Review this function for correctness and edge cases.",
    models='["sonnet","gemini:gemini-flash-latest","grok:grok-4.3","local:qwen2.5:32b"]',
    dry_run=False
)
```

Expected:
- latency and output comparisons,
- ranked model results.

Prompt-scripting idea:
- Run benchmark weekly and update routing defaults from evidence.
