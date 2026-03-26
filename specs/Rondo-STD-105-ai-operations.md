# Rondo-STD-105: AI Operations

*How Rondo dispatches to AI models, tracks costs, handles rate limits, and supports multi-model routing. Rondo IS the dispatch layer.*

**Created:** 2026-03-18 | **Status:** DESIGNED
**Classification:** redacted
**Version:** 0.1
**Owner:** Mark G. Hubers
**Reviewed:** not-yet
**Supersedes:** none
**Universal standard** — same topic number across all products (DEC-017)
**Product:** Rondo
**Matches:** CORE-STD-006, Rondo-STD-105 (Caliber)
**Depends on:** CORE-STD-006, CORE-STD-012, Rondo-STD-101, ACE-STD-020, Rondo-IFS-104, CORE-STD-021, Rondo-STD-102, CORE-STD-013, Rondo-STD-107

---

## 1. Purpose & Scope

Defines the rules for how Rondo works with AI systems. Unlike OB (which consumes AI results), Rondo IS the AI dispatch layer — it sends tasks to models, captures results, and tracks costs. This spec covers model selection, cost tracking via DispatchUsage, rate limit handling, context window awareness, and multi-model support.

**IN scope:**
- Model selection and routing (COALESCE chain)
- Cost tracking per dispatch (DispatchUsage fields)
- Rate limit detection and handling
- Context window awareness and budget hints
- Multi-model support (Claude, Gemini, Ollama — future)
- Stream-json extraction protocol

**OUT of scope:**
- Independent AI review protocol (CORE-STD-006 domain — OB manages reviewer independence)
- Attention budget tiers (CORE-STD-006 domain — consumers decide context budgets)
- Spec digest format (CORE-STD-006 domain — Rondo dispatches prompts, not specs)
- AI self-correction loops (CORE-STD-004 domain)

**Users:** Mark (primary). Claude AI agents dispatching to other models. Future: teams needing multi-model AI orchestration, batch processing, cost optimization across AI providers.

---

## 2. The Problem

AI dispatch without cost tracking is a blank check. Without model routing, every task uses the same model regardless of complexity. Without rate limit awareness, overnight runs fail silently when the API throttles them. Rondo must be the intelligent dispatch layer — routing tasks to the right model, tracking every dollar spent, and handling API constraints gracefully.

---

## 3. Requirements

*All requirements use MUST/SHOULD priority per CORE-STD-012.*

### Model Selection
| ID | Requirement | Priority |
|----|-------------|----------|
| 001 | System SHALL model selection follows the COALESCE chain: CLI `--model` flag > `task.model` hint > `config.dispatch.default_model` > `"sonnet"` hardcoded fallback | MUST |
| 002 | System SHALL rondo passes `--model {model}` to the `claude -p` subprocess. Model names match Claude Code CLI values: `opus`, `sonnet`, `haiku` | MUST |
| 003 | System SHALL round definitions tag each task with a recommended model based on task complexity. Simple tasks (file counting, format checks) use `haiku`. Complex tasks (architecture review, code generation) use `opus`. Default is `sonnet` | MUST |
| 004 | System SHALL model validation at dispatch: if the resolved model is not in the known model list, fail with error_code `CONFIG_INVALID_MODEL` before spawning the subprocess | MUST |
| 005 | System SHALL the known model list is maintained in `config.py`, not hardcoded per-file. When Claude releases new models, update one list | MUST |

### Cost Tracking (DispatchUsage)
| ID | Requirement | Priority |
|----|-------------|----------|
| 006 | Every AI dispatch MUST produce a `DispatchUsage` object with these fields (per NAMING-MAP.md): | MUST |

