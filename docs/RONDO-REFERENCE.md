# Rondo Reference — Complete System Guide

**Product:** Rondo v0.6 | **Updated:** 2026-04-05 | **Tests:** 1,404 | **MCP Tools:** 23

*Define AI tasks in Python. Send them to any provider. Get structured results back.*

---

## Architecture

```
                          ┌─────────────────────────────────────────┐
                          │             THREE DOORS IN              │
                          │                                        │
                          │  CLI              MCP           Python  │
                          │  rondo run        rondo_run()   Round() │
                          │  rondo providers  rondo_cloud() Task()  │
                          │  rondo metrics    + 19 more     run()   │
                          │  15 commands      23 tools      import  │
                          └────────┬──────────┬──────────┬──────────┘
                                   │          │          │
                          ┌────────┴──────────┴──────────┴──────────┐
                          │           CONFIG (COALESCE)             │
                          │  CLI flag > ~/.rondo/config.toml > code │
                          │  Tiers: high / default / low            │
                          │  Profiles: review / coding / research   │
                          └────────────────┬────────────────────────┘
                                           │
                ┌──────────────────────────┬┴┬──────────────────────────┐
                │                          │ │                          │
     ┌──────────┴──────────┐    ┌──────────┴─┴─────────┐    ┌─────────┴──────────┐
     │   CLAUDE PATH       │    │   CLOUD ADAPTERS      │    │   LOCAL PATH       │
     │   (subprocess)      │    │   (HTTP API)          │    │   (Ollama)         │
     │                     │    │                       │    │                    │
     │   claude -p         │    │   Gemini    (Google)  │    │   llama3.1:8b      │
     │   Max plan / API    │    │   Grok      (xAI)    │    │   qwen2.5:32b      │
     │                     │    │   Mistral   (EU)     │    │   deepseek-r1      │
     │                     │    │   OpenAI    (GPT-4.1) │    │                    │
     │                     │    │   Anthropic (API key) │    │                    │
     └──────────┬──────────┘    └──────────┬───────────┘    └─────────┬──────────┘
                │                          │                          │
                └──────────────┬───────────┘──────────────────────────┘
                               │
                ┌──────────────┴───────────────────────────────────────┐
                │           ALWAYS-ON FINALIZATION                     │
                │                                                      │
                │   Audit OUTCOME → Sanitize → Spool → History →      │
                │   Metrics → Cost tracking                            │
                │                                                      │
                │   Every dispatch. Every provider. No bypass.         │
                └──────────────┬───────────────────────────────────────┘
                               │
                          TaskResult (same format, any provider)
```

### Provider Routing

Model strings route to adapters automatically:

| Prefix | Provider | Adapter | Example |
|--------|----------|---------|---------|
| `gemini:` | Google Gemini | GeminiAdapter | `gemini:gemini-flash-latest`, `gemini:gemini-pro-latest` |
| `grok:` | xAI Grok | ChatCompletionsAdapter | `grok:grok-4.3` |
| `mistral:` | Mistral | ChatCompletionsAdapter | `mistral:mistral-large-latest` |
| `openai:` | OpenAI | ChatCompletionsAdapter | `openai:gpt-5.5` |
| `anthropic:` | Anthropic API | AnthropicAPIAdapter | `anthropic:claude-sonnet-4-6` |
| `local:` | Ollama | OllamaAdapter | `local:llama3.1:8b` |
| *(no prefix)* | Claude CLI | subprocess | `sonnet`, `opus`, `haiku` |

### 3-Tier Model Selection

Each provider defines 3 tiers in `~/.rondo/config.toml`:

| Tier | Use for | Flag |
|------|---------|------|
| **high** | Architecture decisions, deep analysis | `--cloud high` or `tier="high"` |
| **default** | Standard reviews, code analysis | *(default)* |
| **low** | Fast checks, simple scans | `--cloud low` or `tier="low"` |

### API Key Chain (REQ-109 reqs 035-040)

Keys loaded automatically — no config needed if env vars are set:

```
env var → macOS Keychain → 1Password CLI
  ↓           ↓                 ↓
GEMINI_API_KEY   ace.ai-key.gemini   op://AI Keys/gemini/password
```

5-minute cache. Invalidated on 401/403 (REQ-109 req 069).

---

## MCP Tools (23)

Claude Code discovers these automatically when the Rondo MCP server is registered.
Also exposes `rondo://help` resource for AI agent discovery (version, commands, schemas).

