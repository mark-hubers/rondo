# STD-006: AI Operations

*How Rondo dispatches to AI models, tracks costs, handles rate limits, and supports multi-model routing. Rondo IS the dispatch layer.*

**Created:** 2026-03-18 | **Status:** DESIGNED
**Universal standard** — same topic number across all products (DEC-017)
**Product:** Rondo
**Matches:** OB-STD-006, Caliber-STD-006

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
- Independent AI review protocol (OB-STD-006 domain — OB manages reviewer independence)
- Attention budget tiers (OB-STD-006 domain — consumers decide context budgets)
- Spec digest format (OB-STD-006 domain — Rondo dispatches prompts, not specs)
- AI self-correction loops (OB-STD-004 domain)

---

## 3. Requirements

### Model Selection

1. Model selection follows the COALESCE chain: CLI `--model` flag > `task.model` hint > `config.dispatch.default_model` > `"sonnet"` hardcoded fallback.
2. Rondo passes `--model {model}` to the `claude -p` subprocess. Model names match Claude Code CLI values: `opus`, `sonnet`, `haiku`.
3. Round definitions tag each task with a recommended model based on task complexity. Simple tasks (file counting, format checks) use `haiku`. Complex tasks (architecture review, code generation) use `opus`. Default is `sonnet`.
4. Model validation at dispatch: if the resolved model is not in the known model list, fail with error_code `CONFIG_INVALID_MODEL` before spawning the subprocess.
5. The known model list is maintained in `config.py`, not hardcoded per-file. When Claude releases new models, update one list.

### Cost Tracking (DispatchUsage)

6. Every AI dispatch MUST produce a `DispatchUsage` object with these fields (per NAMING-MAP.md):

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

7. DispatchUsage field names MUST match NAMING-MAP.md exactly. When OB stores Rondo results, it maps `DispatchUsage.cost_usd` to `sprint_intelligence.cost_usd` — same name, zero translation.
8. If stream-json parsing fails (STD-002 rule 11), create a DispatchUsage with zeroed token fields and `cost_usd = 0.0`. Never skip the DispatchUsage object — consumers depend on it existing.
9. Round-level cost summary: `sum(usage.cost_usd for usage in round_result.usage)` gives total round cost. This is computed by the consumer, not stored redundantly by Rondo.

### Rate Limit Handling

10. Stream-json emits `rate_limit_event` with current usage status. Rondo captures: `rate_limit_status` ("allowed" or "blocked"), `is_using_overage`, and `rate_limit_resets_at` (epoch timestamp).
11. When rate limit status is "blocked": log at WARNING, record in DispatchUsage, and let the consumer decide whether to retry later. Rondo does NOT auto-retry on rate limits (STD-002 rule 17).
12. Rate limit information is per-dispatch, not per-round. Different tasks may hit different rate limit states depending on timing.
13. For overnight automation (REQ-002): the scheduler reads rate limit status from the previous dispatch and can pause between phases to wait for reset. This is scheduler logic, not dispatch logic.

### Context Window Awareness

14. Rondo captures `context_window` from stream-json (200K standard or 1M extended). This is informational — Rondo does not manage context budgets (OB does that).
15. If a task consistently hits context limits (output truncated, errors about context), log at WARNING with the task name and context window size. The consumer should reduce the prompt or use a larger context model.
16. Rondo does NOT pre-calculate prompt token counts. Token counting is model-specific and changes with each API version. Let Claude handle it — Rondo captures the actuals from stream-json.

### Multi-Model Support

17. Current support: Claude Code CLI (`claude -p`). This is the only backend for v1.0.
18. Future backends (Gemini, Ollama) will be added as separate dispatch modules. The dispatch interface is:
    - Input: task prompt (str), model hint (str), config (RondoConfig)
    - Output: TaskResult + DispatchUsage
    - Each backend implements this interface
19. Model-to-backend routing: the `model` field determines which backend dispatches the task. Claude models (opus, sonnet, haiku) use `claude -p`. Future: gemini models use the Gemini API, ollama models use the local Ollama API.
20. Backend selection is transparent to round definitions. A round says `model="sonnet"` — it does not say "use Claude." The dispatch layer resolves model to backend.

### Dispatch Protocol

21. The prompt template wraps the task's three-field contract (Do/Read/Done) with output format instructions. The template is standardized — all tasks get the same framing.
22. Dispatch MUST pass `--output-format stream-json` to capture real metrics. Text mode is never used (F20 lesson: estimated costs were inaccurate).
23. Dispatch MUST pass `--permission-mode {mode}` from the config's `permission_mode` field. Default: `auto`.
24. For code generation tasks (`tool_mode: "none"`): dispatch passes `--tools ""` to disable file tools.
25. For code fixing tasks (`tool_mode: "sandbox"`): dispatch passes `--dangerously-skip-permissions` (containers only, no internet).
26. Tool mode MUST be specified per task in the round definition. Default: `"default"` (Claude decides which tools to use).

---

## 10. Rules & Constraints

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
| Model selection | COALESCE chain, pass to CLI | N/A — trusts Rondo |
| Cost tracking | DispatchUsage per task | Stores in sprint_intelligence |
| Rate limits | Detect and report | Decide retry strategy |
| Context budget | Capture actual from stream-json | Define budget tiers, manage digests |
| Independent review | N/A — dispatches what it's told | Enforces Context Asymmetry |
| Token reduction | N/A — sends the prompt as-is | Builds spec digests before sending |

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

## 35. Change History

| Version | Date | What Changed |
|---------|------|-------------|
| 0.1 | 2026-03-18 | Initial draft. Matches OB-STD-006 topics (AI management, cost tracking, multi-model) adapted for Rondo as the dispatch layer. 26 requirements. COALESCE model routing, DispatchUsage field contract, rate limit handling, multi-backend future architecture, tool mode per task. |
