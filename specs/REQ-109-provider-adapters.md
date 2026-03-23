# REQ-109: Provider Adapters & Model Routing

*Talk to any AI. Route by task type. Track which models are best at what. One adapter per provider, one routing table for all.*

**Product:** Rondo
**Category:** REQ
**Created:** 2026-03-20 | **Updated:** 2026-03-22 | **Status:** DESIGNED
**Classification:** open
**Version:** 1.1
**Owner:** Mark G. Hubers
**Reviewed:** not-yet
**Depends on:** REQ-100 (Core), REQ-103 (Preflight), CORE-ADR-001 (Service Architecture), CORE-IFS-001 (Integration Contract)
**Used by:** REQ-101 (Automation — multi-account), IFS-101 (Caliber Integration), IFS-102 (OB Integration)
**Evidence:** Session 83 — 3 providers tested live (Gemini 45 models/133ms, OpenAI 129 models/524ms, Claude 9 models/238ms)
**References:** CORE-STD-012 (Requirement Readiness), CORE-STD-013 (TrackerData), CORE-IFS-005 (MCP Standard)

---

## 1. Purpose & Scope

**What this spec does:** Defines how Rondo dispatches to multiple AI providers through a common adapter interface. Rondo is the ONLY component that knows about specific AI providers (CORE-ADR-001). This spec defines the adapter pattern, model routing table, credential management, provider health monitoring, and affinity tracking (which models are best at which tasks).

**IN scope:**
- ProviderAdapter abstract interface
- Concrete adapter implementations (Claude CLI, Claude API, Gemini, OpenAI, Ollama, Container)
- Credential management (macOS Keychain)
- Model routing table (task type → provider + model)
- Provider health monitoring
- Affinity tracking (learned model-task performance)

**OUT of scope:**
- AI model internals (prompt engineering, response parsing)
- Multi-account capacity management (REQ-101 addendum owns that)
- OB or Caliber integration details (IFS-101, IFS-102 own those)

**Users:** Mark (primary). Claude AI agents dispatching to other models. Future: teams needing multi-model AI orchestration, batch processing, cost optimization across AI providers.

---

## 2. The Problem

Rondo dispatches to multiple AI providers (Claude, Gemini, OpenAI, Ollama). Each provider
has a different API, authentication method, model naming convention, and response format.
Without an adapter layer, provider-specific code would leak into the dispatch engine, OB,
Caliber, and every consumer. Adding a new provider would require changes everywhere.
The adapter pattern isolates provider specifics: one class per provider, one interface for all.

---

## 3. Requirements

### Provider Adapter Interface


*All requirements use MUST/SHOULD priority per CORE-STD-012.*

| ID | Requirement | Priority | Verified By |
|----|-------------|----------|-------------|
| 001 | `ProviderAdapter` abstract base class with: `dispatch(prompt, model, config) → DispatchResult`, `health() → bool`, `models() → list[str]` | MUST | Interface test |
| 002 | One adapter class per provider: `ClaudeCLIAdapter`, `ClaudeAPIAdapter`, `GeminiAdapter`, `OpenAIAdapter`, `OllamaAdapter`, `ContainerAdapter` | MUST | Adapter test |
| 003 | Adding a new provider = implement one adapter class. NO changes to OB, Caliber, ACE, or any other code. | MUST | Isolation test |
| 004 | All adapters return the same `DispatchResult` format regardless of provider (model-agnostic output) | MUST | Format test |
| 005 | Adapter config via TOML: `[providers.<name>] type, api_key_env, endpoint, default_model` | MUST | Config test |


### Credential Management

