# rondo-meta: mode=subprocess provider=anthropic category=observability value="End-to-end health/metrics/history/audit monitoring flow"

# 13 — Observability Suite

Operational MCP calls you should run regularly.

```text
rondo_health()
rondo_metrics()
rondo_cost(days=30)
rondo_history(limit=20)
rondo_audit_summary(limit=20)
rondo_models()
rondo_dispatch_info()
```

Use this sequence for:
1. health state,
2. spend/performance trends,
3. recent failures and context,
4. configured model/provider reality.

Why useful:
- Turns Rondo from "it seems fine" to measurable operational confidence.
