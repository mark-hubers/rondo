# 12 — Diff Two Runs

Compare current output against previous output to detect drift or regressions.

```text
rondo_diff(
    current_json='{"tasks":[...]}',
    previous_json='{"tasks":[...]}'
)
```

Expected:
- new/changed/removed findings summary.

Prompt-scripting idea:
- Use in CI to flag new risk findings after a change.