| ID | Requirement | Priority | Verified By |
|----|-------------|----------|-------------|
| 006 | API keys stored in macOS Keychain (`security` command). Service name pattern: `ace2-<provider>` | MUST | Keychain test |
| 007 | Keys retrieved at dispatch time via `ai-keys.py get <provider>` or direct Keychain query | MUST | Retrieval test |
| 008 | Keys NEVER in config files, env files, or git. Keychain only. (CORE-STD-008) | MUST | Security test |
| 009 | Multiple accounts for same provider supported (different Keychain entries): `ace2-claude-api` + `ace2-claude-batch` | MUST | Multi-account test |
| 010 | `ai-keys.py status` shows all configured providers with masked keys | MUST | Status test |
| 011 | `ai-keys.py test` calls each provider's health endpoint, shows models + latency | MUST | Health test |


### Model Routing

| ID | Requirement | Priority | Verified By |
|----|-------------|----------|-------------|
| 012 | Routing table maps task type → provider + model: `build → claude-api/sonnet`, `review_forward → gemini/flash` | MUST | Routing test |
| 013 | Default routing defined in config. Override per-dispatch via OAPayload `runtime.model` field. | MUST | Override test |
| 014 | Each provider has 3 model tiers: `default_model` (balanced), `best_model` (quality), `cheap_model` (cost) | SHOULD | Tier test |
| 015 | Routing fallback: if preferred provider is down, use fallback provider (configurable) | MUST | Fallback test |
| 016 | NEVER fall back to Mark's interactive account for batch work (REQ-101 addendum rule) | MUST | Protect test |


### Provider Health

