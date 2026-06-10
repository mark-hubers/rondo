# rondo-meta: mode=agent provider=anthropic category=basic value="Explicit agent plan mode for host-side execution"

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

Expected shape (plan, schema "3" — RONDO-394):
- `engine="agent"`
- `kind="agent_dispatch_plan"`
- `status="plan"`
- `schema_version="3"`, `dispatch_id="dsp_..."` (audited: INTENT + advisory
  OUTCOME written before return)
- `guarantees_scope="advisory"` + the `not_covered` list — an agent plan is
  host-executed; rondo declares what it cannot guarantee instead of silently
  not covering it. Subprocess plans carry `guarantees_scope="guarded"` —
  consumers can never mistake one for the other.

Host behavior:
1. Spawn Agent with `model` from plan.
2. Run plan prompt.
3. Return task result to user.
