# rondo-meta: mode=inline provider=anthropic category=basic value="MCP default inline plan and host-executed behavior"

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

Expected shape (plan, schema "3" — RONDO-394):
- `engine="inline"`
- `kind="inline_dispatch_plan"`
- `status="plan"`
- `schema_version="3"`
- `dispatch_id="dsp_..."` — the plan's audit record (INTENT + an honest
  `status="advisory"` OUTCOME are written before the plan is returned)
- `guarantees_scope="advisory"` — rondo never executes inline work, so
  `not_covered` lists what is honestly NOT guaranteed here:
  `["budget", "circuit_breaker", "cost_tracking", "result_audit",
  "output_sanitization", "idempotency"]`
- `execution_token="[RONDO-EXEC:...]"` — fresh per plan, never cached

Budget note: pass `max_budget` and the plan is ESTIMATE-GATED at issuance —
a token-estimate cost above the budget refuses the plan with
`ERR_BUDGET_EXCEEDED` (actuals of host-executed work are never tracked;
that is declared, not faked).

Host behavior:
1. Read `prompt`.
2. Execute in current session.
3. Return only the requested output.
