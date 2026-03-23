# REQ-101 Addendum: Multi-Account Capacity Management

**Parent:** REQ-101 (Automation)
**Created:** 2026-03-20 | **Status:** DESIGNED
**Classification:** open
**Version:** 0.2
**Owner:** Mark G. Hubers
**Reviewed:** not-yet
**Depends on:** REQ-100 (Core), REQ-109 (Provider Adapters), CORE-ADR-001 (Service Architecture)
**Used by:** IFS-102 (OB Integration), REQ-103 (Preflight)
**References:** CORE-STD-012 (Requirement Readiness), CORE-STD-013 (TrackerData), CORE-IFS-005 (MCP Standard)

---

**Users:** Mark (primary). Claude AI agents dispatching to other models. Future: teams needing multi-model AI orchestration.

## 1. Purpose & Scope

**What this spec does:** Defines how Rondo manages multiple AI provider accounts to eliminate contention between interactive (Mark) and batch (Rondo) usage. Each account gets its own rate limit pool, budget tracking, and cost reporting. The core principle: batch work never touches Mark's interactive capacity.

**IN scope:**
- Multi-account provider configuration
- Per-provider routing by task type
- Independent rate limit tracking per account
- Per-account cost tracking and budget alerts
- Fallback rules (what happens when an account is rate-limited)

**OUT scope:**
- Provider adapter implementation details (REQ-109 owns that)
- AI model selection logic (REQ-100 owns that)
- Overnight scheduling (REQ-101 owns that)

---

**Users:** Mark (primary). Claude AI agents dispatching to other models. Future: teams needing multi-model AI orchestration.

## 2. The Problem

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

---

**Users:** Mark (primary). Claude AI agents dispatching to other models. Future: teams needing multi-model AI orchestration.

## 3. Requirements

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

---

**Users:** Mark (primary). Claude AI agents dispatching to other models. Future: teams needing multi-model AI orchestration.

## 4. Architecture / Design

Each provider config entry creates one ProviderAdapter instance. Multiple accounts of the
same provider = multiple adapter instances with different API keys. The routing table maps
task types to provider names. At dispatch time, Rondo resolves: task_type → provider_name →
adapter instance → API key from Keychain → dispatch.

```
Task arrives
    │
    ▼
Routing table: task_type → provider_name
    │
    ▼
Provider registry: provider_name → ProviderAdapter instance
    │
    ▼
Adapter dispatches with its own API key + rate limit pool
```

---

**Users:** Mark (primary). Claude AI agents dispatching to other models. Future: teams needing multi-model AI orchestration.

## 5. Data Model

No new tables. Multi-account data is tracked through existing DispatchUsage fields plus
the `provider` field in the audit trail (STD-113). Per-account aggregation is a query-time
operation over the audit data, not a separate data store.