| Field | Type | Source |
|-------|------|--------|
| `task_name` | str | Task definition |
| `model` | str | Resolved model name |
| `cost_usd` | float | stream-json `result` event `total_cost_usd` |
| `input_tokens` | int | stream-json `result` event |
| `output_tokens` | int | stream-json `result` event |
| `cache_read_tokens` | int | stream-json `result` event |
| `cache_create_tokens` | int | stream-json `result` event |
| `duration_ms` | int | stream-json wall-clock |
| `duration_api_ms` | int | stream-json API time |
| `num_turns` | int | stream-json tool-use loop count |
| `context_window` | int | stream-json (200000 or 1000000) |
| `rate_limit_status` | str | "allowed", "blocked", or "unknown" |
| `is_using_overage` | bool | Past plan allocation? |
| `rate_limit_resets_at` | int | Epoch timestamp (0 = not available) |
| ID | Requirement | Priority |
|----|-------------|----------|
| 007 | DispatchUsage field names MUST match NAMING-MAP.md exactly. When OB stores Rondo results, it maps `DispatchUsage.cost_usd` to `sprint_intelligence.cost_usd` — same name, zero translation | MUST |
| 008 | System SHALL if stream-json parsing fails (Rondo-STD-101 rule 11), create a DispatchUsage with zeroed token fields and `cost_usd = 0.0`. Never skip the DispatchUsage object — consumers depend on it existing | MUST |
| 009 | System SHALL round-level cost summary: `sum(usage.cost_usd for usage in round_result.usage)` gives total round cost. This is computed by the consumer, not stored redundantly by Rondo | MUST |

### Rate Limit Handling
| ID | Requirement | Priority |
|----|-------------|----------|
| 010 | System SHALL stream-json emits `rate_limit_event` with current usage status. Rondo captures: `rate_limit_status` ("allowed" or "blocked"), `is_using_overage`, and `rate_limit_resets_at` (epoch timestamp) | MUST |
| 011 | System SHALL when rate limit status is "blocked": log at WARNING, record in DispatchUsage, and let the consumer decide whether to retry later. Rondo does NOT auto-retry on rate limits (Rondo-STD-101 rule 17) | MUST |
| 012 | System SHALL rate limit information is per-dispatch, not per-round. Different tasks may hit different rate limit states depending on timing | SHOULD |
| 013 | System SHALL for overnight automation (Rondo-REQ-101): the scheduler reads rate limit status from the previous dispatch and can pause between phases to wait for reset. This is scheduler logic, not dispatch logic | MUST |

### Context Window Awareness
| ID | Requirement | Priority |
|----|-------------|----------|
| 014 | System SHALL rondo captures `context_window` from stream-json (200K standard or 1M extended). This is informational — Rondo does not manage context budgets (OB does that) | MUST |
| 015 | System SHALL if a task consistently hits context limits (output truncated, errors about context), log at WARNING with the task name and context window size. The consumer should reduce the prompt or use a larger context model | SHOULD |
| 016 | System SHALL rondo does NOT pre-calculate prompt token counts. Token counting is model-specific and changes with each API version. Let Claude handle it — Rondo captures the actuals from stream-json | MUST |

### Multi-Model Support
| ID | Requirement | Priority |
|----|-------------|----------|
| 017 | System SHALL current support: Claude Code CLI (`claude -p`). This is the only backend for v1.0 | MUST |
| 018 | System SHALL future backends (Gemini, Ollama) will be added as separate dispatch modules. The dispatch interface is: | MUST |

    - Input: task prompt (str), model hint (str), config (RondoConfig)
    - Output: TaskResult + DispatchUsage
    - Each backend implements this interface
| ID | Requirement | Priority |
|----|-------------|----------|
| 019 | System SHALL model-to-backend routing: the `model` field determines which backend dispatches the task. Claude models (opus, sonnet, haiku) use `claude -p`. Future: gemini models use the Gemini API, ollama models use the local Ollama API | MUST |
| 020 | System SHALL backend selection is transparent to round definitions. A round says `model="sonnet"` — it does not say "use Claude." The dispatch layer resolves model to backend | MUST |

### Dispatch Protocol
| ID | Requirement | Priority |
|----|-------------|----------|
| 021 | System SHALL the prompt template wraps the task's three-field contract (Do/Read/Done) with output format instructions. The template is standardized — all tasks get the same framing | MUST |
| 022 | Dispatch MUST pass `--output-format stream-json` to capture real metrics. Text mode is never used (ACE-STD-020 lesson: estimated costs were inaccurate) | MUST |
| 023 | Dispatch MUST pass `--permission-mode {mode}` from the config's `permission_mode` field. Default: `auto` | MUST |
| 024 | System SHALL for code generation tasks (`tool_mode: "none"`): dispatch passes `--tools ""` to disable file tools | MUST |
| 025 | System SHALL for code fixing tasks (`tool_mode: "sandbox"`): dispatch passes `--dangerously-skip-permissions` (containers only, no internet) | MUST |
| 026 | Tool mode MUST be specified per task in the round definition. Default: `"default"` (Claude decides which tools to use) | MUST |

