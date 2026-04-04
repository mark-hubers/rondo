# Rondo-REQ-109: Provider Adapters & Model Routing

*Talk to any AI. Route by task type. Track which models are best at what. One adapter per provider, one routing table for all.*

**Product:** Rondo
**Category:** REQ
**Created:** 2026-03-20 | **Updated:** 2026-04-03 | **Status:** DESIGNED
**Classification:** open
**Version:** 1.7
**Owner:** Mark G. Hubers
**Reviewed:** not-yet
**Depends on:** Rondo-REQ-100 (Core), Rondo-REQ-103 (Preflight), CORE-ADR-001 (Service Architecture), CORE-IFS-001 (Integration Contract), Rondo-REQ-110, Rondo-IFS-101, Rondo-IFS-102, CORE-STD-008
**Used by:** Rondo-REQ-110 (Multi-Account), Rondo-REQ-101 (Automation), Rondo-IFS-101 (Caliber Integration), Rondo-IFS-102 (OB Integration)
**Evidence:** Session 83 — 3 providers tested live (Gemini 45 models/133ms, OpenAI 129 models/524ms, Claude 9 models/238ms)
**References:** CORE-STD-012 (Requirement Readiness), CORE-STD-013 (TrackerData), CORE-STD-021 (MCP Standard)

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
- Multi-account capacity management (Rondo-REQ-110 owns that)
- OB or Caliber integration details (Rondo-IFS-101, Rondo-IFS-102 own those)

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
| 002 | **3 adapter classes** (not per-provider): `ChatCompletionsAdapter` (OpenAI + Grok + Mistral — same API), `GeminiAdapter` (unique API), `AnthropicAPIAdapter` (unique API). Plus existing `OllamaAdapter` for local models. Claude subprocess dispatch uses `dispatch_task()` directly. | MUST | Adapter test |
| 003 | Adding a new provider = implement one adapter class OR configure an existing one (ChatCompletions providers only need config). NO changes to OB, Caliber, ACE. | MUST | Isolation test |
| 004 | All adapters return the same `TaskResult` format regardless of provider (model-agnostic output) | MUST | Format test |
| 005 | Adapter config via TOML `[providers.<name>]` with: `enabled`, `base_url`, `model`, `keychain_item`, `temperature`, `max_tokens`. Per-provider subtables. | MUST | Config test |

### Adapter Architecture (Session 94 — Cursor design review)

| ID | Requirement | Priority | Verified By |
|----|-------------|----------|-------------|
| 030 | Adapters MUST live in `rondo/src/rondo/adapters/` directory: `chat_completions.py`, `gemini.py`, `anthropic_api.py`, `ollama.py`. `providers.py` stays small (routing + interface only). | MUST | Structure test |
| 031 | `ChatCompletionsAdapter` handles OpenAI, Grok, Mistral via config (different `base_url`, same API shape). One class, three providers. | MUST | Multi-provider test |
| 032 | Provider routing via `provider:model` prefix: `openai:gpt-4.1`, `gemini:flash`, `local:llama3.1:8b`. `parse_model()` splits on first `:`. No prefix → Claude. | MUST | Routing test |
| 033 | `rondo_multi_review` MCP tool: dispatch same prompt to N providers, return per-provider findings + merged findings + cost/latency stats. Replaces `ai-review --all-providers`. | SHOULD | MCP test |
| 034 | API keys loaded from macOS Keychain via `keychain_item` field in config. Fallback to env var. Never in files or git. | MUST | Auth test |


### Shared Finalization Pipeline (Session 94 — split-brain fix)

| ID | Requirement | Priority | Verified By |
|----|-------------|----------|-------------|
| 026 | ALL provider dispatch results MUST pass through the shared finalization pipeline (`_finalize_dispatch`): audit OUTCOME, sanitize, spool, history, metrics. No provider may skip any stage. | MUST | Pipeline test |
| 027 | Claude dispatch uses `dispatch_task()` → `_finalize_dispatch()` (proven path, 1168 tests). Non-Claude providers use `ProviderAdapter.dispatch()` → `_finalize_dispatch()`. Two transports, one finalization. | MUST | Path test |
| 028 | `recommend_model(task_type)` MUST read from TOML config (`[routing.task_models]`), not a hardcoded dictionary. Manual config always wins over learned affinity (req 024). | MUST | Config test |
| 029 | Anti-pattern guard: if a new dispatch path is added that bypasses `_finalize_dispatch`, tests MUST fail. The pipeline is mandatory, not optional. | MUST | Guard test |


### Credential Management (updated Session 94 — KeyBackend interface)

