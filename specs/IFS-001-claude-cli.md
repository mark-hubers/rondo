# IFS-001: Claude Code CLI Interface

*The exact contract between Rondo and Claude Code's `claude -p` command.*

**Created:** 2026-03-13 | **Status:** DRAFT
**Classification:** open
**Depends on:** Claude Code CLI (Anthropic) | **Blocks:** REQ-001 (Core)
**Author:** Mark Hubers — HubersTech

---

## Item 1: Purpose & Scope

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
- Rondo's dispatch logic (REQ-001)
- Authentication with Anthropic's servers

---

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
| `--permission-mode` | `default`, `acceptEdits`, `plan`, `auto`, `bypassPermissions` | NO | auto |

**Permission mode:** Controls how Claude Code handles tool permission prompts during dispatch.
Since `claude -p` runs non-interactively (stdin disconnected), a permission prompt would hang
the subprocess until timeout kills it. `auto` lets Claude Code decide; `bypassPermissions`
skips all prompts (safest for unattended/overnight runs); `acceptEdits` auto-approves file
edits but still asks for other tools.

**Model variants:** The `[1m]` suffix enables the 1M token context window (vs 200K default).
Both Opus and Sonnet support `[1m]`. Available on Max plan at no extra cost.

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

Every dispatch receives this event for free — no extra API call needed.

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

## Requirements

Numbered requirements for VER-001 traceability:

1. Rondo MUST read stream-json output line by line, parsing each as a JSON object.
2. Rondo MUST extract `rate_limit_event` and populate `DispatchUsage` rate limit fields.
3. Rondo MUST extract `result` event and populate `DispatchUsage` cost/token/duration fields.
4. Rondo MUST extract `system:init` event and verify the model matches the requested model.
5. Rondo MUST verify that `system:init.model` matches the `--model` flag sent. Log warning on mismatch.
6. Rondo MUST capture `isUsingOverage` from `rate_limit_event` into `DispatchUsage.is_using_overage`.
7. Rondo MUST capture `total_cost_usd` from `result` event into `DispatchUsage.cost_usd`.
8. Rondo MUST capture `duration_ms` from `result` event into `DispatchUsage.duration_ms`.
9. Rondo MUST handle missing `rate_limit_event` gracefully — set rate limit fields to defaults (`status="unknown"`, `is_using_overage=False`).
10. Rondo MUST accept `[1m]` model suffix variants (e.g., `opus[1m]`, `sonnet[1m]`) as valid model names.

---

## Stream-JSON to Dataclass Mapping

How each stream-json event maps to Rondo's dataclasses (REQ-001, STD-020):

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

## Assumptions

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

---

## 2. The Problem

REQUIRED — fill before build.

---

## 4. Architecture/Design

REQUIRED — fill before build.

---

## 5. Data Model

REQUIRED — fill before build.

---

## 6. Data Boundary

REQUIRED — fill before build.

---

## 8. States & Modes

— if applicable.

---

## 9. Configuration

— if applicable.

---

## 10. Rules & Constraints

REQUIRED — fill before build.

---

## 11. Quality Attributes

— if applicable.

---

## 12. Shared Patterns

— if applicable.

---

## 13. Integration Points

REQUIRED — fill before build.

---

## 14. Foundation References

— if applicable.

---

## 15. Self-Correction

— if applicable.

---

## 17. Success Criteria

REQUIRED — fill before build.

---

## 18. Build Notes/Estimate

— filled during build.

---

## 19. Test Categories

— filled during build.

---

## 20. Failure Modes

— if applicable.

---

## 21. Dependencies + Used By

REQUIRED — fill before build.

---

## 22. Decisions

REQUIRED — fill before build.

---

## 23. Open Questions

— if applicable.

---

## 24. Glossary

— if applicable.

---

## 25. Risk/Criticality

— if applicable.

---

## 26. External Scan

— if applicable.

---

## 27. Security Considerations

— if applicable.

---

## 28. Performance/Resource

— if applicable.

---

## 29. Approval Record

— filled after build.

---

## 30. AI Review

— filled after build.

---

## 31. AI Went Wrong

— filled during build.

---

## 32. AI Assumptions

— filled during build.

---

## 33. AI Cost

— filled during build.

---

## 34. Notes

— filled after build.

---

## 35. Change History

| Version | Date | What Changed |
|---------|------|-------------|
| 0.1 | 2026-03-13 | Initial interface documentation |
| 0.2 | 2026-03-14 | Added stream-json output format, rate_limit_event, result metadata, 1M context, 4 new assumptions |
| 0.3 | 2026-03-14 | Deep review fixes: added 10 numbered requirements, stream-json-to-dataclass mapping tables (rate_limit_event→DispatchUsage, result→DispatchUsage, assistant→TaskResult) |
| 0.4 | 2026-03-14 | Added `--permission-mode` to invocation table — controls tool access prompts in non-interactive dispatch |