### Dispatch (2 tools)

| Tool | Parameters | What it does |
|------|-----------|-------------|
| **rondo_run** | `file_path`, `prompt`, `model`, `execution`, `dry_run`, `background`, `max_budget`, `timeout_sec`, `done_when`, `project` | Run a round file OR inline prompt. `execution` controls dispatch mode (`inline|subprocess|agent|""`). `dry_run=True` previews. `background=True` for async. |
| **rondo_run_status** | `dispatch_id`, `brief`, `heartbeat` | Check background dispatch. 3 detail tiers: heartbeat (~10 tokens), brief (~40), full (~300+). |

Execution defaults when `execution=""`:
- MCP caller: `inline`
- Python/CLI caller: `subprocess`
- Provider-prefixed models always route HTTP and bypass execution mode

### Composition (6 tools)

| Tool | Parameters | What it does |
|------|-----------|-------------|
| **rondo_cloud** | `prompt`, `profile`, `tier`, `count`, `dry_run` | Cloud AI dispatch — pick providers by profile (review/coding/research), tier (high/default/low), count (1-4). Cost-capped at $0.50/dispatch. |
| **rondo_multi_review** | `prompt`, `providers` (JSON array), `dry_run` | Same prompt to N providers, returns per-provider findings + merged summary. Default: local:qwen2.5:32b + gemini:gemini-flash-latest + grok:grok-4.3. |
| **rondo_chain** | `steps_json`, `dry_run` | Pipeline — output of step N feeds into step N+1. Max 20 steps. |
| **rondo_benchmark** | `prompt`, `models` (JSON array), `dry_run` | Same prompt to multiple models, ranked by speed + cost. Max 10 models. |
| **rondo_explain** | `output`, `question`, `model`, `dry_run` | Second opinion from local model ($0 cost). Default: qwen2.5:32b. |
| **rondo_summarize** | `dispatch_json`, `model`, `dry_run` | Condense multiple task results into one summary via AI. |

### Observable (6 tools)

| Tool | Parameters | What it does |
|------|-----------|-------------|
| **rondo_metrics** | *(none)* | Full dashboard — cost, reliability, latency, tokens, health. |
| **rondo_health** | *(none)* | Quick GREEN/YELLOW/RED + per-provider status. |
| **rondo_cost** | `days` | Monthly spend by model. Default 30 days. |
| **rondo_history** | `model`, `status`, `limit` | Filtered dispatch history + aggregate stats. |
| **rondo_audit_summary** | `limit` | Last N dispatch records with status, cost, duration. |
| **rondo_dispatch_info** | *(none)* | Version, commands, capabilities. Discovery tool for AI agents. |

### Operations (3 tools)

| Tool | Parameters | What it does |
|------|-----------|-------------|
| **rondo_diff** | `current_json`, `previous_json` | Compare two dispatch results — new/changed/removed findings. |
| **rondo_retry** | `dispatch_id`, `model` | Re-run failed tasks from a previous dispatch. |
| **rondo_spool_consume** | *(none)* | Drain overnight result mailbox. Returns all queued results. |

### Management (4 tools)

| Tool | Parameters | What it does |
|------|-----------|-------------|
| **rondo_models** | *(none)* | All providers with tiers, routing, task-type recommendations. |
| **rondo_templates** | *(none)* | Pre-built rounds: code-review, test-gaps, doc-sweep, security-audit, dependency-check. |
| **rondo_schedule_list** | *(none)* | Installed scheduled dispatches (launchd plists). |
| **rondo_schedule_create** | `file_path`, `interval`, `model`, `name`, `dry_run` | Create recurring dispatch: hourly/daily/weekly/monthly. |

---

## CLI Commands (19)