---
## 4. Architecture / Design

Dispatch follows a pipeline: resolve model (COALESCE) → construct subprocess args → spawn `claude -p` → capture stream-json → parse into DispatchUsage → return TaskResult. The dispatch module handles subprocess mechanics. The runner handles task sequencing. Model-to-backend routing is resolved before subprocess construction.

---

## 5. Data Model

`DispatchUsage` is the core data model — a Python dataclass with 13 fields capturing everything about a single AI dispatch. Fields match NAMING-MAP.md exactly. DispatchUsage is attached to each TaskResult and serialized to spool files. No separate cost database — consumers aggregate from DispatchUsage.

---

## 6. Data Boundary

Rondo produces DispatchUsage per dispatch. OB ingests it into `sprint_intelligence`. Caliber reads cost from scan results. The boundary is the DispatchUsage object (in-memory) and the spool file (on-disk). Field names are the contract — same names on both sides per NAMING-MAP.md.

---

## 7. MCP / API Interface

Future MCP tools (Rondo-IFS-104, CORE-STD-021): `rondo_query_cost` (cost estimate), `rondo_query_providers` (available models), `rondo_action_dispatch` (send prompt). Current v1.0: no MCP interface. Dispatch is via CLI (`rondo run`) or Python import.

---

## 8. States & Modes

Two auth modes affect AI operations: `max` (subscription, $0 marginal cost, rate-limited by plan) and `api` (pay-per-token, cost-tracked, higher limits). Tool mode per task: `default` (Claude chooses tools), `none` (no file tools), `sandbox` (skip permissions). Model selection per task via COALESCE.

---

## 9. Configuration

AI operations config in `rondo.toml [dispatch]`: `default_model`, `auth`, `task_timeout_sec`, `output_format`, `permission_mode`. Per-task model hints in round definitions. Model allowlist in `config.py`. See Rondo-STD-102 for full config resolution.

---

## 10. Rules
**Rate limit handling (CRIT fix):** Rondo does NOT auto-retry at the DISPATCH level (STD-105 is correct). STD-107's "retry on rate limit" applies to the SECURITY LAYER only (re-checking credentials after provider cooldown). Dispatch returns rate_limit status to the consumer. Consumer decides whether to retry, switch provider, or abort. Two different levels: security retries auth checks, dispatch does not retry task execution. & Constraints

### Model Selection COALESCE

```
effective_model = cli_flag  or  task.model  or  config.default_model  or  "sonnet"
                  ────────      ──────────      ──────────────────      ─────────
                  operator      round author    project config          hardcoded
```

### Model Complexity Guide

| Model | Cost | Use When |
|-------|------|----------|
| `haiku` | Lowest | Simple tasks: file counting, format checks, yes/no questions |
| `sonnet` | Medium | Default: code review, summaries, analysis, most tasks |
| `opus` | Highest | Complex: architecture review, multi-file refactoring, deep reasoning |

Round authors pick the right model per task. Operators override with `--model` when needed.

### What Rondo Manages vs What OB Manages

| Concern | Rondo (dispatch layer) | OB (consumer) |
|---------|----------------------|---------------|
| Model selection | COALESCE chain, pass to CLI | Not applicable for this spec type — see Section 3 for requirements and Section 4 for architecture. — trusts Rondo |
| Cost tracking | DispatchUsage per task | Stores in sprint_intelligence |
| Rate limits | Detect and report | Decide retry strategy |
| Context budget | Capture actual from stream-json | Define budget tiers, manage digests |
| Independent review | Not applicable for this spec type — see Section 3 for requirements and Section 4 for architecture. — dispatches what it's told | Enforces Context Asymmetry |
| Token reduction | Not applicable for this spec type — see Section 3 for requirements and Section 4 for architecture. — sends the prompt as-is | Builds spec digests before sending |

### DispatchUsage Defaults (When Data Unavailable)

| Field | Default | When |
|-------|---------|------|
| `cost_usd` | `0.0` | stream-json parse failure |
| `input_tokens` | `0` | stream-json parse failure |
| `output_tokens` | `0` | stream-json parse failure |
| `cache_read_tokens` | `0` | No cache event in stream |
| `cache_create_tokens` | `0` | No cache event in stream |
| `rate_limit_status` | `"unknown"` | No rate_limit_event in stream |
| `is_using_overage` | `False` | No rate_limit_event in stream |
| `rate_limit_resets_at` | `0` | No rate_limit_event in stream |
| `context_window` | `200000` | No system event with window size |

