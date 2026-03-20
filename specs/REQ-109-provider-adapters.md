# REQ-109: Provider Adapters & Model Routing

*Talk to any AI. Route by task type. Track which models are best at what. One adapter per provider, one routing table for all.*

**Product:** Rondo
**Category:** REQ
**Created:** 2026-03-20 | **Updated:** 2026-03-20 | **Status:** DESIGNED
**Classification:** open
**Version:** 1.0
**Owner:** Mark G. Hubers
**Reviewed:** not-yet
**Depends on:** REQ-100 (Core), REQ-103 (Preflight), CORE-ADR-001 (Service Architecture), CORE-IFS-001 (Integration Contract)
**Used by:** REQ-101 (Automation — multi-account), IFS-101 (Caliber Integration), IFS-102 (OB Integration)
**Evidence:** Session 83 — 3 providers tested live (Gemini 45 models/133ms, OpenAI 129 models/524ms, Claude 9 models/238ms)

---

## 1. Purpose & Scope

**What this spec does:** Defines how Rondo dispatches to multiple AI providers through a common adapter interface. Rondo is the ONLY component that knows about specific AI providers (CORE-ADR-001). This spec defines the adapter pattern, model routing table, credential management, provider health monitoring, and affinity tracking (which models are best at which tasks).

---

## 3. Requirements

### Provider Adapter Interface

| # | Requirement | Priority | Verified By |
|---|------------|----------|-------------|
| 1 | `ProviderAdapter` abstract base class with: `dispatch(prompt, model, config) → DispatchResult`, `health() → bool`, `models() → list[str]` | MUST | Interface test |
| 2 | One adapter class per provider: `ClaudeCLIAdapter`, `ClaudeAPIAdapter`, `GeminiAdapter`, `OpenAIAdapter`, `OllamaAdapter`, `ContainerAdapter` | MUST | Adapter test |
| 3 | Adding a new provider = implement one adapter class. NO changes to OB, Caliber, ACE, or any other code. | MUST | Isolation test |
| 4 | All adapters return the same `DispatchResult` format regardless of provider (model-agnostic output) | MUST | Format test |
| 5 | Adapter config via TOML: `[providers.<name>] type, api_key_env, endpoint, default_model` | MUST | Config test |

### Credential Management

| # | Requirement | Priority | Verified By |
|---|------------|----------|-------------|
| 6 | API keys stored in macOS Keychain (`security` command). Service name pattern: `ace2-<provider>` | MUST | Keychain test |
| 7 | Keys retrieved at dispatch time via `ai-keys.py get <provider>` or direct Keychain query | MUST | Retrieval test |
| 8 | Keys NEVER in config files, env files, or git. Keychain only. (CORE-STD-008) | MUST | Security test |
| 9 | Multiple accounts for same provider supported (different Keychain entries): `ace2-claude-api` + `ace2-claude-batch` | MUST | Multi-account test |
| 10 | `ai-keys.py status` shows all configured providers with masked keys | MUST | Status test |
| 11 | `ai-keys.py test` calls each provider's health endpoint, shows models + latency | MUST | Health test |

### Model Routing

| # | Requirement | Priority | Verified By |
|---|------------|----------|-------------|
| 12 | Routing table maps task type → provider + model: `build → claude-api/sonnet`, `review_forward → gemini/flash` | MUST | Routing test |
| 13 | Default routing defined in config. Override per-dispatch via OAPayload `runtime.model` field. | MUST | Override test |
| 14 | Each provider has 3 model tiers: `default_model` (balanced), `best_model` (quality), `cheap_model` (cost) | SHOULD | Tier test |
| 15 | Routing fallback: if preferred provider is down, use fallback provider (configurable) | MUST | Fallback test |
| 16 | NEVER fall back to Mark's interactive account for batch work (REQ-101 addendum rule) | MUST | Protect test |

### Provider Health

