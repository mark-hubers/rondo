# 02 — Agent Host Plan

Use when you want host Agent isolation with a specific Claude model.

```text
rondo_run(
    prompt="Audit this module for race conditions and propose fixes.",
    model="opus",
    execution="agent",
    dry_run=False
)
```

Expected shape (plan):
- `engine="agent"`
- `kind="agent_dispatch_plan"`
- `status="plan"`

Host behavior:
1. Spawn Agent with `model` from plan.
2. Run plan prompt.
3. Return task result to user.