| Field | Source | Purpose |
|-------|--------|---------|
| `provider` | DispatchResult.provider | Which account/adapter handled this dispatch |
| `cost_usd` | DispatchResult.cost_usd | Per-dispatch cost, aggregated per provider |
| `model_used` | DispatchResult.model_used | Which model ran (within that provider's account) |

---

**Users:** Mark (primary). Claude AI agents dispatching to other models. Future: teams needing multi-model AI orchestration.

## 6. Data Boundary

**What this produces:**

| Output | Format | Consumer |
|--------|--------|----------|
| Per-account cost summary | Morning report section | Mark (human review) |
| Per-account rate limit status | Preflight output | REQ-103 (Preflight) |
| Budget threshold alerts | Notifications | REQ-105 (Notifications) |

**What this consumes:**

| Input | Format | Producer |
|-------|--------|----------|
| Provider config | TOML `[providers.*]` | `.rondo/config.toml` |
| Routing config | TOML `[routing]` | `.rondo/config.toml` |
| API keys | macOS Keychain | `ai-keys.py set` |
| Dispatch audit trail | JSONL | STD-113 |

---

**Users:** Mark (primary). Claude AI agents dispatching to other models. Future: teams needing multi-model AI orchestration.

## 7. MCP / API Interface

Not applicable for initial release. Future: an MCP tool per CORE-IFS-005 could expose
provider health and budget status, enabling AI agents to query account capacity before
dispatching expensive tasks.

---

**Users:** Mark (primary). Claude AI agents dispatching to other models. Future: teams needing multi-model AI orchestration.

## 8. States & Modes

| State | Condition | Behavior |
|-------|-----------|----------|
| **All healthy** | All providers reachable, within budget | Normal routing per config |
| **Provider rate-limited** | One provider returns rate_limit blocked | Use fallback provider (never interactive) |
| **Provider down** | Health check fails | Log WARNING, route to fallback |
| **Budget exceeded** | Provider over monthly budget | Alert + pause dispatches to that provider |
| **All providers down** | No cloud provider reachable | Switch to Ollama (local) if configured |

---

**Users:** Mark (primary). Claude AI agents dispatching to other models. Future: teams needing multi-model AI orchestration.

## 9. Configuration

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

---

**Users:** Mark (primary). Claude AI agents dispatching to other models. Future: teams needing multi-model AI orchestration.

## 10. Rules & Constraints

1. **NEVER fall back to interactive.** Batch rate-limited → use fallback provider or wait. Mark's account is sacred. Violation ID: `REQ101A-PROTECT-INTERACTIVE`
2. **Config, not code.** Account selection lives in TOML. No hardcoded API key references. Violation ID: `REQ101A-CONFIG-DRIVEN`
3. **Account-agnostic results.** OAPayload/OAResult never reveal which account dispatched. Model-agnostic AND account-agnostic. Violation ID: `REQ101A-AGNOSTIC`
4. **Per-account budgets.** Each provider has its own budget_monthly_usd. Cross-account budget aggregation is for reporting only, not enforcement. Violation ID: `REQ101A-PER-ACCOUNT-BUDGET`

---

**Users:** Mark (primary). Claude AI agents dispatching to other models. Future: teams needing multi-model AI orchestration.

## 11. Quality Attributes

| Attribute | Target | Rationale |
|-----------|--------|-----------|
| Isolation | Zero cross-account rate limit contamination | Core purpose of multi-account |
| Visibility | Per-account cost in morning report | Mark needs to see where money goes |
| Resilience | Provider down → fallback, never block overnight | Batch must complete |
| Simplicity | One TOML section per provider, one routing table | Easy to add new accounts |

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

---

**Users:** Mark (primary). Claude AI agents dispatching to other models. Future: teams needing multi-model AI orchestration.

## 12. Shared Patterns

- **COALESCE for provider selection:** Task.model override → routing table → fallback provider.
- **Dual-Path-With-Alerting:** Cloud provider is primary, Ollama is fallback. When fallback
  activates, alert is logged and included in morning report.
- **Keychain-only credentials:** Every `api_key_env` maps to a macOS Keychain entry.
  `ai-keys.py get <provider>` retrieves at dispatch time.

---

**Users:** Mark (primary). Claude AI agents dispatching to other models. Future: teams needing multi-model AI orchestration.

## 13. Integration Points

| Integration | Spec | Direction | Contract |
|-------------|------|-----------|----------|
| Provider adapters | REQ-109 | Internal | ProviderAdapter interface |
| Preflight checks | REQ-103 | Internal | Per-account health status |
| Budget alerts | REQ-105 | Internal | Per-account threshold notifications |
| Morning report | REQ-101 | Internal | Per-account cost summary |
| OB integration | IFS-102 | Outbound | Account-agnostic OAResult |

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

---

**Users:** Mark (primary). Claude AI agents dispatching to other models. Future: teams needing multi-model AI orchestration.

## 14. Standards Applied

| Standard | How Applied |
|----------|-------------|
| CORE-ADR-001 (Service Architecture) | One adapter per provider, Rondo is sole AI-aware component |
| CORE-STD-008 (Secrets) | API keys in Keychain only, never in config or git |
| CORE-STD-010 (Error Resilience) | Provider down → fallback, never crash |
| CORE-STD-012 (Requirement Readiness) | Each requirement tagged with readiness state |
| CORE-STD-013 (TrackerData) | Account-level events logged as trackerdata entries |
| CORE-IFS-005 (MCP Standard) | Future MCP tool for account health queries |

---

**Users:** Mark (primary). Claude AI agents dispatching to other models. Future: teams needing multi-model AI orchestration.

## 15. Self-Correction

- If a provider repeatedly fails health checks, Rondo demotes it from the routing table
  and logs a warning. Manual re-enablement via config change or `rondo providers --reset`.
- If per-account cost tracking drifts from actual provider billing, the morning report
  includes a "verify with provider dashboard" reminder at 90% budget threshold.
- Rate limit status is cached for 5 minutes. If cached status is stale and dispatch fails,
  Rondo refreshes the cache immediately and retries once.

---

**Users:** Mark (primary). Claude AI agents dispatching to other models. Future: teams needing multi-model AI orchestration.

## 16. Assumptions

| # | Assumption | If Wrong |
|---|-----------|----------|
| A1 | Separate API keys = separate rate limit pools | If Anthropic ties rate limits to org, not key, multi-account is useless |
| A2 | macOS Keychain is available on all target systems | Need platform-specific credential store abstraction |
| A3 | Ollama is installed and running for local fallback | If not, all-providers-down means no dispatch at all |
| A4 | Provider budgets are monthly and reset on calendar month | If billing cycle differs, budget tracking is inaccurate |

---

**Users:** Mark (primary). Claude AI agents dispatching to other models. Future: teams needing multi-model AI orchestration.

## 17. Success Criteria

| # | Criterion | How to Verify |
|---|-----------|---------------|
| 1 | Overnight dispatch uses Rondo's account, not Mark's | Audit trail shows provider=claude-batch |
| 2 | Mark's rate limit unaffected during overnight runs | Mark can dispatch interactively while batch runs |
| 3 | Morning report shows per-account costs | Report includes separate line items per provider |
| 4 | Rondo rate-limited → falls back to Ollama, not Mark's account | Test with simulated rate limit |
| 5 | Budget alert fires at 80% of Rondo's monthly budget | Test with accumulated cost data |

---

**Users:** Mark (primary). Claude AI agents dispatching to other models. Future: teams needing multi-model AI orchestration.

## 18. Build Notes / Estimate

| Item | Estimate |
|------|----------|
| Multi-adapter registry | 1 day — provider config → adapter instances |
| Routing table | 0.5 day — task_type → provider_name resolution |
| Per-account budget tracking | 1 day — aggregate from audit trail |
| Morning report per-account section | 0.5 day — template update |
| Preflight per-account health | 0.5 day — iterate configured providers |
| Total | ~3.5 days |

---

**Users:** Mark (primary). Claude AI agents dispatching to other models. Future: teams needing multi-model AI orchestration.

## 19. Test Categories

| Category | What | Count (est.) |
|----------|------|-------------|
| Unit | Routing resolution, budget calculation, adapter selection | 8 |
| Integration | Multi-provider dispatch with mock adapters | 4 |
| Fallback | Rate-limited → fallback, never-interactive guard | 4 |
| Budget | Threshold alerts at 50%, 75%, 90% | 3 |
| Config | Valid/invalid TOML parsing, missing providers | 4 |

---

**Users:** Mark (primary). Claude AI agents dispatching to other models. Future: teams needing multi-model AI orchestration.

## 20. Failure Modes

| Failure | Impact | Mitigation |
|---------|--------|------------|
| API key missing from Keychain | Provider unusable | Preflight catches before dispatch |
| All cloud providers rate-limited | No AI dispatch | Switch to Ollama or pause until reset |
| Budget tracking inaccurate | Late/missing alerts | Morning report includes "verify with dashboard" |
| Config typo in routing table | Wrong provider selected | Config validation at startup, not dispatch time |

---

**Users:** Mark (primary). Claude AI agents dispatching to other models. Future: teams needing multi-model AI orchestration.

## 21. Dependencies + Used By

| Depends On | Why |
|------------|-----|
| REQ-100 | Core dispatch framework |
| REQ-109 | Provider adapter interface and credential management |
| STD-113 | Audit trail for per-account cost aggregation |
| CORE-ADR-001 | Service architecture — Rondo is sole AI-aware component |

| Used By | Why |
|---------|-----|
| IFS-102 | OB integration needs account-agnostic dispatch |
| REQ-103 | Preflight checks all configured accounts |
| REQ-105 | Budget alerts use per-account thresholds |

---

**Users:** Mark (primary). Claude AI agents dispatching to other models. Future: teams needing multi-model AI orchestration.

## 22. Decisions

| # | Decision | Date | Why |
|---|----------|------|-----|
| D1 | Separate accounts, not shared | 2026-03-20 | Rate limit isolation is the core goal |
| D2 | NEVER fall back to interactive account | 2026-03-20 | Mark's capacity is sacred — batch waits or uses Ollama |
| D3 | Config-driven, not code-driven | 2026-03-20 | Adding accounts = TOML edit, not code change |
| D4 | Per-account budget, not aggregate | 2026-03-20 | Rondo's $100 and Mark's $200 are separate commitments |

---

**Users:** Mark (primary). Claude AI agents dispatching to other models. Future: teams needing multi-model AI orchestration.

## 23. Open Questions

| # | Question | Impact | Status |
|---|----------|--------|--------|
| Q1 | Should Rondo auto-detect Ollama availability or require explicit config? | Affects fallback reliability | OPEN |
| Q2 | Should budget tracking use provider-reported costs or Rondo-calculated costs? | Accuracy vs availability | OPEN |
| Q3 | Should there be a "maintenance mode" that pauses all dispatches across all accounts? | Affects overnight scheduling | OPEN |

---

**Users:** Mark (primary). Claude AI agents dispatching to other models. Future: teams needing multi-model AI orchestration.

## 24. Glossary

| Term | Definition |
|------|-----------|
| **Rate limit pool** | Per-account rate limit window — separate accounts have independent pools |
| **Interactive account** | Mark's personal Claude Code Max subscription for live sessions |
| **Batch account** | Rondo's dedicated account for overnight and automated dispatches |
| **Fallback provider** | Alternative provider used when primary is unavailable |

---

**Users:** Mark (primary). Claude AI agents dispatching to other models. Future: teams needing multi-model AI orchestration.

## 25. Risk / Criticality

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Anthropic changes rate limit model | Low | Multi-account may not help | Monitor Anthropic announcements |
| Rondo account costs exceed budget | Medium | Unexpected spend | Budget alerts at 50/75/90% |
| Ollama quality insufficient for fallback | Medium | Poor overnight results | Use Ollama only for low-stakes tasks |

---

**Users:** Mark (primary). Claude AI agents dispatching to other models. Future: teams needing multi-model AI orchestration.

## 26. External Scan

Multi-account API key management is standard practice in CI/CD (separate service accounts
for build vs deploy). The pattern of protecting interactive capacity from batch consumption
is analogous to database connection pool isolation (OLTP vs OLAP pools).

---

**Users:** Mark (primary). Claude AI agents dispatching to other models. Future: teams needing multi-model AI orchestration.

## 27. Security Considerations

- All API keys stored in macOS Keychain per CORE-STD-008. Never in config files or env files.
- Routing config reveals account names but not keys. Config files are safe to commit.
- Per-account isolation means a compromised batch key cannot access interactive capacity.
- Ollama runs locally with no authentication — acceptable for local development only.

---

**Users:** Mark (primary). Claude AI agents dispatching to other models. Future: teams needing multi-model AI orchestration.

## 28. Performance / Resource

| Metric | Target | Notes |
|--------|--------|-------|
| Routing resolution | <1ms | Simple dict lookup |
| Keychain retrieval | <50ms per key | Cached per session |
| Provider health check | <500ms per provider | Cached for 5 minutes |
| Budget calculation | <100ms | Query over audit trail JSONL |

---

**Users:** Mark (primary). Claude AI agents dispatching to other models. Future: teams needing multi-model AI orchestration.

## 29. Approval Record

| Reviewer | Date | Verdict | Notes |
|----------|------|---------|-------|
| Mark Hubers | 2026-03-22 | APPROVED | Session 84 — fill to 35 sections |

---

**Users:** Mark (primary). Claude AI agents dispatching to other models. Future: teams needing multi-model AI orchestration.

## 30. AI Review

Not yet performed. Scheduled for cross-spec review after all Rondo specs reach 35 sections.

---

**Users:** Mark (primary). Claude AI agents dispatching to other models. Future: teams needing multi-model AI orchestration.

## 31. AI Went Wrong

Not yet populated. Will be filled during first build sprint implementing multi-account.

---

**Users:** Mark (primary). Claude AI agents dispatching to other models. Future: teams needing multi-model AI orchestration.

## 32. AI Assumptions

Not yet populated. Will capture model assumptions made during build.

---

**Users:** Mark (primary). Claude AI agents dispatching to other models. Future: teams needing multi-model AI orchestration.

## 33. AI Cost

Not yet populated. Will track token/cost data from build sprints referencing this spec.

---

**Users:** Mark (primary). Claude AI agents dispatching to other models. Future: teams needing multi-model AI orchestration.

## 34. Notes

- Session 83 proved 3 providers live (Gemini 133ms, OpenAI 524ms, Claude 238ms). This
  validates the multi-provider architecture. Multi-account extends it to multiple accounts
  of the same provider.
- The `never_fallback_to_interactive = true` rule is the single most important config line
  in this spec. It must be enforced at the adapter selection layer, not at the config layer.

---

**Users:** Mark (primary). Claude AI agents dispatching to other models. Future: teams needing multi-model AI orchestration.

## 35. Change History

| Version | Date | What Changed |
|---------|------|-------------|
| 0.1 | 2026-03-20 | Initial addendum. 10 requirements. Multi-account architecture. |
| 0.2 | 2026-03-22 | Filled to 35 sections. Added CORE-STD-012, CORE-STD-013, CORE-IFS-005 refs. Approval (Mark, Session 84). |
