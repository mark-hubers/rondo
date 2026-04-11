# 08 — Cloud Profile + Tier Dispatch

Dispatch to profile-selected providers with quality/cost tier.

```text
rondo_cloud(
    prompt="Analyze coupling hotspots and suggest decoupling steps.",
    profile="review",
    tier="high",
    count=2,
    dry_run=False
)
```

Useful patterns:
- `tier="low"` for cheap triage,
- `tier="high"` for final decision support.

Best practice:
- Keep profile definitions in `~/.rondo/config.toml`.
