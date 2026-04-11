# 09 — Chain Pipeline (Step Output Feeds Next)

Use for find -> fix -> verify or similar multi-step prompt workflows.

```text
rondo_chain(
    steps_json='[
      {"prompt":"Find top 5 risks in this code block.", "model":"gemini:gemini-2.5-flash"},
      {"prompt":"For each risk, propose a concrete fix.", "model":"sonnet"},
      {"prompt":"Verify the proposed fixes and flag weak ones.", "model":"grok:grok-3"}
    ]',
    dry_run=False
)
```

Why powerful:
- Keeps context progression explicit and scriptable.
- Each step can use the best model for that stage.