| # | Requirement | Priority | Verified By |
|---|------------|----------|-------------|
| 17 | Preflight (REQ-103) checks ALL configured providers: key present + API reachable | MUST | Preflight test |
| 18 | Provider health cached for 5 minutes (don't re-check on every dispatch) | SHOULD | Cache test |
| 19 | Provider down → log WARNING, use fallback. Provider stays "down" until next health check. | MUST | Down test |
| 20 | `rondo providers` CLI: show all providers with health status, model count, latency | SHOULD | CLI test |

### Affinity Tracking (learn which model is best)

| # | Requirement | Priority | Verified By |
|---|------------|----------|-------------|
| 21 | Track per-model, per-task-type success rate: "Claude Opus succeeds 95% on reverse review, Gemini Flash succeeds 88%" | SHOULD | Tracking test |
| 22 | Track per-model cost efficiency: cost per successful task (not just cost per dispatch) | SHOULD | Cost test |
| 23 | Affinity suggestions: after 50+ dispatches per model-task pair, suggest optimal routing | SHOULD | Suggestion test |
| 24 | Manual override always wins: Mark sets routing, affinity is advisory only | MUST | Override test |
| 25 | CORE-STD-011 integration: routing decisions are guesses → track accuracy over time | SHOULD | Correction test |

---

## 4. Architecture / Design

```
OAPayload arrives at Rondo
        │
   ┌────┴────┐
   │ Router  │ ← checks task_type → routing table → selects provider + model
   └────┬────┘
        │
   ┌────┴──────────────────────────────────────┐
   │           Provider Adapters                │
   │                                            │
   │  ┌──────────┐  ┌──────────┐  ┌──────────┐ │
   │  │ Claude   │  │ Gemini   │  │ OpenAI   │ │
   │  │ CLI/API  │  │ REST     │  │ REST     │ │
   │  └────┬─────┘  └────┬─────┘  └────┬─────┘ │
   │       │              │              │       │
   │  ┌────┴─────┐  ┌────┴─────┐  ┌────┴─────┐ │
   │  │ Ollama   │  │Container │  │ Future   │ │
   │  │ REST     │  │ CLI      │  │ adapter  │ │
   │  └──────────┘  └──────────┘  └──────────┘ │
   └───────────────────┬───────────────────────┘
                       │
                  DispatchResult (same format regardless of provider)
                       │
                  OAResult (model-agnostic)
```

### Default Routing (Session 83 — proven task-model affinities)

| Task Type | Provider | Model | Why |
|-----------|----------|-------|-----|
| build | claude-api | claude-sonnet-4-6 | Best code generation quality |
| review_forward | gemini | gemini-2.5-flash | Fast pattern matching, cheap |
| review_reverse | claude-api | claude-opus-4-6 | Best adversarial reasoning |
| review_sideways | gemini | gemini-2.5-flash | Cross-file consistency |
| fix | claude-api | claude-sonnet-4-6 | Code gen quality for fixes |
| overnight_build | claude-batch | claude-sonnet-4-6 | Separate rate limit pool |
| overnight_review | gemini | gemini-2.5-flash | Cheap for high-volume batch |
| cheap_batch | gemini | gemini-2.0-flash | Lowest cost for low-stakes |
| spec_writing | claude-api | claude-opus-4-6 | Best reasoning for specs |
| contradiction_check | gemini | gemini-2.5-pro | Rule analysis across large rulesets |

---

## 5. Data Model

### DispatchResult (returned by every adapter)

| Field | Type | Description |
|-------|------|-------------|
| `status` | str | done/partial/error/timeout |
| `output` | str | AI response text |
| `parsed_result` | dict or None | Parsed JSON from response |
| `model_used` | str | Actual model that ran (may differ from requested) |
| `provider` | str | Which adapter dispatched (gemini/claude-api/openai/ollama) |
| `input_tokens` | int | Tokens sent |
| `output_tokens` | int | Tokens generated |
| `cost_usd` | float | Cost of this dispatch |
| `duration_ms` | int | Wall-clock time |
| `error_code` | str or None | ERR_* code if failed |

### Provider Config (TOML)

```toml
[providers.<name>]
type = "rest" | "claude-cli"
api_key_env = "KEYCHAIN_SERVICE_NAME"
endpoint = "https://..."           # REST providers only
default_model = "model-name"
best_model = "model-name"
cheap_model = "model-name"
budget_monthly_usd = 100.00
```

### Routing Table (TOML)

```toml
[routing]
build = "claude-api"
review_forward = "gemini"
overnight_build = "claude-batch"
```

---

## 6. Data Boundary

**What this produces:**

| Output | Format | Consumer |
|--------|--------|----------|
| DispatchResult | Python dataclass / JSON | Rondo core, OAResult builder |
| Provider health status | JSON | Preflight (REQ-103), `rondo providers` CLI |
| Affinity data | DB rows (from dispatch audit trail) | Routing suggestions |
| Cost per provider | Aggregated from DispatchResult | Notifications (REQ-105), morning report |

**What this consumes:**

| Input | Format | Producer |
|-------|--------|----------|
| API keys | macOS Keychain entries | `ai-keys.py set` |
| Routing config | TOML | `.rondo/config.toml` |
| OAPayload | JSON | OB or direct caller |
| Provider API responses | JSON (provider-specific) | AI provider REST APIs |

---

## 10. Rules & Constraints

1. **One adapter per provider.** Adding Mistral = one new class. Nothing else changes. Violation ID: `REQ109-ONE-ADAPTER`
2. **Keychain only for keys.** No .env files, no config files, no git. macOS Keychain or platform equivalent. Violation ID: `REQ109-KEYCHAIN-ONLY`
3. **Never fall back to interactive.** Batch rate-limited → use fallback provider or wait. Never touch Mark's account. Violation ID: `REQ109-PROTECT-INTERACTIVE`
4. **Affinity is advisory.** Manual routing config wins over learned affinity. Always. Violation ID: `REQ109-MANUAL-WINS`
5. **Same DispatchResult from every adapter.** OB/Caliber never know which provider ran. Model-agnostic output. Violation ID: `REQ109-AGNOSTIC-OUTPUT`

---

## 17. Success Criteria

| # | Criterion | How to Verify |
|---|-----------|---------------|
| 1 | `ai-keys.py test` shows 3+ providers live with models + latency | Provider test |
| 2 | Same OAPayload dispatched to Claude and Gemini → both return valid DispatchResult | Cross-provider test |
| 3 | Provider down → fallback fires, dispatch succeeds on alternate provider | Fallback test |
| 4 | After 50+ dispatches → affinity suggestions match observed performance | Affinity test |
| 5 | New provider added with zero changes to OB/Caliber/ACE | Isolation test |

---

## 35. Change History

| Version | Date | What Changed |
|---------|------|-------------|
| 1.0 | 2026-03-20 | Initial. Provider adapter interface, credential management, model routing, affinity tracking. 25 requirements. Session 83: 3 providers proven live. |