---

## 11. Quality Attributes

- **Cost transparency:** Every dispatch has a dollar amount. No hidden costs.
- **Model flexibility:** Task complexity matches model capability via COALESCE hints.
- **Graceful degradation:** Rate limits and parse failures produce partial results, not crashes.

---

## 12. Shared Patterns

- **COALESCE model selection:** CLI > task hint > config > default. Same idiom as config resolution (Rondo-STD-102).
- **DispatchUsage as transfer object:** Same fields consumed by OB, Caliber, and ACE — zero translation.
- **Stream-json extraction:** Shared parsing logic across all Claude-based dispatches.

---

## 13. Integration Points

| Integration | What Crosses | Standard Enforced |
|-------------|-------------|-------------------|
| Rondo → Claude CLI | `claude -p` subprocess with model/auth args | Dispatch protocol (section 3) |
| Rondo → OB | DispatchUsage fields | NAMING-MAP.md |
| Rondo → Caliber | Cost per scan dispatch | DispatchUsage.cost_usd |
| Rondo → CORE-STD-013 | Dispatch cost events | TrackerData format |

---

## 14. Standards Applied

| Standard | How It Applies |
|----------|---------------|
| CORE-STD-006 | Parent AI operations standard — Rondo adapts for dispatch context |
| CORE-STD-012 | Requirement readiness — model availability is a dispatch prerequisite |
| CORE-STD-013 | TrackerData — dispatch events (cost, model, duration) are trackable |
| CORE-STD-021 | MCP standard — future dispatch and cost query tools |

---

## 15. Self-Correction

Rondo captures data that enables consumer self-correction: cost trends, model performance, rate limit patterns. OB's CORE-STD-011 loop uses DispatchUsage history to learn optimal model routing. Rondo itself does not self-correct — it dispatches what it is told, faithfully.

---

## 16. Assumptions

1. Claude CLI supports `--output-format stream-json` with stable event format.
2. Claude CLI supports `--model` flag for model selection.
3. Rate limit information is available in stream-json events (not guaranteed for all plans).
4. Cost per token is calculated by the API, not by Rondo.

---

## 17. Success Criteria

| # | Criterion | How to Verify |
|---|-----------|---------------|
| 1 | Every dispatch produces a complete DispatchUsage with real token counts | Dispatch test |
| 2 | Model COALESCE resolves correctly at each priority level | COALESCE test |
| 3 | Rate limit detected → logged at WARNING, not crash | Rate limit test |
| 4 | Invalid model name → rejected before subprocess spawn | Validation test |

---

## 18. Build Notes / Estimate

Dispatch module: 6 hours (subprocess construction, stream-json parsing, DispatchUsage assembly). Model routing: 2 hours (COALESCE resolver, model allowlist). Rate limit handling: 2 hours. Multi-backend interface: 2 hours (abstract interface, Claude backend). Total: ~12 hours.

---

## 19. Test Categories

| Category | What It Tests |
|----------|--------------|
| Dispatch tests | Subprocess args, env stripping, stream-json parsing |
| Model routing tests | COALESCE resolution at each priority level |
| Rate limit tests | Detection, logging, DispatchUsage population |
| Cost tracking tests | DispatchUsage field accuracy from fixture data |

---

## 20. Failure Modes

| Failure | Impact | Mitigation |
|---------|--------|------------|
| Stream-json parse failure | Zeroed DispatchUsage (graceful) | Fallback path with WARNING log |
| Rate limit blocked | Dispatch fails, cost_usd=0 | Logged, consumer decides retry |
| Invalid model | Dispatch rejected | Validation before subprocess spawn |
| API key missing (api mode) | Subprocess fails immediately | Config validation at startup |

---

## 21. Dependencies + Used By

| Direction | Spec | Relationship |
|-----------|------|-------------|
| Depends on | CORE-STD-006 | Parent AI operations standard |
| Depends on | Rondo-STD-102 | Config provides model, auth, timeout |
| Depends on | CORE-STD-012 | Model availability prerequisites |
| Used by | Rondo-STD-101 | Observability captures DispatchUsage metrics |
| Used by | Rondo-STD-113 | Audit trail records dispatch details |
| Used by | Rondo-IFS-102 | OB ingests DispatchUsage |