| ID | Requirement | Priority | Verified By |
|----|-------------|----------|-------------|
| 006 | API keys stored in macOS Keychain (`security` command). Service name: `ace.ai-key.<provider>` (matches ai-keys.py). Account: `markhubers`. | MUST | Keychain test |
| 007 | Keys retrieved via `adapters/auth.py load_api_key(provider)` — shared by all adapters AND ai_review.py. Single source of truth. | MUST | Retrieval test |
| 008 | Keys NEVER in config files, env files, or git. Only references (vault name, item name) in config.toml. (CORE-STD-008) | MUST | Security test |
| 009 | Multiple accounts for same provider supported (different Keychain entries): `ace.ai-key.claude-api` + `ace.ai-key.claude-batch` | MUST | Multi-account test |
| 010 | `ai-keys.py status` shows all configured providers with masked keys | MUST | Status test |
| 011 | `ai-keys.py test` calls each provider's health endpoint, shows models + latency | MUST | Health test |
| 035 | `load_api_key(provider)` MUST follow precedence: env var → macOS Keychain → 1Password CLI (if configured). First non-empty value wins. | MUST | Precedence test |
| 036 | `KeyBackend` interface: `get_key(provider) → str`. Implementations: `EnvBackend`, `KeychainBackend`, `OnePasswordBackend`. Backend selected via `[auth] backend = "auto"` in config.toml. | SHOULD | Interface test |
| 037 | `auto` mode tries backends in order: env → keychain → 1password. Stops at first success. | MUST | Auto test |
| 038 | 1Password integration: use `op read "op://vault/item/password"` CLI. Requires `op` binary on PATH. If not installed, skip silently. | SHOULD | 1P test |
| 039 | Config.toml `[auth]` section: `backend = "auto"`, `onepassword_vault = "AI Keys"`. Only metadata — NEVER secret values. | MUST | Config test |
| 040 | Keys MAY be cached per-process with 5-minute TTL. Cache invalidated on error (key might have rotated). | SHOULD | Cache test |


### Provider Tiers (Session 96 — 4 AI body consensus)

| ID | Requirement | Priority | Verified By |
|----|-------------|----------|-------------|
| 041 | Each provider config MUST define 3 model tiers: `cheap_model` (fast/lowest cost), `default_model` (balanced), `best_model` (highest quality). Exact model names per provider. | MUST | Config test |
| 042 | Tier resolution: `provider:tier` syntax resolves via config lookup. `gemini:high` → `[providers.gemini].best_model`. `gemini:low` → `cheap_model`. `gemini:default` or `gemini:` → `default_model`. | MUST | Tier test |
| 043 | Exact model name ALWAYS beats tier. `gemini:flash` → literal model "flash", not a tier lookup. Precedence: exact model > tier > default. | MUST | Precedence test |
| 044 | Tier names are fixed: `high`, `default`, `low`. No custom tier names in v1 (simplicity — 4 AI bodies agreed 3 tiers is right starting point). | MUST | Validation test |
| 045 | If a provider has fewer than 3 distinct models, tiers MAY point to the same model (e.g., Grok: `best_model = "grok-3"`, `default_model = "grok-3"`). | SHOULD | Config test |

### ai-review script (`scripts/ai_review.py`) — Rondo SSOT for tier models

Multi-AI spec review (`ai-review --tier best|standard|fast`) uses the **same** three fields as Rondo: `best_model`, `default_model`, `cheap_model` per `[providers.<name>]` in `~/.rondo/config.toml`. Built-in model names in `TIERS_BUILTIN` apply only when config is missing, a provider is disabled, or merge fails.

| ID | Requirement | Priority | Verified By |
|----|-------------|----------|-------------|
| 064 | Module `rondo/review_tiers.py` SHALL provide `merge_ai_review_tiers(builtin)` returning a deep copy of `builtin` with per-provider models overridden from config. Mapping: `--tier best` → `best_model`, `standard` → `default_model`, `fast` → `cheap_model`. | MUST | `test_review_tiers.py` |
| 065 | Optional env `RONDO_CONFIG_PATH` SHALL select the TOML file (for tests); default `~/.rondo/config.toml`. | SHOULD | `test_review_tiers.py` |
| 066 | ai-review provider key `claude` SHALL read from `[providers.anthropic]` (same as Rondo routing). Keys `openai`, `gemini`, `mistral`, `grok` read from matching `[providers.*]` sections. | MUST | `test_review_tiers.py` |
| 067 | `scripts/ai_review.py` SHALL call `merge_ai_review_tiers(TIERS_BUILTIN)` at import when `rondo/src` is on `sys.path` (repo checkout); on any failure, use `TIERS_BUILTIN` only. | MUST | Import smoke |

### Cloud Dispatch (Session 96 — `--cloud` flag)

