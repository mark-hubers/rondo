# REQ-101 Addendum: Multi-Account Capacity Management

**Parent:** REQ-101 (Automation)
**Created:** 2026-03-20 | **Status:** DESIGNED

---

## Problem

One Claude Code Max account shared between Mark (interactive) and Rondo (overnight batch) means contention: batch runs eat Mark's rate limit, and Mark's interactive work blocks batch progress. Separate accounts = separate rate limit pools = zero contention.

## Architecture

```
Mark's Account ($200/month Max)
  └── Interactive Claude Code sessions
  └── Rate limit pool A (Mark's 5-hour window)
  └── ANTHROPIC_API_KEY in Mark's env

Rondo's Account ($20-$100/month Max)
  └── Overnight batch dispatches
  └── Container builds (OB-REQ-129)
  └── Automated reviews + fixes
  └── Rate limit pool B (Rondo's OWN 5-hour window)
  └── RONDO_API_KEY separate env var
```

## Requirements

| # | Requirement | Priority |
|---|------------|----------|
| 1 | Support multiple Claude Code accounts via separate API keys in config | MUST |
| 2 | Per-provider routing: `interactive` tasks → Mark's account, `overnight`/`container` tasks → Rondo's account | MUST |
| 3 | Each account has independent rate limit tracking (`is_using_overage` tracked per account) | MUST |
| 4 | Account selection in config, not code: `[providers.claude-batch] api_key_env = "RONDO_API_KEY"` | MUST |
| 5 | Fallback: if Rondo's account is rate-limited, DO NOT fall back to Mark's account (protect interactive capacity) | MUST |
| 6 | Cost tracking per account: morning report shows "Mark's account: $X, Rondo's account: $Y" | MUST |
| 7 | Budget alerts per account: "Rondo's account at 80% of monthly budget" independent of Mark's | MUST |
| 8 | Account health in preflight: `rondo preflight` shows rate limit status for ALL configured accounts | SHOULD |
| 9 | Same OAPayload/OAResult regardless of which account dispatched — model-agnostic AND account-agnostic | MUST |
| 10 | Support mixed providers: Rondo's account for Claude batch, Google API key for Gemini review, Ollama for cheap tasks | SHOULD |

## Configuration

```toml
## Rondo provider configuration

[providers.claude-interactive]
type = "claude-cli"
auth = "max"
api_key_env = "ANTHROPIC_API_KEY"
description = "Mark's interactive account"
budget_monthly_usd = 200.00

[providers.claude-batch]
type = "claude-cli"
auth = "max"
api_key_env = "RONDO_API_KEY"
description = "Rondo's overnight account"
budget_monthly_usd = 100.00

[providers.gemini]
type = "rest"
api_key_env = "GOOGLE_API_KEY"
endpoint = "https://generativelanguage.googleapis.com/v1beta"
description = "Google Gemini for review tasks"
budget_monthly_usd = 50.00

[providers.ollama]
type = "rest"
endpoint = "http://localhost:11434"
description = "Local Ollama for cheap batch tasks"
budget_monthly_usd = 0.00

## Routing: which provider for which task type
[routing]
interactive = "claude-interactive"     # Mark's sessions
overnight_build = "claude-batch"       # Rondo's account
overnight_review = "gemini"            # Gemini for review (cheaper)
container_build = "claude-batch"       # Container builds on Rondo's account
cheap_batch = "ollama"                 # Local model for high-volume low-stakes
fallback = "claude-batch"             # Default if no routing match

## Capacity rules
[capacity]
never_fallback_to_interactive = true   # PROTECT Mark's rate limit
pause_on_overage = false               # Continue on Rondo's overage (it's paid for)
switch_to_ollama_if_rate_limited = true # Use local model while waiting for rate reset
```

## Capacity Scenarios

| Scenario | Behavior |
|----------|----------|
| Rondo's account rate-limited at 2am | Pause dispatch OR switch to Ollama (per config). NEVER touch Mark's account. |
| Mark working + Rondo overnight simultaneously | Zero contention — different accounts, different rate pools |
| Gemini API down | Rondo routes review tasks to claude-batch. OAPayload unchanged. |
| Budget alert on Rondo's account | Morning report: "Rondo account at $85/$100." Mark decides to top up or reduce batch. |
| All cloud providers down | Switch to Ollama (local). Slower but free and always available. |

## Why This Matters

| Metric | One Account | Two Accounts |
|--------|-------------|--------------|
| Interactive rate limit impact | Overnight eats capacity | Zero impact |
| Overnight throughput | Competes with Mark | Full dedicated capacity |
| Cost visibility | Blended "who spent what?" | Per-account tracking |
| Resilience | One rate limit = one failure | Independent pools |

## Provider Adapter Integration (CORE-ADR-001)

Each provider entry in config maps to a ProviderAdapter instance:

```python
## Rondo creates one adapter per provider config entry
adapters = {
    "claude-interactive": ClaudeCLIAdapter(api_key="ANTHROPIC_API_KEY", auth="max"),
    "claude-batch": ClaudeCLIAdapter(api_key="RONDO_API_KEY", auth="max"),
    "gemini": GeminiAdapter(api_key="GOOGLE_API_KEY"),
    "ollama": OllamaAdapter(endpoint="http://localhost:11434"),
}

## Routing table selects adapter per task type
def select_provider(task_type: str) -> ProviderAdapter:
    provider_name = config.routing[task_type]
    return adapters[provider_name]
```

Multiple accounts of the SAME provider = multiple adapter instances with different API keys. Same code, different credentials.