| Command | What it does |
|---------|-------------|
| `rondo run <file>` | Execute a round definition file |
| `rondo run <file> --dry-run` | Preview prompts without dispatching |
| `rondo run <file> --model gemini:gemini-flash-latest` | Override model for all tasks |
| `rondo live <file>` | Interactive mode — human reviews each task |
| `rondo overnight <file>` | Multi-phase overnight dispatch + morning report |
| `rondo report <results_dir>` | Generate morning report from saved results |
| `rondo replay <run_id>` | Re-run one saved task dispatch using stored prompt/model/execution |
| `rondo compare <id_a> <id_b>` | Side-by-side diff of status, duration, cost, and output snippet |
| `rondo preflight` | Check environment (Claude, disk, auth, providers) |
| `rondo providers` | Show all providers with health status + latency |
| `rondo history` | Dispatch history with model/status filters |
| `rondo audit` | Audit trail — cost, failures, dispatch details |
| `rondo metrics` | Cost/reliability/latency dashboard |
| `rondo flaky` | Detect flaky tasks with flip-rate analysis |
| `rondo spool list\|consume\|clean` | Manage overnight result mailbox |
| `rondo init` | Create starter round file |
| `rondo schedule <file>` | Create recurring launchd schedule |
| `rondo mcp` | Start MCP stdio server for Claude Code |
| `rondo version [--bump]` | Show version or bump build counter (RONDO-290) |

---

## Cloud Dispatch Profiles

Profiles are **config-defined** in `~/.rondo/config.toml` (not hardcoded).
If `[cloud.profiles]` is missing, `rondo_cloud(profile="review")` returns `ERR_INVALID_PROFILE`.

Recommended starter profiles:

| Profile | Providers | Use for |
|---------|-----------|---------|
| **review** | gemini:gemini-flash-latest + grok:grok-4.3 | Code reviews, spec reviews |
| **coding** | gemini:gemini-flash-latest + mistral:mistral-large | Implementation, refactoring |
| **research** | gemini:gemini-pro-latest + mistral:mistral-large | Deep analysis, architecture |
| **security** | gemini:gemini-flash-latest + grok:grok-4.3 + mistral:mistral-large | Security audit (3 providers) |

Define profiles in `~/.rondo/config.toml`:
```toml
[cloud.profiles.my-team]
providers = ["gemini:gemini-flash-latest", "anthropic:sonnet"]
description = "Team default"
```

---

## Error Handling (REQ-109 reqs 068-070)

Canonical envelope + error taxonomy reference: `docs/ERROR-ENVELOPE-CONTRACT.md` (REQ-112).

### Error Code Taxonomy

**Adapter errors (HTTP-based):**

| Code | HTTP | Meaning | Action |
|------|------|---------|--------|
| `ERR_AUTH` | 401/403 | Bad/expired API key | Key cache invalidated, retry with fresh key |
| `ERR_RATE_LIMIT` | 429 | Provider throttling | Back off, try later |
| `ERR_PROVIDER_DOWN` | 5xx | Server error | Fallback to next provider |
| `ERR_EMPTY_RESPONSE` | 200 (empty) | Provider returned nothing | Treated as error, not success |
| `ERR_PROVIDER` | other | Network/timeout/parse | Generic — check error_message |

**Orchestration errors (MCP/engine):**

| Code | Where | Meaning |
|------|-------|---------|
| `ERR_INPUT_TOO_LARGE` | MCP tools | Prompt exceeds 500KB limit |
| `ERR_INVALID_PROFILE` | rondo_cloud | Profile not found in config |
| `ERR_COST_CAP` | rondo_cloud | Estimated cost exceeds max_cost_per_dispatch |
| `ERR_LIMIT_EXCEEDED` | schedule_create | Max 20 schedules |
| `ERR_SUBPROCESS` | dispatch | Claude CLI subprocess failed |
| `ERR_NESTED_SESSION` | dispatch | Tried to dispatch inside existing Claude session |
| `ERR_WATCHDOG_TIMEOUT` | overnight | Phase exceeded watchdog timer |
| `ERR_TIMEOUT` | runner | Task exceeded timeout_sec |
| `ERR_CONFIG` | config | Invalid configuration |
| `ERR_INTERNAL` | parallel | Internal execution error |
| `ERR_INVALID_INPUT` | engine | Bad task/round parameters |
| `ERR_MUTATIONS_DISABLED` | engine | Write attempted in read-only mode |

### Health Check Strategy (REQ-109 reqs 071-073)

| Provider | Method | "Healthy" means |
|----------|--------|----------------|
| OpenAI | GET /v1/models | 200 with model list |
| Mistral | GET /v1/models | 200 with model list |
| Grok | GET /v1/models (fallback: any non-5xx) | API reachable |
| Gemini | GET /v1beta/models | 200 with model list |
| Anthropic | HEAD /v1/messages | Any non-5xx (even 405) |
| Ollama | GET /api/tags | 200 with tags |

Health cached 5 minutes. Provider down = log WARNING + use fallback.

---

## Test Suite — Living Examples

### Overview

