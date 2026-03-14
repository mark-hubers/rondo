# IFS-001: Claude Code CLI Interface

*The exact contract between Rondo and Claude Code's `claude -p` command.*

**Created:** 2026-03-13 | **Status:** DRAFT
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
claude -p <prompt> [--model <model>] [--effort <effort>] [--output-format <format>]
```

| Flag | Values | Required | Default |
|------|--------|----------|---------|
| `-p` | Prompt text (string) | YES | — |
| `--model` | `opus`, `sonnet`, `haiku`, `opus[1m]`, `sonnet[1m]` | NO | sonnet |
| `--effort` | `low`, `medium`, `high`, `max` | NO | high |
| `--output-format` | `text`, `json`, `stream-json` | NO | text |

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

## Change History

| Version | Date | What Changed |
|---------|------|-------------|
| 0.1 | 2026-03-13 | Initial interface documentation |
| 0.2 | 2026-03-14 | Added stream-json output format, rate_limit_event, result metadata, 1M context, 4 new assumptions |
