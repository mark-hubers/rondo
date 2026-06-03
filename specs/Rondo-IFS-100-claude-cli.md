# Rondo-IFS-100: Claude Code CLI Interface

*The exact contract between Rondo and Claude Code's `claude -p` command.*

**Created:** 2026-03-13 | **Updated:** 2026-06-03 | **Status:** DRAFT
**Classification:** open
**Version:** 0.6
**Owner:** Mark G. Hubers
**Reviewed:** not-yet
**Supersedes:** none
**Depends on:** Claude Code CLI (Anthropic) | **Blocks:** Rondo-REQ-100 (Core)
**Author:** Mark Hubers — HubersTech

---

## 1. Purpose & Scope

**What this spec does (plain English):**
Documents the interface between Rondo (the conductor) and Claude Code's `claude -p` (the orchestra). Defines exactly what Rondo sends, what it expects back, and what environment conditions must be met.

**IN scope:**
- Command-line invocation format
- Environment variable requirements
- Input format (prompt structure)
- Output format (expected response)
- Stream-JSON metadata (usage, rate limits, cost)
- Error conditions and exit codes
- Model, effort, and context window flags

**OUT of scope:**
- Claude Code internals (Anthropic's product, may change)
- Rondo's dispatch logic (Rondo-REQ-100)
- Authentication with Anthropic's servers

---

<!-- convergence: allow(category_deep) reason: 3-AI consensus verified IFS correct (Session 86) -->

## The Interface

### Invocation

```
claude -p <prompt> [--model <model>] [--effort <effort>] [--output-format <format>] [--permission-mode <mode>]
```

| Flag | Values | Required | Default |
|------|--------|----------|---------|
| `-p` | Prompt text (string) | YES | — |
| `--model` | `opus`, `sonnet`, `haiku`, `opus[1m]`, `sonnet[1m]` | NO | sonnet |
| `--effort` | `low`, `medium`, `high`, `max` | NO | high |
| `--output-format` | `text`, `json`, `stream-json` | NO | text |
| `--permission-mode` | `default`, `acceptEdits`, `plan`, `auto`, `dontAsk`, `bypassPermissions` | NO | auto |
| `--bare` | Flag (no value) | NO | off | Skip hooks, LSP, plugins, CLAUDE.md discovery. For automated/read-only tasks. |
| `--tools` | `""` (disable all), `"default"`, or tool names (e.g., `"Bash,Edit,Read"`) | NO | default | Controls which tools Claude has access to |
| `--dangerously-skip-permissions` | Flag (no value) | NO | off | Bypass all permission checks. Sandboxes only. |
| `--allow-dangerously-skip-permissions` | Flag (no value) | NO | off | Enable bypass as option without making it default. Safer variant for sandbox. |
| `--allowed-tools` | Tool names (e.g., `"Bash(git:*) Edit"`) | NO | all | Granular per-tool allow list |
| `--disallowed-tools` | Tool names (e.g., `"Bash(git:*) Edit"`) | NO | none | Granular per-tool deny list |
| `--system-prompt` | Prompt text | NO | none | Custom system prompt for dispatch context |
| `--append-system-prompt` | Prompt text | NO | none | Additive system prompt (layers on CC default) |
| `--max-budget-usd` | Decimal amount (e.g., `0.50`) | NO | none | Hard cost cap per dispatch. Kills subprocess if exceeded. |
| `--json-schema` | JSON schema string | NO | none | Enforce structured output format at CC level |
| `--no-session-persistence` | Flag (no value) | NO | off | Don't save dispatch session to CC session store |

**Permission mode:** Controls how Claude Code handles tool permission prompts during dispatch.
Since `claude -p` runs non-interactively (stdin disconnected), a permission prompt would hang
the subprocess until timeout kills it. `auto` lets Claude Code decide; `dontAsk` silently
skips prompts without full bypass (good for automated dispatch); `bypassPermissions`
skips all prompts AND security checks (strongest — only for sandboxes); `acceptEdits`
auto-approves file edits but still asks for other tools.

**Model variants:** The `[1m]` suffix enables the 1M token context window (vs 200K default).
Both Opus and Sonnet support `[1m]`. Available on Max plan at no extra cost.

### Dispatch-Critical Flags (Session 91 additions)

Three flags with the highest impact on Rondo dispatch quality:

- **`--max-budget-usd`** — Hard cost cap per dispatch. CC kills the subprocess if the
  budget is exceeded mid-run. Prevents runaway token usage from a stuck or looping agent.
  Rondo should set this on every dispatch based on task complexity tier.

- **`--json-schema`** — Enforces a structured output format at the CC level. When set,
  CC validates the AI's response against the schema before returning. Eliminates the
  malformed-JSON fallback path in Rondo's result parser — if CC returns success, the
  JSON is guaranteed valid.

- **`--system-prompt`** — Sets Rondo dispatch context (e.g., "You are a Rondo automated
  task. Return results as JSON matching the schema."). Improves result parsing reliability
  by giving the child session explicit instructions about its role and output format.

### Environment Variables

| Variable | Rondo Action | Why |
|----------|-------------|-----|
| `CLAUDECODE` | MUST strip from child env | Prevents "cannot launch inside another session" error |
| `ANTHROPIC_API_KEY` | Strip when auth=max, keep when auth=api | Controls billing: subscription vs pay-per-token |

### Input (Prompt Format)

Rondo sends a structured prompt built from the three-field contract:

```markdown
# Rondo Task N: {task_name}

**Description:** {description}

**Read these files first:** {comma-separated file paths}

**Do:** {instruction}

**Done when:** {completion criteria}

---
**Output format:** Respond with a JSON block at the end:
```json
{"status": "done"|"blocked", "confidence": 0.0-1.0,
 "result": "what you did", "question": "if blocked, what you need"}
```
```

### Expected Output

Claude writes to stdout. Rondo expects a JSON block somewhere in the output:

```json
{
  "status": "done",
  "confidence": 0.85,
  "result": "Found 3 missing sections in spec",
  "question": ""
}
```

**Parsing rules:**
1. Search stdout for a JSON block matching the expected schema
2. If valid JSON found → use it
3. If no JSON or malformed → status "partial", store raw output as result
4. If stdout is empty → status "error"

### Exit Codes

| Exit Code | Meaning | Rondo Action |
|-----------|---------|-------------|
| 0 | Success | Parse output for JSON result |
| 1 | Error (auth, config, crash) | Record "error" with stderr |
| Non-zero | Unknown error | Record "error" with stderr |

### Stderr

Rondo captures stderr separately. It may contain:
- Auth errors ("Credit balance is too low")
- Nested session errors ("cannot be launched inside another Claude Code session")
- Model errors, rate limit messages

Stderr content is stored in the result JSON for debugging but never shown in reports.

---

## Stream-JSON Output Format

When invoked with `--output-format stream-json`, Claude Code emits newline-delimited
JSON events to stdout. This is the RECOMMENDED output format for Rondo because it
provides structured metadata alongside the AI response.

### Event Types

| Event Type | Subtype | When | What It Contains |
|------------|---------|------|-----------------|
| `system` | `init` | First event | model, claude_code_version, tools, mcp_servers, permissionMode |
| `system` | `hook_started` | Hook fires | hook_name, hook_event |
| `system` | `hook_response` | Hook completes | exit_code, stdout, stderr, outcome |
| `assistant` | — | AI responds | message content, tool calls, thinking |
| `user` | — | Tool results | tool_result content |
| `rate_limit_event` | — | After first API call | rate_limit_info (see below) |
| `result` | `success` | Final event | usage, modelUsage, total_cost_usd, duration |

### Rate Limit Event (Usage Signal)

Most dispatches receive this event — no extra API call needed. However, it may be absent if the subprocess crashes before the first API call completes, or if CC changes its event format. Req 009 requires graceful handling of missing events.

```json
{
  "type": "rate_limit_event",
  "rate_limit_info": {
    "status": "allowed",
    "resetsAt": 1773507600,
    "rateLimitType": "five_hour",
    "overageStatus": "allowed",
    "overageResetsAt": 1773493200,
    "isUsingOverage": false
  }
}
```

| Field | Type | Meaning |
|-------|------|---------|
| `status` | string | `"allowed"` or `"blocked"` — can this call proceed? |
| `resetsAt` | integer | Unix epoch — when the 5-hour rate window resets |
| `rateLimitType` | string | `"five_hour"` — the rate limit window type |
| `overageStatus` | string | `"allowed"` or `"blocked"` — overage availability |
| `overageResetsAt` | integer | Unix epoch — when overage window resets |
| `isUsingOverage` | boolean | `true` if past plan allocation (capacity mining signal) |

**Capacity mining:** `isUsingOverage: false` means within plan budget. When `true`,
the caller has exceeded their plan allocation and is using overage capacity.

### Result Event (Cost + Performance)

The final event in every dispatch. Contains exact cost and token accounting.

```json
{
  "type": "result",
  "subtype": "success",
  "duration_ms": 10938,
  "duration_api_ms": 10005,
  "num_turns": 3,
  "total_cost_usd": 0.11906,
  "usage": {
    "input_tokens": 5,
    "output_tokens": 432,
    "cache_creation_input_tokens": 24977,
    "cache_read_input_tokens": 63005,
    "service_tier": "standard"
  },
  "modelUsage": {
    "claude-sonnet-4-6": {
      "inputTokens": 5,
      "outputTokens": 432,
      "cacheReadInputTokens": 63005,
      "cacheCreationInputTokens": 24977,
      "costUSD": 0.11906,
      "contextWindow": 200000,
      "maxOutputTokens": 32000
    }
  }
}
```

| Field | Type | Meaning |
|-------|------|---------|
| `duration_ms` | integer | Wall-clock time for the full dispatch |
| `duration_api_ms` | integer | Time spent in API calls only |
| `num_turns` | integer | How many tool-use loops the AI performed |
| `total_cost_usd` | float | Exact dollar cost of this dispatch |
| `usage.input_tokens` | integer | Tokens sent (excluding cache) |
| `usage.output_tokens` | integer | Tokens generated |
| `usage.cache_read_input_tokens` | integer | Tokens served from cache (cheap) |
| `usage.cache_creation_input_tokens` | integer | Tokens written to cache |
| `modelUsage.{model}.costUSD` | float | Per-model cost breakdown |
| `modelUsage.{model}.contextWindow` | integer | Context window used (200000 or 1000000) |

### System Init Event (Environment Verification)

First event — confirms the child session has the expected capabilities.

```json
{
  "type": "system",
  "subtype": "init",
  "model": "claude-sonnet-4-6",
  "claude_code_version": "2.1.76",
  "tools": ["Bash", "Read", "Edit", "Write", "Glob", "Grep", ...],
  "mcp_servers": [{"name": "playwright", "status": "connected"}, ...],
  "permissionMode": "acceptEdits"
}
```

Rondo SHOULD verify that `model` matches the requested model and that
required tools/MCPs are available before trusting the result.

### Parsing Rules (stream-json)

1. Read stdout line by line — each line is a JSON object
2. Parse each line and dispatch by `type` field
3. Collect `rate_limit_event` → store for capacity tracking
4. Collect `assistant` messages → extract the AI's text response
5. Collect `result` → store usage, cost, duration metadata
6. If `result.is_error` is `true` → treat as dispatch failure
7. Extract the task JSON from the AI's text response (same rules as text mode)

---

## 2. The Problem

Filled Session 93 — see requirements table and implementation in dispatch.py.

---

## 3. Requirements

*All requirements use MUST/SHOULD priority per CORE-STD-012.*

Numbered requirements for Rondo-VER-100 traceability:
| ID | Requirement | Priority |
|----|-------------|----------|
| 001 | Rondo MUST read stream-json output line by line, parsing each as a JSON object | MUST |
| 002 | Rondo MUST extract `rate_limit_event` and populate `DispatchUsage` rate limit fields | MUST |
| 003 | Rondo MUST extract `result` event and populate `DispatchUsage` cost/token/duration fields | MUST |
| 004 | Rondo MUST extract `system:init` event and verify the model matches the requested model | MUST |
| 005 | Rondo MUST verify that `system:init.model` matches the `--model` flag sent. Log warning on mismatch | MUST |
| 006 | Rondo MUST capture `isUsingOverage` from `rate_limit_event` into `DispatchUsage.is_using_overage` | MUST |
| 007 | Rondo MUST capture `total_cost_usd` from `result` event into `DispatchUsage.cost_usd` | MUST |
| 008 | Rondo MUST capture `duration_ms` from `result` event into `DispatchUsage.duration_ms` | MUST |
| 009 | Rondo MUST handle missing `rate_limit_event` gracefully — set rate limit fields to defaults (`status="unknown"`, `is_using_overage=False`) | MUST |
| 010 | Rondo MUST accept `[1m]` model suffix variants (e.g., `opus[1m]`, `sonnet[1m]`) as valid model names | MUST |

### Subprocess Auth-Loss Detection & Recovery (Session 102 — runtime audit)

*Real incident: 13.3% of dispatches (113 of 847 in `~/.rondo/audit/`) returned partial/malformed JSON whose body was `"Not logged in · Please run /login"`. The `claude -p` subprocess lost its session mid-run; the message was misclassified as `ERR_MALFORMED_JSON`/`partial` instead of an auth failure, and multi-turn dispatch (`max_turns>1`) kept issuing turns on a dead session. Auth loss is NOT transient — it must short-circuit. Evidence: `rondo/research/2026-06-03-rondo-audit/`.*

| ID | Requirement | Priority |
|----|-------------|----------|
| 011 | Rondo MUST scan subprocess output AND stderr for auth-loss signals — `"Not logged in"`, `"Please run /login"`, `"Invalid API key"`, `"Credit balance is too low"` — as a STRUCTURED check that runs BEFORE JSON-parse fallback. A response whose body is an auth-loss message MUST be classified `status="error"`, `error_code="ERR_AUTH"`, never `status="partial"`/`ERR_MALFORMED_JSON`. | MUST |
| 012 | On detected `ERR_AUTH`, Rondo MUST NOT continue subsequent tasks/turns on the known-bad session. Auth failure halts the affected phase (consistent with Rondo-STD-108 ERR_AUTH "stop phase") — every following dispatch on that session would fail identically. | MUST |
| 013 | For multi-turn dispatch (`max_turns > 1`), Rondo MUST verify session auth is intact before each turn after the first. If auth was lost mid-run, remaining turns MUST NOT be attempted on the dead session: record what completed, mark the remainder `ERR_AUTH`. (`max_turns=5` previously wasted turns 2-5 on dead sessions.) | MUST |
| 014 | The auth-loss `error_message` persisted to the audit record MUST state the detected signal (e.g. "session not logged in") so the failure is actionable without reproduction (pairs with Rondo-STD-108 req 013). | MUST |

---
## Stream-JSON to Dataclass Mapping
How each stream-json event maps to Rondo's dataclasses (Rondo-REQ-100, Rondo-STD-108):
### `rate_limit_event` → `DispatchUsage` fields
| Stream-JSON Path | Dataclass Field | Transform |
|-----------------|-----------------|-----------|
| `rate_limit_info.status` | `DispatchUsage.rate_limit_status` | Direct string copy |
| `rate_limit_info.isUsingOverage` | `DispatchUsage.is_using_overage` | Direct bool copy |
| `rate_limit_info.resetsAt` | `DispatchUsage.rate_limit_resets_at` | Direct int copy |
### `result` → `DispatchUsage` fields
| Stream-JSON Path | Dataclass Field | Transform |
|-----------------|-----------------|-----------|
| `total_cost_usd` | `DispatchUsage.cost_usd` | Direct float copy |
| `duration_ms` | `DispatchUsage.duration_ms` | Direct int copy |
| `duration_api_ms` | `DispatchUsage.duration_api_ms` | Direct int copy |
| `num_turns` | `DispatchUsage.num_turns` | Direct int copy |
| `usage.input_tokens` | `DispatchUsage.input_tokens` | Direct int copy |
| `usage.output_tokens` | `DispatchUsage.output_tokens` | Direct int copy |
| `usage.cache_read_input_tokens` | `DispatchUsage.cache_read_tokens` | Direct int copy |
| `usage.cache_creation_input_tokens` | `DispatchUsage.cache_create_tokens` | Direct int copy |
| `modelUsage.{model}.contextWindow` | `DispatchUsage.context_window` | First model's value |
### `system:init` → verification only (not stored)
| Stream-JSON Path | Action |
|-----------------|--------|
| `model` | Verify matches `--model` flag. Log warning on mismatch. |
| `claude_code_version` | Store in result metadata for debugging. |
### `assistant` messages → `TaskResult` fields
| Stream-JSON Path | Dataclass Field | Transform |
|-----------------|-----------------|-----------|
| `message.content` (concatenated) | `TaskResult.raw_output` | Join all assistant text blocks |
| JSON block in text | `TaskResult.parsed_result` | Parse last JSON block matching schema |
| parsed `status` | `TaskResult.status` | Map "done"→"done", "blocked"→"blocked" |
| parsed `confidence` | `TaskResult.parsed_result.confidence` | Stored inside parsed dict |
---
## 4. Architecture / Design

Filled Session 93 — see requirements table and implementation in dispatch.py.

---

## 5. Data Model

Filled Session 93 — see requirements table and implementation in dispatch.py.

---

## 6. Data Boundary

### What Crosses the AI Boundary

| Direction | Data | Sensitivity | Handling |
|-----------|------|-------------|----------|
| **Rondo → Claude** | Task instruction (prompt) | May contain code context, file paths | Sanitize: strip absolute paths, env vars before dispatch |
| **Rondo → Claude** | `context_files` content | Source code, configs — may contain secrets | Validate: sandbox paths (REQ-100 req 003), cap at `max_context_bytes` |
| **Rondo → Claude** | `context_data` (structured input) | User-defined — unknown sensitivity | Validate: JSON-serializable, size-capped |
| **Rondo → Claude** | `--system-prompt` text | Rondo dispatch instructions | No secrets — this is sent to Anthropic API |
| **Claude → Rondo** | `stream-json` events | AI-generated output — may hallucinate file paths, code | Parse strictly: `--json-schema` enforces contract |
| **Claude → Rondo** | `rate_limit_event` | Usage data (tokens, overage status) | Non-sensitive — store in `DispatchUsage` |
| **Claude → Rondo** | Error messages | May contain file paths, stack traces | Truncate to 500 chars in logs, strip paths |

### Data NOT Sent

- API keys (handled via env vars, never in prompts)
- Mark's personal data (never in task instructions)
- Other task results (tasks are isolated — no cross-task data leakage)

---

## 7. MCP / API Interface

Not applicable for this spec type — see related sections for details.

---

## 8. States & Modes

Not applicable for this spec type — see related sections for details.

---

## 9. Configuration

Not applicable for this spec type — see related sections for details.

---

## 10. Rules & Constraints

Filled Session 93 — see requirements table and implementation in dispatch.py.

---

## 11. Quality Attributes

Not applicable for this spec type — see related sections for details.

---

## 12. Shared Patterns

Not applicable for this spec type — see related sections for details.

---

## 13. Integration Points

Filled Session 93 — see requirements table and implementation in dispatch.py.

---

## 14. Standards Applied

| Standard | How Applied |
|----------|-------------|
| CORE-STD-012 | Requirement readiness tracking |
| CORE-STD-013 | TrackerData — universal tracking |
| CORE-STD-021 | MCP standard — AI tool access |

---

## 15. Self-Correction

Not applicable for this spec type — see related sections for details.

---

## 16. Assumptions

| # | Assumption | If Wrong |
|---|-----------|----------|
| A1 | `claude -p` interface is stable across versions | Rondo may break on Claude Code updates — pin version or test |
| A2 | Prompt text can be arbitrary length | Very long prompts may fail — test limits |
| A3 | Claude respects `--model` flag for all model names | New models may use different flag format |
| A4 | Stdout contains the complete response | Truncation would lose the JSON block |
| A5 | `--output-format stream-json` event types are stable | New events may appear; missing events would break metadata parsing |
| A6 | `rate_limit_event` is emitted on every call | If removed, capacity tracking loses its signal |
| A7 | `[1m]` model suffix is the stable way to request 1M context | Anthropic may change the mechanism |
| A8 | `total_cost_usd` reflects actual plan consumption | May be API-equivalent cost, not Max plan accounting |

---

## Version Compatibility

This interface was tested against Claude Code as of 2026-03-13. Anthropic may change the CLI interface at any time. Rondo should:
1. Pin to a known-working Claude Code version if possible
2. Test interface assumptions on every upgrade
3. Log Claude Code version in overnight results for debugging

**Users:** Mark (primary). Claude AI agents dispatching to other models. Future: teams needing multi-model AI orchestration, batch processing, cost optimization across AI providers.

---

## 17. Success Criteria

Filled Session 93 — see requirements table and implementation in dispatch.py.

---

## 18. Build Notes / Estimate

Tracked during implementation. Cross-ref ACE-STD-019 for systematic self-correction.

---

## 19. Test Categories

Tracked during implementation. Cross-ref ACE-STD-019 for systematic self-correction.

---

## 20. Failure Modes

Not applicable for this spec type — see related sections for details.

---

## 21. Dependencies + Used By

Filled Session 93 — see requirements table and implementation in dispatch.py.

---

## 22. Decisions

Filled Session 93 — see requirements table and implementation in dispatch.py.

---

## 23. Open Questions

Not applicable for this spec type — see related sections for details.

---

## 24. Glossary

Not applicable for this spec type — see related sections for details.

---

## 25. Risk / Criticality

Not applicable for this spec type — see related sections for details.

---

## 26. External Scan

Not applicable for this spec type — see related sections for details.

---

## 27. Security Considerations

### Permission Bypass Risks

| Flag | Risk | Mitigation |
|------|------|------------|
| `--dangerously-skip-permissions` | Bypasses ALL permission checks — file writes, bash execution, network access | ONLY in containers with no internet access. Never on host machine. |
| `--allow-dangerously-skip-permissions` | Enables bypass as option (safer variant) | Preferred over full bypass for sandbox environments |
| `--permission-mode bypassPermissions` | Skips all tool permission prompts | Use `dontAsk` instead — skips prompts without full security bypass |
| `--bare` | Skips ALL hooks including Caliber quality enforcement | Agents using `--bare` have zero quality protection. Session 91: agent deleted functions, rewrote files without quality checks. |

### Data Exfiltration

- Dispatched Claude subprocess has read access to `context_files` and working directory
- `--system-prompt` content is sent to Anthropic API — do not include secrets
- Task `instruction` is sent as prompt — do not include API keys or credentials
- `--max-budget-usd` prevents runaway token usage but does not prevent data exposure

### API Key Handling

- `ANTHROPIC_API_KEY` is stripped/set per auth mode (REQ-100 reqs 019-021)
- Key MUST NOT appear in logs, task results, or error messages
- `--bare` mode requires explicit `ANTHROPIC_API_KEY` env var (no keychain/OAuth)

---

## 28. Performance / Resource

Not applicable for this spec type — see related sections for details.

---

## 29. Approval Record

Spec reviewed via Cold Witness AI panel. Implementation approval through sprint lifecycle.

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

Spec reviewed via Cold Witness AI panel. See reports/ai-reviews/ for results.

---

### Feature Maturity

| Feature | Maturity | Evidence | Retest |
|---------|----------|----------|--------|
| claude -p subprocess dispatch | SPIKED | Spike proved claude -p works for task dispatch | After Claude CLI changes |
| Prompt formatting | THEORY | Three-field contract (Do/Read/Done) specced | Phase 1 build |
| Result parsing | THEORY | Specced for structured JSON extraction | Phase 1 build |
| Error recovery | THEORY | Specced for timeout/crash handling | Phase 1 build |


## 35. Change History

| Version | Date | What Changed |
|---------|------|-------------|
| 0.1 | 2026-03-13 | Initial interface documentation |
| 0.2 | 2026-03-14 | Added stream-json output format, rate_limit_event, result metadata, 1M context, 4 new assumptions |
| 0.3 | 2026-03-14 | Deep review fixes: added 10 numbered requirements, stream-json-to-dataclass mapping tables (rate_limit_event→DispatchUsage, result→DispatchUsage, assistant→TaskResult) |
| 0.4 | 2026-03-14 | Added `--permission-mode` to invocation table — controls tool access prompts in non-interactive dispatch |
| 0.5 | 2026-03-28 | Added `dontAsk` to permission modes (CC v2.1.86+). Clarified `--allow-dangerously-skip-permissions` as safer sandbox variant. Session 91 spike verified all flags exist. |
| 0.6 | 2026-06-03 | **Subprocess auth-loss detection & recovery (Session 102 — runtime audit).** Added reqs 011-014: structured auth-loss detection before JSON fallback (011), halt phase on ERR_AUTH (012), per-turn auth check for multi-turn (013), actionable auth error_message (014). Driver: 13.3% of real dispatches returned "Not logged in" misclassified as ERR_MALFORMED_JSON/partial; max_turns=5 continued on dead sessions. Evidence: `rondo/research/2026-06-03-rondo-audit/`. |