| ID | Requirement | Priority | Verified By |
|----|-------------|----------|-------------|
| 046 | `--cloud` flag (CLI) and `cloud=True` (MCP/Python): dispatch same prompt to N cloud providers in parallel, return per-provider results + merged findings. | MUST | Cloud test |
| 047 | `[cloud] default_count = 2` in config.toml: how many providers `--cloud` uses by default. User override: `--cloud 3` or `--cloud 1`. | MUST | Count test |
| 048 | `[cloud] max_count = 4`: hard cap on parallel cloud dispatches. Prevents accidental cost spikes. | MUST | Cap test |
| 049 | Cloud profiles in config: `[cloud.profiles.review]`, `[cloud.profiles.coding]`, `[cloud.profiles.research]`. Each has a `providers` list and `description`. | MUST | Profile test |
| 050 | Profile selection: `--cloud review` uses review profile. `--cloud` with no profile uses all enabled providers. Future: auto-detect task type from prompt keywords. | MUST | Selection test |
| 051 | Cloud tier: `--cloud high` dispatches to all selected providers at `best_model` tier. `--cloud low` uses `cheap_model`. Default: `default_model`. Combinable: `--cloud high 3` = 3 providers at best tier. | MUST | Tier flag test |
| 052 | Cloud providers SHOULD be dispatched concurrently where possible. v1 implementation is sequential (acceptable for 2-3 providers). Future: `asyncio` or thread pool when provider count exceeds 3. Results collected and merged after all complete or timeout. | SHOULD | Parallel test |

### Cloud Cost Controls (all 4 AI bodies flagged as critical)

| ID | Requirement | Priority | Verified By |
|----|-------------|----------|-------------|
| 053 | `[cloud] max_cost_per_dispatch = 0.50`: abort cloud dispatch if estimated cost exceeds cap. Estimate based on prompt token count × provider pricing. | MUST | Cost cap test |
| 054 | Per-provider monthly budget: `[providers.<name>] budget_monthly_usd = 50.00`. Track cumulative spend. Warn at 80%, block at 100%. | SHOULD | Budget test |
| 055 | Cost estimate shown before dispatch when `dry_run=True`. Shows per-provider estimated cost + total. | MUST | Estimate test |
| 056 | Cloud dispatch result includes `total_cost_usd` and per-provider `cost_usd` in response. | MUST | Cost report test |

### Cloud Failure Policy (Cursor identified as gap)

| ID | Requirement | Priority | Verified By |
|----|-------------|----------|-------------|
| 057 | Default failure policy: **partial result**. If 1 of N providers fails, return results from providers that succeeded + error detail for failed provider. Do NOT fail the whole dispatch. | MUST | Partial test |
| 058 | Failed provider marked in result with `status: "error"` and `error_code`. Successful providers have `status: "done"`. | MUST | Status test |
| 059 | If ALL providers fail, return `status: "error"` with per-provider error details. | MUST | All-fail test |
| 060 | Timeout per cloud provider: respect `timeout_sec` from dispatch config. Provider that exceeds timeout returns `status: "timeout"`, others continue. | MUST | Timeout test |

### Cloud Security (OpenAI + Gemini flagged)

| ID | Requirement | Priority | Verified By |
|----|-------------|----------|-------------|
| 061 | Data sensitivity flag per task: `sensitivity = "public" | "internal" | "private"`. `public` = any provider. `internal` = skip untrusted providers. `private` = local only (Ollama). | SHOULD | Sensitivity test |
| 062 | Provider trust level in config: `[providers.<name>] trust = "trusted" | "untrusted"`. `internal` tasks skip `untrusted` providers. | SHOULD | Trust test |
| 063 | Cloud dispatch MUST NOT send prompts containing file paths, API keys, or credential-like strings to untrusted providers. Sanitization before dispatch. | MUST | Sanitize test |

### E2E Test Modes (Session 97 — config-driven validation)

| ID | Requirement | Priority | Verified By |
|----|-------------|----------|-------------|
| 074 | `pytest -m cloud` runs real cloud dispatch tests (existing adapter tests). Skips automatically if API key not configured. Cost: ~$0.02. | MUST | Marker test |
| 075 | `pytest -m cloud_full` reads `~/.rondo/config.toml` `[providers]` and dispatches a minimal prompt to every enabled provider at every tier (cheap/default/best). Verifies each model ID is valid against the real API. Cost: ~$0.10-0.50 depending on provider count. | MUST | Config validation test |
| 076 | `cloud_full` MUST report per-provider, per-tier results as a table: provider, tier, model ID, status (PASS/FAIL/SKIP), latency, error if any. | MUST | Output test |
| 077 | `cloud_full` MUST also validate `_DEFAULT_TASK_MODELS` entries — every hardcoded model string must dispatch successfully. Catches stale model IDs (like `gemini:flash` → 404). | MUST | Default validation test |
| 078 | Both `cloud` and `cloud_full` are opt-in markers. Normal `pytest rondo/tests/` MUST NOT run cloud tests. | MUST | Isolation test |

### Health & UX Clarity (Session 97 — Cursor usability feedback)

| ID | Requirement | Priority | Verified By |
|----|-------------|----------|-------------|
| 079 | `rondo_health()` MUST separate live API status (`api_status`: GREEN/YELLOW/RED based on provider probes) from historical dispatch health (`dispatch_health`: based on success_rate). A user seeing "RED" when all providers are up is confusing. | MUST | Health output test |
| 080 | `rondo_multi_review` MUST reject empty or whitespace-only prompts with `ERR_INVALID_INPUT`. Do not dispatch empty prompts to cloud providers. | MUST | Empty prompt test |
| 081 | Dry-run output MUST include `prompt_length` (integer, actual byte count) alongside truncated `prompt_sent` (capped at 500 chars for display). Users must know how large the real prompt is. | MUST | Dry-run length test |