| ID | Requirement | Priority | Verified By |
|----|-------------|----------|-------------|
| 017 | Preflight (REQ-103) checks ALL configured providers: key present + API reachable | MUST | Preflight test |
| 018 | Provider health cached for 5 minutes (don't re-check on every dispatch) | SHOULD | Cache test |
| 019 | Provider down → log WARNING, use fallback. Provider stays "down" until next health check. | MUST | Down test |
| 020 | `rondo providers` CLI: show all providers with health status, model count, latency | SHOULD | CLI test |


### Affinity Tracking (learn which model is best)

| ID | Requirement | Priority | Verified By |
|----|-------------|----------|-------------|
| 021 | Track per-model, per-task-type success rate: "Claude Opus succeeds 95% on reverse review, Gemini Flash succeeds 88%" | SHOULD | Tracking test |
| 022 | Track per-model cost efficiency: cost per successful task (not just cost per dispatch) | SHOULD | Cost test |
| 023 | Affinity suggestions: after 50+ dispatches per model-task pair, suggest optimal routing | SHOULD | Suggestion test |
| 024 | Manual override always wins: Mark sets routing, affinity is advisory only | MUST | Override test |
| 025 | CORE-STD-011 integration: routing decisions are guesses → track accuracy over time | SHOULD | Correction test |


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

## 7. MCP / API Interface

Future: an MCP tool per CORE-IFS-005 could expose provider health and routing table,
enabling AI agents to query available models and their status before requesting dispatch.
Example: "Which providers are healthy?" → returns provider list with health + model count.

---

## 8. States & Modes

Per-provider states:

| State | Condition | Behavior |
|-------|-----------|----------|
| **healthy** | Health check passed, API key present | Normal dispatch |
| **degraded** | Slow responses or partial failures | Dispatch with warning |
| **down** | Health check failed or key missing | Use fallback provider |
| **unconfigured** | Not in config file | Not available for dispatch |

State transitions happen on health check (every 5 minutes or on-demand).

**State Machine Type:** BIDIRECTIONAL
**Rationale:** Providers transition freely between healthy ↔ degraded ↔ down based on health check results. Recovery is automatic when health checks pass again. Unconfigured is a separate initial state.
**Rollback:** Automatic — health check recovery restores previous operational state.

---

## 9. Configuration

See section 5 (Provider Config TOML and Routing Table TOML) for the full schema.
COALESCE resolution: OAPayload.runtime.model → routing table → provider.default_model.

---

## 10. Rules & Constraints

1. **One adapter per provider.** Adding Mistral = one new class. Nothing else changes. Violation ID: `REQ109-ONE-ADAPTER`
2. **Keychain only for keys.** No .env files, no config files, no git. macOS Keychain or platform equivalent. Violation ID: `REQ109-KEYCHAIN-ONLY`
3. **Never fall back to interactive.** Batch rate-limited → use fallback provider or wait. Never touch Mark's account. Violation ID: `REQ109-PROTECT-INTERACTIVE`
4. **Affinity is advisory.** Manual routing config wins over learned affinity. Always. Violation ID: `REQ109-MANUAL-WINS`
5. **Same DispatchResult from every adapter.** OB/Caliber never know which provider ran. Model-agnostic output. Violation ID: `REQ109-AGNOSTIC-OUTPUT`

---

## 11. Quality Attributes

| Attribute | Target | Rationale |
|-----------|--------|-----------|
| Extensibility | New provider in <1 day of coding | Adapter pattern enables rapid expansion |
| Isolation | Zero OB/Caliber changes when adding provider | CORE-ADR-001 boundary |
| Reliability | Fallback provider within 1 dispatch attempt | Provider down → transparent failover |
| Security | Zero plaintext keys anywhere | Keychain-only credential management |

---

## 12. Shared Patterns

- **Adapter pattern:** Classic GoF pattern — common interface, per-implementation class.
  Used throughout industry for payment gateways, notification channels, storage backends.
- **COALESCE for routing:** OAPayload.runtime.model → config routing table → provider default.
  Same COALESCE pattern as config resolution (STD-109).
- **Health check with cache:** Check once, cache for TTL, re-check on failure. Same pattern
  as REQ-103 (preflight) rate limit caching.

---

## 13. Integration Points

| Integration | Spec | Direction | Contract |
|-------------|------|-----------|----------|
| Dispatch engine | REQ-100 | Internal | Router selects adapter, adapter returns DispatchResult |
| Preflight | REQ-103 | Internal | Per-provider health checks |
| Multi-account | REQ-101 addendum | Internal | Multiple adapter instances per provider |
| Caliber | IFS-101 | Indirect | Caliber requests model via Task.model, Rondo routes |
| OB | IFS-102 | Indirect | OB requests model via OAPayload.runtime.model |
| Audit trail | STD-113 | Outbound | Provider + model in every audit entry |

---

## 14. Standards Applied

| Standard | How Applied |
|----------|-------------|
| CORE-ADR-001 (Service Architecture) | Rondo is sole AI-aware component, adapters isolate providers |
| CORE-IFS-001 (Integration Contract) | DispatchResult is the universal contract across adapters |
| CORE-STD-008 (Secrets) | API keys in Keychain only |
| CORE-STD-011 (Self-Correction) | Affinity tracking is self-correction — learn optimal routing |
| CORE-STD-012 (Requirement Readiness) | Each requirement tagged with readiness state |
| CORE-STD-013 (TrackerData) | Provider events logged as trackerdata entries |
| CORE-IFS-005 (MCP Standard) | Future MCP tool for provider health queries |

---

## 15. Self-Correction

- After 50+ dispatches per model-task pair, affinity suggestions compare observed performance
  against the routing table. If a different model consistently outperforms the configured
  one, the morning report suggests a routing change.
- If a provider's health check fails 3 times consecutively, it's marked "down" and excluded
  from the routing table until manual re-enablement or successful health check.
- Cost tracking per provider feeds back into REQ-106 (trend alerting) — if a provider's
  cost per token increases, the trend alert fires and suggests switching to a cheaper model.

---

## 16. Assumptions

| # | Assumption | If Wrong |
|---|-----------|----------|
| A1 | macOS Keychain is available on all target platforms | Need platform-specific credential store |
| A2 | Provider REST APIs are stable across versions | Need version pinning in adapter implementations |
| A3 | DispatchResult can capture all provider response formats | May need provider-specific extension fields |
| A4 | 50 dispatches is enough for meaningful affinity tracking | Low-volume task types may need longer |
| A5 | Provider latency is stable enough for health caching (5 min TTL) | Rapid degradation may be missed between checks |

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

## 18. Build Notes / Estimate

| Item | Estimate |
|------|----------|
| ProviderAdapter ABC + DispatchResult | 0.5 day |
| ClaudeCLIAdapter + ClaudeAPIAdapter | 2 days |
| GeminiAdapter | 1 day |
| OpenAIAdapter | 1 day |
| OllamaAdapter | 0.5 day |
| ContainerAdapter | 1 day |
| Router + routing table | 1 day |
| Keychain integration (ai-keys.py) | 1 day |
| Health checking + caching | 0.5 day |
| Affinity tracking | 1.5 days |
| Tests | 2 days |
| Total | ~12 days |

---

## 19. Test Categories

| Category | What | Count (est.) |
|----------|------|-------------|
| Unit | Each adapter (mock provider API), router, health check | 18 |
| Integration | End-to-end dispatch through adapter to mock API | 6 |
| Credential | Keychain store/retrieve/mask/multi-account | 6 |
| Routing | Task type → provider resolution, fallback, override | 8 |
| Health | Health check, caching, down detection, recovery | 6 |
| Affinity | Score tracking, suggestion generation | 4 |

---

## 20. Failure Modes

| Failure | Impact | Mitigation |
|---------|--------|------------|
| Provider API changes format | Adapter returns bad DispatchResult | Version pinning + adapter-level parsing |
| Keychain unavailable | No API keys | Preflight catches before dispatch |
| All providers down | No dispatch possible | Ollama (local) as last resort |
| Routing table misconfigured | Wrong provider for task type | Config validation at startup |
| Affinity data misleading | Bad routing suggestion | Manual override always wins |
| Claude Code CLI flags change | `--output-format stream-json` or other flags removed/renamed | REQ-103 smoke test catches before dispatch. Version compatibility matrix tracks known-good flag sets. |
| Claude Code CLI update breaks overnight | Silent failures in batch runs | REQ-103 preflight re-validates on version change (req 020). Detailed debug logging (req 024). |

---

## 21. Dependencies + Used By

| Depends On | Why |
|------------|-----|
| REQ-100 | Core dispatch framework (defines Task, DispatchResult interface) |
| REQ-103 | Preflight checks provider health |
| CORE-ADR-001 | Service architecture — Rondo is sole AI-aware component |
| CORE-IFS-001 | Universal contract patterns |
| CORE-STD-008 | Secrets management (Keychain) |

| Used By | Why |
|---------|-----|
| REQ-101 | Multi-account routing for overnight |
| IFS-101 | Caliber tasks routed through adapters |
| IFS-102 | OB tasks routed through adapters |
| REQ-106 | Per-model trend data comes from adapter dispatch results |
| REQ-107 | Per-model flakiness tracking |

---

## 22. Decisions

| # | Decision | Date | Why |
|---|----------|------|-----|
| D1 | Abstract base class (not protocol/interface) | 2026-03-20 | ABCs enforce implementation at class creation time |
| D2 | macOS Keychain for all credentials | 2026-03-20 | OS-level encryption, no plaintext anywhere |
| D3 | Affinity is advisory, manual wins | 2026-03-20 | Mark controls routing. AI suggests, Mark decides. |
| D4 | 6 adapter types in v1 | 2026-03-20 | Claude CLI/API, Gemini, OpenAI, Ollama, Container covers all known needs |
| D5 | Session 83 default routing table | 2026-03-20 | Proven live — 3 providers tested with real API calls |

---

## 23. Open Questions

| # | Question | Impact | Status |
|---|----------|--------|--------|
| Q1 | Should adapters support streaming responses? | Affects progress reporting for long dispatches | OPEN |
| Q2 | Should affinity tracking influence automatic routing (not just suggestions)? | Automation vs control | OPEN — advisory only for now |
| Q3 | Should there be a provider "marketplace" for sharing adapter configs? | Multi-user, future scope | OPEN — not in v1 |
| Q4 | Should ContainerAdapter support Apple Containers natively? | macOS-specific optimization | OPEN — Docker first |

---

## 24. Glossary

| Term | Definition |
|------|-----------|
| **ProviderAdapter** | Abstract base class for AI provider integration |
| **DispatchResult** | Standardized result format returned by all adapters |
| **Routing table** | Config mapping task types to provider + model pairs |
| **Affinity** | Learned performance profile of model-task combinations |
| **Health check** | Quick API probe to verify provider availability |

---

## 25. Risk / Criticality

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Provider API breaking change | Medium | Adapter fails | Pin versions, test regularly |
| Keychain API changes in macOS update | Low | Credential retrieval fails | Abstraction layer for credential store |
| Model naming inconsistency across providers | Medium | Routing confusion | Canonical model names in config, adapter translates |
| Single-point-of-failure (one provider) | Medium | Batch blocked | Fallback provider always configured |

---

## 26. External Scan

Session 83 proved 3 providers live: Gemini (45 models, 133ms latency), OpenAI (129 models,
524ms), Claude (9 models, 238ms). Industry pattern: LiteLLM provides a universal API for
100+ LLM providers. Rondo's adapter approach is simpler (6 providers, Rondo-specific) but
follows the same principle. The key difference: Rondo tracks affinity and routing — LiteLLM
does not.

---

## 27. Security Considerations

- All API keys in macOS Keychain — never in files, env, or git. CORE-STD-008 enforced.
- `ai-keys.py status` shows masked keys only (last 4 chars).
- Provider health checks use minimal API calls (list models, not dispatch).
- Multi-account isolation prevents batch key from accessing interactive capacity.
- HTTPS for all remote provider APIs (TLS enforced by provider SDKs).

---

## 28. Performance / Resource

| Metric | Target | Notes |
|--------|--------|-------|
| Adapter dispatch overhead | <100ms beyond API call | Prompt assembly + result parsing |
| Health check | <500ms per provider | Cached for 5 minutes |
| Keychain retrieval | <50ms | Cached per session |
| Routing resolution | <1ms | Dict lookup |
| Memory per adapter | <10MB | Stateless — no buffering between dispatches |

---

## 29. Approval Record

| Reviewer | Date | Verdict | Notes |
|----------|------|---------|-------|
| Mark Hubers | 2026-03-22 | APPROVED | Session 84 — fill to 35 sections |

---

## 30. AI Review

Not yet performed. Scheduled for cross-spec review after all Rondo specs reach 35 sections.

---

## 31. AI Went Wrong

Not yet populated. Will be filled during first build sprint implementing provider adapters.

---

## 32. AI Assumptions

Not yet populated. Will capture model assumptions made during build.

---

## 33. AI Cost

Not yet populated. Will track token/cost data from build sprints referencing this spec.

---

## 34. Notes

- Session 83 live testing proved the multi-provider architecture works. Three providers
  responded within 524ms worst case. This validates the adapter approach before building
  the production implementation.
- The ContainerAdapter is for running AI inside Apple Containers or Docker — dispatch the
  prompt to a containerized model rather than a cloud API. This enables offline operation
  and maximum isolation.

---

### Feature Maturity

| Feature | Maturity | Evidence | Retest |
|---------|----------|----------|--------|
| Provider adapter interface | SPIKED | Spike prototyped Claude adapter via claude -p | Phase 1 build |
| Claude Code adapter | SPIKED | Spike proved subprocess dispatch works | After Claude CLI changes |
| Multi-model routing | THEORY | Specced for opus/sonnet/haiku per task | Phase 1 build |
| Alternative provider support | THEORY | Specced for future non-Claude providers | Phase 3 build |


## 35. Change History

| Version | Date | What Changed |
|---------|------|-------------|
| 1.0 | 2026-03-20 | Initial. Provider adapter interface, credential management, model routing, affinity tracking. 25 requirements. Session 83: 3 providers proven live. |
| 1.1 | 2026-03-22 | Filled to 35 sections. Added CORE-STD-012, CORE-STD-013, CORE-IFS-005 refs. Approval (Mark, Session 84). |