| Category | File(s) | Tests | What they prove |
|----------|---------|-------|----------------|
| **E2E** | test_integration_e2e.py | 113 | Real CLI binary + real cloud provider dispatch |
| **MCP** | test_mcp.py | 109 | All 21 MCP tools return correct schemas |
| **Dispatch** | test_dispatch.py | 203 | Prompt building, model resolution, subprocess, JSON parsing |
| **Engine** | test_engine.py | 126 | Round/Task data model, validation, gates, state |
| **Runner** | test_runner.py | 41 | Execution orchestration, task states, timeouts |
| **Parallel** | test_parallel.py | 34 | Thread pool, worker config, conflict detection |
| **Overnight** | test_overnight.py | 48 | Phase sequencing, rate limiting, watchdog |
| **Examples** | test_examples.py | 25 | Example rounds are valid + spec-compliant |
| **Live mode** | test_live.py | 23 | Interactive execution, human input |
| **Providers** | test_providers.py | 85 | Adapters, routing, tiers, error codes, health |
| **Config** | test_config.py | 85 | TOML loading, validation, COALESCE resolution |
| **CLI** | test_cli.py | 85 | Subcommands, flags, arg parsing |
| **AI Help** | test_ai_help.py | 50 | AI discovery schema, capabilities |
| **Auth** | test_auth.py | 24 | Key backends (env, keychain, 1Password) |
| **Health** | test_health.py | 22 | Provider health, caching, fallback |
| **Conventions** | test_conventions.py | 21 | Code standards (SPDX, docstrings, imports) |
| **Audit** | test_audit.py | 34 | Audit trail recording, scrubbing |
| **Other** | 11 more files | ~131 | Sanitize, preflight, spool, metrics, history, report, flaky, notify |
| **TOTAL** | **28 files** | **1,347** | |

### E2E Tests as Usage Examples

Every E2E test runs the real `rondo` binary. They are the definitive documentation of how commands work.

**How to run a round (TestE2EExampleRounds):**
```
rondo run examples/rounds/round_hello.py --dry-run
rondo run examples/rounds/round_code_review.py --dry-run
rondo run examples/rounds/round_doc_sweep.py --dry-run
```

**How to check provider health (TestE2EPreflight):**
```
rondo preflight
rondo preflight --json
```

**How to review dispatch history (TestE2EHistory):**
```
rondo history --json
rondo history --model sonnet --expensive
```

**How to use overnight mode (TestE2EOvernightDryRun):**
```
rondo overnight examples/rounds/phases_overnight.py --dry-run
```

**How to use live interactive mode (TestE2ELiveMode):**
```
rondo live examples/rounds/round_hello.py --task greet
```

**How to create a new round (TestE2EInit):**
```
rondo init --name my-review
```

### MCP Tests as AI Integration Examples

MCP tests demonstrate what Claude Code sees when calling Rondo tools.

**Cloud dispatch with profiles (TestCloudDispatch):**
```python
rondo_cloud(prompt="Review this code", profile="review", tier="high", count=2, dry_run=True)
```

**Multi-provider review (TestMultiReview):**
```python
rondo_multi_review(prompt="Analyze this", providers='["gemini:gemini-flash-latest", "grok:grok-4.3"]', dry_run=True)
```

**Pipeline chaining (TestRondoChain):**
```python
rondo_chain(steps_json='[{"prompt": "Find issues", "model": "gemini:gemini-flash-latest"}, {"prompt": "Fix them", "model": "sonnet"}]', dry_run=True)
```

**Background dispatch (TestRondoRunStatus):**
```python
result = rondo_run(prompt="Long analysis", background=True)
status = rondo_run_status(dispatch_id=result["dispatch_id"], heartbeat=True)
```

### Real Cloud E2E Tests (living proof the adapters work)

These tests make **real API calls** to cloud providers. They prove the full chain:
key loading → adapter → HTTP → response parsing → TaskResult.

| Test | Provider | What it proves | Cost |
|------|----------|---------------|------|
| `test_real_gemini_dispatch` | Gemini | generateContent API works | ~$0.001 |
| `test_real_grok_dispatch` | Grok (xAI) | Chat Completions API works | ~$0.003 |
| `test_real_mistral_dispatch` | Mistral (EU) | Chat Completions API works | ~$0.002 |
| `test_real_gemini_grok_review` | Gemini + Grok | Two providers review same code | ~$0.004 |
| `test_real_gemini_mistral_review` | Gemini + Mistral | Both detect SQL injection | ~$0.003 |
| `test_gemini_health` | Gemini | Live health check returns True | free |
| `test_grok_health` | Grok | Live health check returns True | free |
| `test_mistral_health` | Mistral | Live health check returns True | free |

