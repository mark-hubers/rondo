# Rondo-REQ-109 Addendum: Adaptive Provider Scoring

**Parent:** Rondo-REQ-109-provider-adapters.md
**Created:** 2026-04-09
**Origin:** Session 100 — AI review consensus + resolves REQ-109 Q2 (OPEN → DECIDED)
**Status:** DRAFT

---

## Problem Statement

Rondo has `recommend_model(task_type)` (REQ-109 req 028) that reads from TOML
config. But this is static — if Gemini starts failing code reviews or Grok
becomes 3x cheaper, the user must manually update config. The system has
history data (dispatch records with cost, latency, success/failure per
provider+task_type) but doesn't use it for routing.

**REQ-109 Q2 resolution:** "Should affinity tracking influence automatic routing?"
**DECIDED: Yes, with COALESCE — manual config always wins over learned scoring.**

`COALESCE(manual_config, learned_score, default_map)`

This means:
- If user sets `[routing.task_models].code-review = "grok:grok-3"` → Grok wins. Always.
- If no manual config → learned scoring picks the best-performing provider.
- If no history data → default map (existing `_DEFAULT_TASK_MODELS`).

---

## Requirements

### Provider Score Computation

| Req # | Requirement | Priority | Test |
|-------|-------------|----------|------|
| 300 | `compute_provider_score(provider, task_type)` MUST return a float 0.0-1.0 based on historical dispatch data for that provider+task_type combination. | MUST | Unit test |
| 301 | Score formula: `success_rate * 0.5 + (1 - normalized_cost) * 0.3 + (1 - normalized_latency) * 0.2`. Weights are configurable via `[scoring.weights]` in config.toml. | MUST | Formula test |
| 302 | Minimum 10 dispatches required before a provider gets a learned score. Below threshold → score is None (use default map). | MUST | Threshold test |
| 303 | Score window: only dispatches from the last 7 days are used. Older data decays — prevents stale scores from a provider that improved/degraded. | MUST | Window test |
| 304 | `success_rate` = dispatches with status "done" / total dispatches (excluding "skipped"). | MUST | Calculation test |
| 305 | Score computation MUST be cached for 5 minutes (same TTL as health cache). Recomputing on every dispatch is wasteful. | MUST | Cache test |

### Adaptive Routing

| Req # | Requirement | Priority | Test |
|-------|-------------|----------|------|
| 310 | `recommend_model(task_type)` MUST use COALESCE: `manual_config → learned_best → default_map → "sonnet"`. | MUST | COALESCE test |
| 311 | `learned_best` = provider+model with highest score for this task_type (from req 300). | MUST | Selection test |
| 312 | When learned scoring changes the recommended provider (vs what default_map would pick), a `log_event("INFO", "adaptive routing")` MUST be emitted with old and new provider. | MUST | Logging test |
| 313 | `rondo providers --scores` CLI command MUST show per-provider scores with breakdown (success_rate, avg_cost, avg_latency, sample_count, score). | SHOULD | CLI test |
| 314 | MCP `rondo_health()` response MUST include `provider_scores` dict when scores are available. | SHOULD | MCP test |

### Safety Rails

| Req # | Requirement | Priority | Test |
|-------|-------------|----------|------|
| 320 | Manual config ALWAYS wins over learned scoring (COALESCE rule). A user who sets a provider in config.toml MUST NOT be overridden by scoring. | MUST | Override test |
| 321 | If the learned-best provider is currently DOWN (health check), fall back to the next-highest-scoring healthy provider. | MUST | Fallback test |
| 322 | Scoring MUST NOT create feedback loops: if Provider A scores highest and gets all traffic, Provider B never gets dispatches to improve its score. Mitigation: 10% exploration rate — 1 in 10 dispatches goes to a random non-top provider. | SHOULD | Exploration test |
| 323 | `[scoring.enabled]` config flag (default: true). Users can disable learned routing entirely. | MUST | Config test |
| 324 | Score data is read-only for the scoring module. It reads from dispatch history (REQ-104). It does NOT write its own data store. | MUST | Read-only test |

---

## Data Source

Scoring reads from existing dispatch history (REQ-104 `DispatchRecord`):
- `provider`: which provider handled the dispatch
- `model`: which model was used
- `status`: done/error/blocked
- `cost_usd`: actual cost
- `duration_sec`: wall-clock time
- `task_type`: from the task definition (if set)

No new tables or storage needed. This is a **read-only consumer** of existing data.

---

## Score Formula Detail

```
score = (success_rate * w_success) + ((1 - norm_cost) * w_cost) + ((1 - norm_latency) * w_latency)

where:
  success_rate = done_count / (done_count + error_count)
  norm_cost = (avg_cost - min_cost) / (max_cost - min_cost)  # 0=cheapest, 1=most expensive
  norm_latency = (avg_latency - min_latency) / (max_latency - min_latency)
  w_success = 0.5 (default)
  w_cost = 0.3 (default)
  w_latency = 0.2 (default)

  If only one provider has data, norm_cost = 0, norm_latency = 0 (no comparison possible).
```

---

## Example

After 50 dispatches for `code-review`:

| Provider | Success | Avg Cost | Avg Latency | Score |
|----------|---------|----------|-------------|-------|
| gemini:flash | 95% | $0.003 | 2.1s | 0.87 |
| grok:grok-3 | 88% | $0.008 | 3.4s | 0.68 |
| mistral:large | 92% | $0.005 | 2.8s | 0.78 |

Result: `recommend_model("code-review")` returns `gemini:flash` (highest score),
unless user has manual config override.

```
$ rondo providers --scores
  Provider        Success  Avg Cost  Avg Latency  Score  Sample
  ────────────    ───────  ────────  ───────────  ─────  ──────
  gemini:flash    95%      $0.003    2.1s         0.87   47
  grok:grok-3     88%      $0.008    3.4s         0.68   38
  mistral:large   92%      $0.005    2.8s         0.78   22
```

---

## Risk

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Feedback loop (best provider gets all traffic) | Medium | Medium | Req 322: 10% exploration rate |
| Stale scores from old data | Medium | Low | Req 303: 7-day window |
| Score disagrees with user expectation | Low | Medium | Req 312: log when adaptive routing changes provider. Req 320: manual always wins. |
| Insufficient data for new providers | High (initially) | Low | Req 302: 10-dispatch minimum. Graceful fallback to defaults. |

---

## Version History

| Ver | Date | Changes |
|-----|------|---------|
| 0.1 | 2026-04-09 | Initial draft. Resolves REQ-109 Q2 (OPEN → DECIDED: yes, with COALESCE). Session 100: 5-AI consensus feature. |