---

## 22. Decisions

| Decision | Rationale | Date |
|----------|-----------|------|
| D1: Stream-json mandatory | Text mode estimates costs — stream-json gives actuals (ACE-STD-020 lesson) | 2026-03-18 |
| D2: No auto-retry | Retry is consumer responsibility. Rondo reports, consumers decide. | 2026-03-18 |
| D3: Multi-backend interface from day 1 | Even though v1.0 is Claude-only, the interface enables Gemini/Ollama later | 2026-03-18 |

---

## 23. Open Questions

1. Will Claude CLI stream-json format remain stable across major versions?
2. When Gemini/Ollama backends are added, will DispatchUsage fields cover their metric formats?

---

## 24. Glossary

| Term | Definition |
|------|-----------|
| **DispatchUsage** | Dataclass capturing per-dispatch metrics (tokens, cost, timing, rate limit) |
| **COALESCE** | First non-null value in a precedence chain wins — used for model selection |
| **Stream-json** | Claude CLI output format providing structured event stream |
| **Auth mode** | `max` (subscription) or `api` (pay-per-token) |

---

## 25. Risk / Criticality

**HIGH.** AI operations is Rondo's core value. Cost tracking errors affect budget decisions. Model routing errors affect result quality. Rate limit mishandling causes silent overnight failures. DispatchUsage accuracy is critical for OB's intelligence tracking.

---

## 26. External Scan

Anthropic Claude CLI is the primary backend. No industry-standard AI dispatch framework exists — Rondo is purpose-built. Multi-model routing draws from ML model serving patterns (TFServing, Seldon) adapted for local CLI dispatch.

---

## 27. Security Considerations

API key isolation: env var stripping based on auth mode (Rondo-STD-107 rules 16-19). Model allowlist prevents unauthorized model use. Cost caps prevent runaway API spend. See Rondo-STD-107 for full security requirements around AI dispatch.

---

## 28. Performance / Resource

Dispatch overhead: ~50ms (arg construction, env setup). Stream-json parsing: ~2ms. Total overhead per dispatch: <100ms — negligible compared to 10-300 second AI response time. Memory: DispatchUsage is <1KB per dispatch.

---

## 29. Approval Record

| Reviewer | Role | Date | Verdict |
|----------|------|------|---------|
| Mark Hubers | Owner | 2026-03-22 | Approved (Session 84) |

---

## 30. AI Review

Reviewed by Cold Witness panel. Results in `reports/ai-reviews/`. Fix-review-fix cycle applied.

---

## 31. AI Went Wrong

No implementation yet — tracks AI-generated code deviations during build.

---

## 32. AI Assumptions

During spec design, AI assumed: Postgres target DB, YAML schemas as source of truth, MCP as query interface.

---

## 33. AI Cost

Spec review cost tracked in `reports/ai-reviews/`. ~$0.10/review/body.

---

## 34. Notes

CORE-STD-012 (Requirement Readiness) tracks model availability as a dispatch prerequisite. CORE-STD-013 (TrackerData) records dispatch cost events for trend analysis. CORE-STD-021 MCP tools will expose dispatch and cost queries when Rondo-IFS-104 is built.

---

### Feature Maturity

| Feature | Maturity | Evidence | Retest |
|---------|----------|----------|--------|
| AI operation standards | THEORY | Specced for Rondo's own AI usage patterns | Phase 1 build |
| Token budget management | THEORY | Specced for per-task token limits | Phase 1 build |
| Model selection criteria | THEORY | Specced for choosing opus vs sonnet vs haiku | Phase 1 build |


## 35. Change History

| Version | Date | What Changed |
|---------|------|-------------|
| 0.1 | 2026-03-18 | Initial draft. Matches CORE-STD-006 topics (AI management, cost tracking, multi-model) adapted for Rondo as the dispatch layer. 26 requirements. COALESCE model routing, DispatchUsage field contract, rate limit handling, multi-backend future architecture, tool mode per task. |
| 0.2 | 2026-03-22 | Filled to 35 sections. Added CORE-STD-012, CORE-STD-013, CORE-STD-021 refs. Approval record (Mark, Session 84). |