Run them:
```bash
## All cloud tests (~$0.02 total)
pytest rondo/tests/test_integration_e2e.py -k "RealCloud or RealMulti or RealProvider" -v

## Just Gemini
pytest rondo/tests/test_integration_e2e.py -k "gemini" -v

## Just multi-provider reviews
pytest rondo/tests/test_integration_e2e.py -k "RealMulti" -v
```

Each test auto-skips if the provider's API key isn't configured.

### Example Round Files

Living examples in `rondo/examples/`:

| File | What it teaches |
|------|----------------|
| `round_hello.py` | Minimal round — 1 task, basic structure |
| `round_file_check.py` | Context files — inject data into prompts |
| `round_multi_task.py` | Multiple tasks in sequence |
| `round_code_review.py` | Real-world code review pattern |
| `round_doc_sweep.py` | Documentation audit pattern |
| `round_test_generator.py` | Test generation from source |
| `round_refactor_audit.py` | Refactoring safety check |
| `round_caliber_fix.py` | Caliber integration example |
| `round_security_audit.py` | Security audit pattern |
| `phases_overnight.py` | Overnight multi-phase example |
| `demo_pipeline.py` | Unix-style pipeline chaining |
| `review_demo.py` | Multi-provider review demo |

### Running the Tests

```bash
# All Rondo tests
cd ~/git/mhubers/ace2 && pytest rondo/tests/ -v

# Just E2E (requires rondo installed)
pytest rondo/tests/test_integration_e2e.py -v

# Just MCP tools
pytest rondo/tests/test_mcp.py -v

# Just cloud adapter tests
pytest rondo/tests/test_providers.py -k "ErrorCode or KeyInvalidation or EmptyResponse or HealthStrategy" -v

# Real dispatch smoke (costs ~$0.01)
pytest rondo/tests/test_integration_e2e.py -k "RealDispatch" -v
```

---

## Project Structure

```
rondo/
  src/rondo/
    __init__.py          # Public API: Round, Task, run_round
    engine.py            # Data model: Round, Task, TaskResult, Gate
    runner.py            # Execution: sequential/parallel, gates
    dispatch.py          # Claude subprocess + provider routing
    config.py            # TOML loading, COALESCE resolution
    cli.py               # 14 CLI subcommands
    mcp_server.py        # 18 MCP tools (stdio transport)
    mcp_tools.py         # Observable + management tool implementations
    adapters/
      ollama.py          # Local LLM (Ollama HTTP API)
      chat_completions.py # OpenAI + Grok + Mistral (same API shape)
      gemini.py          # Google Gemini (unique API)
      anthropic_api.py   # Anthropic Messages API (unique API)
      auth.py            # API key chain: env -> keychain -> 1password
      health.py          # Provider health checks (5-min TTL cache)
    providers.py         # Model routing + tier resolution
    audit.py             # Always-on dispatch audit trail
    history.py           # Dispatch history + filtering
    metrics.py           # Cost, reliability, token aggregation
    sanitize.py          # Credential scrubbing
    spool.py             # Overnight result mailbox
    schedule.py          # launchd plist generation
    notify.py            # macOS desktop notifications
    preflight.py         # Environment checks
    report.py            # Morning report generation
    flaky.py             # Flakiness detection
    _version.py          # Version management
  tests/                 # 1,311 tests (28 files)
  examples/              # Living example rounds
  specs/                 # REQ-100 through REQ-109
  docs/                  # This file + guides
```

---

## Key Numbers

| Metric | Value |
|--------|-------|
| MCP tools | 23 |
| CLI commands | 14 |
| Cloud adapters | 5 (Gemini, ChatCompletions, Anthropic, Ollama, Claude CLI) |
| Cloud providers | 7 (Gemini, Grok, Mistral, OpenAI, Anthropic, Ollama, Claude) |
| Tests | 1,347 |
| E2E tests | 113 (8 real cloud dispatch) |
| Example rounds | 12 |
| Lines of code | ~8,000 (rondo/src/) |
| Specs | REQ-100 through REQ-109 (10 specs) |

---

*Built by Mark G. Hubers with Claude Code (Opus). Session 97.*