### `rondo review` CLI Command (Session 97 — top feature request)

| ID | Requirement | Priority | Verified By |
|----|-------------|----------|-------------|
| 082 | `rondo review <file>` reads a file and sends its contents to 2+ cloud providers for independent review. Returns per-provider findings. No round file needed. | MUST | CLI E2E test |
| 083 | Default providers come from `[cloud.profiles.review]` in config.toml. Override with `--providers gemini,grok,mistral`. | MUST | Config test |
| 084 | `--tier high\|default\|low` selects model tier per provider. Default: `default`. | SHOULD | Tier test |
| 085 | `--dry-run` shows the prompt that would be sent without dispatching. | MUST | Dry-run test |
| 086 | Output: per-provider section with findings. `--output json` for structured output. Default: human-readable text. | MUST | Output test |
| 087 | `rondo review` also available as MCP tool `rondo_review_file(path, providers, tier, dry_run)` for AI editor integration. | SHOULD | MCP test |

### Model Routing

| ID | Requirement | Priority | Verified By |
|----|-------------|----------|-------------|
| 012 | Routing table maps task type → provider + model: `build → claude-api/sonnet`, `review_forward → gemini/flash` | MUST | Routing test |
| 013 | Default routing defined in config. Override per-dispatch via OAPayload `runtime.model` field. | MUST | Override test |
| 014 | Each provider has 3 model tiers: `default_model` (balanced), `best_model` (quality), `cheap_model` (cost) | SHOULD | Tier test |
| 015 | Routing fallback: if preferred provider is down, use fallback provider (configurable) | MUST | Fallback test |
| 016 | NEVER fall back to Mark's interactive account for batch work (Rondo-REQ-110 rule) | MUST | Protect test |


### Provider Health

