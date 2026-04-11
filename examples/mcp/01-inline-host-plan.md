# 01 — Inline Host Plan (MCP Default)

Use when you want current-session context.

```text
rondo_run(
    prompt="Review this patch and return top 3 risks as JSON.",
    model="sonnet",
    execution="",
    dry_run=False
)
```

Expected shape (plan):
- `engine="inline"`
- `kind="inline_dispatch_plan"`
- `status="plan"`

Host behavior:
1. Read `prompt`.
2. Execute in current session.
3. Return only the requested output.