| ID | Requirement | Priority | Verified By |
|----|-------------|----------|-------------|
| 017 | Preflight (Rondo-REQ-103) checks ALL configured providers: key present + API reachable | MUST | Preflight test |
| 018 | Provider health cached for 5 minutes (don't re-check on every dispatch) | SHOULD | Cache test |
| 019 | Provider down → log WARNING, use fallback. Provider stays "down" until next health check. | MUST | Down test |
| 020 | `rondo providers` CLI: show all providers with health status, model count, latency | SHOULD | CLI test |

### Provider Health Strategy (Session 97 — Cursor deep review)

| ID | Requirement | Priority | Verified By |
|----|-------------|----------|-------------|
| 071 | `ChatCompletionsAdapter.health()` MUST use a **provider-appropriate** endpoint. OpenAI and Mistral expose `GET /v1/models`; Grok (xAI) may not. If `/models` is unavailable, fall back to TCP connect or HEAD request to `base_url`. Do NOT assume all ChatCompletions providers share OpenAI's endpoint layout. | MUST | Per-provider health test |
| 072 | `AnthropicAPIAdapter.health()` MUST verify network reachability, not just key presence. Acceptable methods: HEAD or GET to `base_url` (any non-timeout response proves connectivity), or TCP connect to host:443. Key-present-only does NOT satisfy req 017 ("API reachable"). | MUST | Anthropic health test |
| 073 | Provider health strategy MUST be documented per adapter: which endpoint is checked, what constitutes "healthy", what constitutes "down". This goes in the adapter's module docstring. | SHOULD | Docstring review |


### Error Handling & Resilience (Session 97 — Cursor deep review)

| ID | Requirement | Priority | Verified By |
|----|-------------|----------|-------------|
| 068 | Adapter error codes MUST distinguish HTTP status categories: `ERR_AUTH` (401/403 — bad or expired key), `ERR_RATE_LIMIT` (429 — provider rate limit), `ERR_PROVIDER_DOWN` (5xx — server error), `ERR_PROVIDER` (network/timeout/other). Generic `ERR_PROVIDER` is NOT acceptable when the HTTP status code is available. | MUST | Error code test |
| 069 | On `ERR_AUTH` (HTTP 401/403), the adapter MUST call `invalidate_key(provider)` to clear the cached key before returning the error result. Next dispatch re-fetches from the backend chain (req 037). This implements the cache-invalidation-on-error promise in req 040. | MUST | Invalidation test |
| 070 | Empty or missing response body from a provider with HTTP 200 MUST be treated as `status="error"` with `error_code="ERR_EMPTY_RESPONSE"`, not `status="done"` with empty `raw_output`. A provider that returns nothing has not completed the task. | MUST | Empty response test |


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
Task arrives at Rondo (MCP, CLI, or Python import)
        │
   ┌────┴────┐
   │ Router  │ ← get_provider(model) → Claude or non-Claude?
   └────┬────┘
        │
  ══════╪══════════════  TRANSPORT LAYER (provider-specific)  ═══════
        │
   ┌────┴──────────────────────────────────────────────────────────┐
   │                                                               │
   │  Claude path               Non-Claude path                   │
   │  ┌──────────────┐          ┌──────────────┐  ┌────────────┐  │
   │  │ dispatch_    │          │ Ollama       │  │ Future     │  │
   │  │ task()       │          │ Adapter      │  │ adapters   │  │
   │  │ (subprocess  │          │ (HTTP API)   │  │ (Gemini,   │  │
   │  │  claude -p)  │          │              │  │  OpenAI)   │  │
   │  │ 1168 tests   │          │              │  │            │  │
   │  └──────┬───────┘          └──────┬───────┘  └─────┬──────┘  │
   │         │                         │                │         │
   └─────────┼─────────────────────────┼────────────────┼─────────┘
             │                         │                │
             └─────────────┬───────────┘────────────────┘
                           │
  ═════════════════  FINALIZATION LAYER (shared, mandatory)  ═════════
                           │
                  ┌────────┴────────┐
                  │ _finalize_      │  audit OUTCOME, sanitize,
                  │ dispatch()      │  spool, history, metrics
                  │ (ALL providers) │  — ALWAYS-ON, no bypass
                  └────────┬────────┘
                           │
                      TaskResult (same format regardless of provider)
```

### Phase 1 vs Phase 2

| Phase | Claude path | Non-Claude path | Finalization |
|-------|-------------|-----------------|--------------|
| **Phase 1 (current)** | `dispatch_task()` directly | `ProviderAdapter.dispatch()` | Shared `_finalize_dispatch()` for ALL |
| **Phase 2 (future)** | Extract transport into `ClaudeCLIAdapter.dispatch()` | Same as Phase 1 | Same — `dispatch_task()` becomes thin router |

Phase 2 triggers when a 3rd provider is added or during an architecture sprint.
The anti-pattern this prevents: "two paths to the same outcome where one path gets features the other doesn't" (split-brain dispatch, caught Session 94 by DeepSeek-R1 contrarian review).

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
[providers.gemini]
enabled = true
base_url = "https://generativelanguage.googleapis.com/v1beta"
keychain_item = "ace.ai-key.gemini"
cheap_model = "gemini-2.0-flash-lite"       ## fast, lowest cost
default_model = "gemini-2.5-flash"           ## balanced
best_model = "gemini-2.5-pro"               ## highest quality
budget_monthly_usd = 50.00
trust = "trusted"

[providers.openai]
enabled = true
base_url = "https://api.openai.com/v1"
keychain_item = "ace.ai-key.openai"
cheap_model = "gpt-4.1-mini"
default_model = "gpt-4.1"
best_model = "o3"
budget_monthly_usd = 50.00
trust = "trusted"

[providers.grok]
enabled = true
base_url = "https://api.x.ai/v1"
keychain_item = "ace.ai-key.grok"
cheap_model = "grok-3-mini"
default_model = "grok-3"
best_model = "grok-3"
budget_monthly_usd = 30.00
trust = "untrusted"                          ## Chinese-owned — internal tasks skip

[providers.anthropic]
enabled = true
base_url = "https://api.anthropic.com/v1"
keychain_item = "ace.ai-key.anthropic"
cheap_model = "claude-haiku-4-5"
default_model = "claude-sonnet-4-6"
best_model = "claude-opus-4-6"
budget_monthly_usd = 100.00
trust = "trusted"

[auth]
backend = "auto"                             ## env → keychain → 1password (REQ-109 req 037)
onepassword_vault = "AI Keys"                ## metadata only — never secrets
```

### Routing Table (TOML)

```toml
[routing]
build = "claude-api"
review_forward = "gemini"
overnight_build = "claude-batch"
```

### Cloud Config (TOML)

```toml
[cloud]
default_count = 2                            ## --cloud uses 2 providers
max_count = 4                                ## --cloud 4 max
max_cost_per_dispatch = 0.50                 ## abort if estimated cost exceeds
default_tier = "default"                     ## high | default | low

[cloud.profiles.review]
providers = ["gemini", "openai", "grok"]
description = "Code review, bug finding, spec analysis"

[cloud.profiles.coding]
providers = ["openai", "anthropic"]
description = "Code generation, refactoring"

[cloud.profiles.research]
providers = ["gemini", "openai"]
description = "Analysis, summarization, literature review"
```

---

## 6. Data Boundary

**What this produces:**

| Output | Format | Consumer |
|--------|--------|----------|
| DispatchResult | Python dataclass / JSON | Rondo core, OAResult builder |
| Provider health status | JSON | Preflight (Rondo-REQ-103), `rondo providers` CLI |
| Affinity data | DB rows (from dispatch audit trail) | Routing suggestions |
| Cost per provider | Aggregated from DispatchResult | Notifications (Rondo-REQ-105), morning report |

**What this consumes:**

| Input | Format | Producer |
|-------|--------|----------|
| API keys | macOS Keychain entries | `ai-keys.py set` |
| Routing config | TOML | `.rondo/config.toml` |
| OAPayload | JSON | OB or direct caller |
| Provider API responses | JSON (provider-specific) | AI provider REST APIs |

---

## 7. MCP / API Interface

### Existing MCP Tools (BUILT)

| Tool | Purpose | Status |
|------|---------|--------|
| `rondo_multi_review` | Dispatch same prompt to N providers, per-provider + merged findings | BUILT (Session 96) |
| `rondo_models` | List available models across all providers | BUILT |
| `rondo_benchmark` | Speed/cost comparison across models | BUILT |

### Planned MCP Tools

| Tool | Purpose | Status |
|------|---------|--------|
| `rondo_cloud` | Cloud dispatch with profiles + tiers (MCP equivalent of `--cloud`) | PLANNED |
| Provider health query | "Which providers are healthy?" → provider list + health + model count | PLANNED |

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
  Same COALESCE pattern as config resolution (Rondo-STD-109).
- **Health check with cache:** Check once, cache for TTL, re-check on failure. Same pattern
  as Rondo-REQ-103 (preflight) rate limit caching.

---

## 13. Integration Points

| Integration | Spec | Direction | Contract |
|-------------|------|-----------|----------|
| Dispatch engine | Rondo-REQ-100 | Internal | Router selects adapter, adapter returns DispatchResult |
| Preflight | Rondo-REQ-103 | Internal | Per-provider health checks |
| Multi-account | Rondo-REQ-110 | Internal | Multiple adapter instances per provider |
| Caliber | Rondo-IFS-101 | Indirect | Caliber requests model via Task.model, Rondo routes |
| OB | Rondo-IFS-102 | Indirect | OB requests model via OAPayload.runtime.model |
| Audit trail | Rondo-STD-113 | Outbound | Provider + model in every audit entry |

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
| CORE-STD-021 (MCP Standard) | Future MCP tool for provider health queries |

---

## 15. Self-Correction

- After 50+ dispatches per model-task pair, affinity suggestions compare observed performance
  against the routing table. If a different model consistently outperforms the configured
  one, the morning report suggests a routing change.
- If a provider's health check fails 3 times consecutively, it's marked "down" and excluded
  from the routing table until manual re-enablement or successful health check.
- Cost tracking per provider feeds back into Rondo-REQ-106 (trend alerting) — if a provider's
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

| Item | Estimate | Status |
|------|----------|--------|
| ProviderAdapter ABC + DispatchResult | 0.5 day | **DONE** |
| 4 adapters (Ollama, ChatCompletions, Gemini, Anthropic) | 2 days | **DONE** |
| Router + routing table (get_provider) | 1 day | **DONE** |
| KeyBackend (env→keychain→1password) | 0.5 day | **DONE** |
| rondo_multi_review MCP tool | 0.5 day | **DONE** |
| Tier resolution (parse_model + config lookup) | 1 day | Sprint B |
| Cloud orchestration (--cloud, profiles, parallel) | 2 days | Sprint C |
| Cloud cost controls (caps, budget, estimates) | 1 day | Sprint C |
| Data sensitivity + trust filtering | 0.5 day | Sprint C |
| Cloud failure policy (partial result) | 0.5 day | Sprint C |
| Health checking + caching | 0.5 day | Sprint D |
| Affinity tracking (learned routing) | 1.5 days | Sprint E |
| Tests (all new features) | 2 days | Across sprints |
| **Total** | **~13 days** | **~5 days DONE, ~8 days remaining** |

---

## 19. Test Categories

| Category | What | Count (est.) | Status |
|----------|------|-------------|--------|
| Unit | Each adapter (mock provider API), router, health check | 18 | Partial (adapters done) |
| Integration | End-to-end dispatch through adapter to mock API | 6 | Partial |
| Credential | KeyBackend chain, Keychain, 1Password, env, cache, invalidate | 24 | **DONE** |
| Routing | Task type → provider resolution, fallback, override | 8 | Partial |
| Health | Health check, caching, down detection, recovery | 6 | Planned |
| Affinity | Score tracking, suggestion generation | 4 | Planned |
| Tier | Tier resolution, config lookup, precedence, validation | 8 | Sprint B |
| Cloud | --cloud flag, profiles, count, parallel dispatch, merge | 12 | Sprint C |
| Cost | Cost caps, budget tracking, estimates, abort | 6 | Sprint C |
| Failure | Partial result, all-fail, timeout, status codes | 6 | Sprint C |
| Security | Sensitivity flag, trust filter, prompt sanitization | 4 | Sprint C |
| Multi-review | MCP tool, dry run, provider list, error handling | 5 | **DONE** |

---

## 20. Failure Modes

| Failure | Impact | Mitigation |
|---------|--------|------------|
| Provider API changes format | Adapter returns bad DispatchResult | Version pinning + adapter-level parsing |
| Keychain unavailable | No API keys | Preflight catches before dispatch |
| All providers down | No dispatch possible | Ollama (local) as last resort |
| Routing table misconfigured | Wrong provider for task type | Config validation at startup |
| Affinity data misleading | Bad routing suggestion | Manual override always wins |
| Claude Code CLI flags change | `--output-format stream-json` or other flags removed/renamed | Rondo-REQ-103 smoke test catches before dispatch. Version compatibility matrix tracks known-good flag sets. |
| Claude Code CLI update breaks overnight | Silent failures in batch runs | Rondo-REQ-103 preflight re-validates on version change (req 020). Detailed debug logging (req 024). |
| Cloud dispatch 1 of N fails | Partial results | Default: return successful results + error for failed provider. All-fail: return error with per-provider details. (Reqs 057-059) |
| Cloud cost exceeds cap | Unexpected bill | Pre-dispatch cost estimate; abort if over cap. Monthly budget tracking per provider. (Reqs 053-056) |
| Sensitive data to untrusted provider | Data leak | Sensitivity flag + trust level filtering. Prompt sanitization strips paths/keys. (Reqs 061-063) |
| Tier name collides with model name | Wrong model dispatched | Tier names are reserved words (high/default/low). Exact model always wins. (Req 043, D12) |

---

## 21. Dependencies + Used By

| Depends On | Why |
|------------|-----|
| Rondo-REQ-100 | Core dispatch framework (defines Task, DispatchResult interface) |
| Rondo-REQ-103 | Preflight checks provider health |
| CORE-ADR-001 | Service architecture — Rondo is sole AI-aware component |
| CORE-IFS-001 | Universal contract patterns |
| CORE-STD-008 | Secrets management (Keychain) |

| Used By | Why |
|---------|-----|
| Rondo-REQ-110 | Multi-account routing for overnight |
| Rondo-IFS-101 | Caliber tasks routed through adapters |
| Rondo-IFS-102 | OB tasks routed through adapters |
| Rondo-REQ-106 | Per-model trend data comes from adapter dispatch results |
| Rondo-REQ-107 | Per-model flakiness tracking |

---

## 22. Decisions

| # | Decision | Date | Why |
|---|----------|------|-----|
| D1 | Abstract base class (not protocol/interface) | 2026-03-20 | ABCs enforce implementation at class creation time |
| D2 | macOS Keychain for all credentials | 2026-03-20 | OS-level encryption, no plaintext anywhere |
| D3 | Affinity is advisory, manual wins | 2026-03-20 | Mark controls routing. AI suggests, Mark decides. |
| D4 | 6 adapter types in v1 | 2026-03-20 | Claude CLI/API, Gemini, OpenAI, Ollama, Container covers all known needs |
| D5 | Session 83 default routing table | 2026-03-20 | Proven live — 3 providers tested with real API calls |
| D6 | Remove ClaudeCLIAdapter (Phase 1) | 2026-03-31 | Dead code — both CLI and MCP callers bypass it via `if provider.name != "claude"`. Misleads readers into thinking Claude goes through adapter pattern. Session 94: 2 AI bodies (Qwen, DeepSeek-R1) confirmed removal. |
| D7 | Shared finalization pipeline for ALL providers | 2026-03-31 | Ollama CLI path was missing audit, sanitize, spool, history, metrics — half the ALWAYS-ON pipeline. Fix: all providers pass results through `_finalize_dispatch()`. Session 94: Cursor identified split-brain, DeepSeek-R1 validated fix. |
| D8 | Phased approach: fix pipeline now, pure adapters later | 2026-03-31 | DeepSeek-R1 argued for full unification (all providers through adapter pattern). Deferred to Phase 2 — refactoring 300+ lines of proven Claude transport code risks regressions with only 2 providers. Phase 2 triggers when 3rd provider arrives. |
| D9 | Move recommend_model() from hardcoded dict to TOML config | 2026-03-31 | Cursor critique: "hardcoded strategy map pretending to be future-proof." Config-driven routing lets Mark update model preferences without code changes. Affinity tracking (req 021-023) can suggest, config decides. |
| D10 | 3 fixed tiers (high/default/low), no custom tiers in v1 | 2026-04-02 | 4 AI bodies (Qwen, Gemini, OpenAI, Cursor) all agreed 3 is the right starting point. Custom tiers add complexity without proven need. Exact model override covers edge cases. |
| D11 | Partial result on cloud failure (not fail-whole) | 2026-04-02 | Cursor identified failure policy as gap. Partial results are more useful — 2 of 3 answers is better than 0. Failed provider clearly marked in result. |
| D12 | Exact model name beats tier in resolution | 2026-04-02 | All 4 AI bodies flagged syntax ambiguity (provider:tier vs provider:model). Resolution: exact model always wins. If "flash" isn't a tier name, it's a model name. Tier names are reserved words: high, default, low. |
| D13 | Cost caps are mandatory (not optional) | 2026-04-02 | All 4 AI bodies independently flagged cost caps as missing/critical. Multi-cloud = N× cost. Default cap: $0.50/dispatch. Per-provider monthly budget. |
| D14 | Data sensitivity flag for cloud security | 2026-04-02 | OpenAI + Gemini flagged multi-cloud attack surface. Sensitivity levels (public/internal/private) + provider trust levels prevent sending sensitive data to untrusted providers. |

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
| Split-brain dispatch (two paths, one gets features) | High | Provider paths diverge silently — one gets audit/sanitize/spool, the other doesn't | Req 026: ALL providers through shared `_finalize_dispatch()`. Req 029: guard test fails if bypass detected. Session 94 lesson. |

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
| Provider adapter interface | BUILT | ABC + 4 adapters live (Ollama, ChatCompletions, Gemini, Anthropic) | After new provider added |
| Claude dispatch (dispatch_task) | BUILT | Proven path, 1168 tests, 74 sprints | After Claude CLI changes |
| Ollama adapter | BUILT | Live dispatch to 8 local models | After Ollama API changes |
| ChatCompletions adapter | BUILT | Session 94 — OpenAI+Grok+Mistral in one adapter | After API changes |
| Gemini adapter | BUILT | Session 94 — generateContent API | After API changes |
| Anthropic API adapter | BUILT | Session 94 — Messages API | After API changes |
| KeyBackend (3 backends) | BUILT | Session 96 — env→keychain→1password, 24 tests | After new backend added |
| rondo_multi_review MCP tool | BUILT | Session 96 — 3 providers dispatched live, 5 tests | After provider changes |
| Shared finalization pipeline | BUILT | Session 94 — all providers through _finalize_dispatch | Phase 1 sprint |
| Multi-model routing (get_provider) | BUILT | Routes 6 providers by prefix | After new provider |
| Provider tiers (3-tier config) | DESIGNED | Session 96 — 4 AI body consensus | Sprint B |
| Cloud dispatch (--cloud flag) | DESIGNED | Session 96 — reqs 046-063 | Sprint C |
| Cloud cost controls | DESIGNED | Session 96 — reqs 053-056 | Sprint C |
| Data sensitivity / trust | DESIGNED | Session 96 — reqs 061-063 | Sprint C |
| Phase 2: Claude as real adapter | THEORY | DeepSeek-R1 validated architecture | When beneficial |


## 35. Change History

| Version | Date | What Changed |
|---------|------|-------------|
| 1.0 | 2026-03-20 | Initial. Provider adapter interface, credential management, model routing, affinity tracking. 25 requirements. Session 83: 3 providers proven live. |
| 1.1 | 2026-03-22 | Filled to 35 sections. Added CORE-STD-012, CORE-STD-013, CORE-STD-021 refs. Approval (Mark, Session 84). |
| 1.2 | 2026-03-31 | **Split-brain fix (Session 94).** Removed ClaudeCLIAdapter (D6). Added shared finalization pipeline reqs 026-029 (D7). Phased approach: Phase 1 fixes pipeline gap, Phase 2 extracts Claude into real adapter (D8). recommend_model to TOML config (D9). New architecture diagram: two transports, one finalization. Risk added: split-brain anti-pattern. Feature maturity updated to reflect built state. AI body review: Qwen 32B (architectural) + DeepSeek-R1 8B (contrarian). Cross-product verified: CORE-ADR-001 already mandates this design, no changes needed to OB/Caliber/ACE specs. |
| 1.3 | 2026-04-01 | **Multi-provider adapter architecture (Session 94 continued).** Updated req 002: 3 adapter classes not 6 (ChatCompletions handles OpenAI+Grok+Mistral). Updated req 005: TOML config schema with per-provider subtables. Added reqs 030-034: adapters/ directory structure, ChatCompletionsAdapter, provider:model routing (parse_model), rondo_multi_review MCP tool, Keychain auth. Based on analysis of ai_review.py (1260 lines, 5 providers) + Cursor design review. v0.7 roadmap: 9 sprints (RONDO-114 to RONDO-122). |
| 1.5 | 2026-04-02 | **Cloud dispatch + tiers + cost controls (Session 96).** Added 23 requirements (041-063): provider tiers (3 per provider), cloud dispatch (`--cloud` flag + profiles + count), cost controls (per-dispatch cap, monthly budget), failure policy (partial result default), data sensitivity + provider trust. Updated config TOML with full provider examples, cloud profiles, auth section. Updated MCP section (rondo_multi_review BUILT). Updated feature maturity (8 features BUILT, 4 DESIGNED). 6 new decisions (D10-D14). 4 new failure modes. Reviewed by 4 AI bodies (Qwen 32B, Gemini 2.5 Flash, OpenAI GPT-4.1, Cursor). Sprint plan: B (tiers), C (cloud orchestration), D (health), E (affinity). |
| 1.4 | 2026-04-02 | **KeyBackend interface (Session 94 final).** Fixed req 006: Keychain service name `ace.ai-key.<provider>` (was `ace2-<provider>`, mismatched ai-keys.py). Updated req 007: shared `load_api_key()` in `adapters/auth.py`. Added reqs 035-040: precedence (env→keychain→1password), KeyBackend interface, auto mode, 1Password CLI integration, config metadata only, key caching with TTL. 3 AI body reviews (DeepSeek + Qwen + Cursor) confirmed pluggable design. |
