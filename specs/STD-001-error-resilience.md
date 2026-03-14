# STD-001: Error Handling & Resilience

*How Rondo handles failures — subprocess crashes, bad output, timeouts.*

**Created:** 2026-03-13 | **Updated:** 2026-03-14 | **Status:** DRAFT
**Depends on:** IFS-001 (exit codes, stderr) | **Blocks:** REQ-001 (Dispatch)
**Author:** Mark Hubers — HubersTech

---

## Item 1: Purpose & Scope

**What this spec does (plain English):**
Defines how Rondo handles every type of failure that can occur during unattended AI
task dispatch. Every failure must be captured, categorized, recorded, and survivable.
No silent failures. No crashes from bad output. No hung processes.

**IN scope:**
- Error categories and status codes
- Error result structure (what every failure record contains)
- Recovery behavior per error type
- Credential safety in error output
- Timeout and kill behavior

**OUT of scope:**
- Retry logic (caller's responsibility — Rondo reports, caller decides)
- Notification/alerting (REQ-002 morning report surfaces failures)
- Error storage backend (REQ-001 defines result file format)

---

## Principle

Rondo runs unattended. Every failure must be captured, recorded, and survivable.
No silent failures. No crashes from bad subprocess output. No hung processes
blocking the pipeline.

---

## Rules

1. Every task result (success or failure) MUST include: task name, status, error
   message (if any), wall-clock duration, and the prompt that was sent.
2. Subprocess errors (exit code != 0) MUST be distinguishable from task-logic
   errors (Claude returned "blocked") in the result JSON.
3. If Claude returns malformed JSON, dispatch MUST fall back to raw output with
   status "partial" — never discard good work because parsing failed.
4. Subprocess timeouts MUST be configurable. Default: 5 minutes per task.
5. A timed-out subprocess MUST be killed (`SIGTERM`, then `SIGKILL` after 5s)
   and recorded as status "error" with reason "timeout".
6. A single task failure MUST NOT crash the framework or affect other tasks.
7. In overnight mode, a failed phase MUST NOT block subsequent phases.
8. API keys, tokens, and credentials MUST NEVER appear in result files or error logs.
9. All exceptions in dispatch MUST be caught, logged with context, and converted
   to error results — no unhandled exceptions escape the dispatch layer.
10. The morning report MUST always be generated — even if all phases fail.
    "Everything failed" is useful information.

---

## Error Status Codes

Every task result has a `status` field. These are the only valid values:

| Status | Meaning | Source |
|--------|---------|--------|
| `done` | Task completed successfully | Claude returned valid JSON with status "done" |
| `blocked` | Task could not proceed | Claude returned "blocked" with a question |
| `partial` | Got output but couldn't parse JSON | Malformed JSON fallback |
| `error` | Dispatch-level failure | Subprocess crash, timeout, auth failure |
| `skipped` | Task not attempted | Pre-gate blocked the round |

**State is terminal.** Once a task has a status, it does not change (unless
resumed from serialized state in a new run).

---

## Error Categories

| Code | Category | Exit Code | Recovery | Example |
|------|----------|-----------|----------|---------|
| `ERR_SUBPROCESS` | Subprocess crash | != 0 | Log stderr, continue | Segfault, OOM |
| `ERR_EMPTY_OUTPUT` | No stdout | 0 | Log, flag auth check | Auth expired silently |
| `ERR_MALFORMED_JSON` | Unparseable response | 0 | Use raw output as result | Claude didn't follow format |
| `ERR_TIMEOUT` | Exceeded time limit | — | Kill process, log duration | Complex task hung |
| `ERR_AUTH` | Authentication failure | 1 | Log, stop phase (all tasks will fail) | Invalid key, expired session |
| `ERR_GATE` | Pre-gate check failed | — | Skip round, log reason | Prerequisite not met |
| `ERR_NETWORK` | Connection failure | 1 | Log, continue | DNS failure, API unreachable |
| `ERR_NESTED_SESSION` | CLAUDECODE not stripped | 1 | Log, fix env stripping | "Cannot launch inside another session" |
| `ERR_RATE_LIMIT` | Rate limited by Anthropic | 1 | Log, pause or stop | "Rate limit reached" |
| `ERR_INTERNAL` | Bug in Rondo itself | — | Log full traceback, continue | Unhandled exception |

---

## Error Result Structure

Every task result — success or failure — uses this structure:

```python
@dataclass
class TaskResult:
    task_name: str               # -- which task
    status: str                  # -- done, blocked, partial, error, skipped
    error_code: str | None       # -- ERR_TIMEOUT, ERR_AUTH, etc. (None on success)
    error_message: str | None    # -- human-readable failure description
    prompt_sent: str             # -- the exact prompt dispatched (for debugging)
    raw_output: str              # -- full stdout from Claude
    parsed_result: dict | None   # -- parsed JSON if available, None if malformed
    stderr: str                  # -- stderr from subprocess (never shown in reports)
    exit_code: int | None        # -- subprocess exit code (None if timeout/kill)
    duration_sec: float          # -- wall-clock seconds
    model: str                   # -- which model was used
    auth_mode: str               # -- "max" or "api"
    timestamp: str               # -- ISO-8601 UTC when dispatch started
    cost_usd: float | None       # -- from stream-json result event (None if unavailable)
```

---

## Error Flow

```
Dispatch starts
    │
    ├── Subprocess launches
    │       │
    │       ├── Exit 0, valid JSON     → status = "done" or "blocked"
    │       │
    │       ├── Exit 0, malformed JSON → status = "partial"
    │       │                            error_code = ERR_MALFORMED_JSON
    │       │                            raw_output preserved
    │       │
    │       ├── Exit 0, empty stdout   → status = "error"
    │       │                            error_code = ERR_EMPTY_OUTPUT
    │       │
    │       ├── Exit != 0              → status = "error"
    │       │                            error_code = ERR_SUBPROCESS or ERR_AUTH
    │       │                            (check stderr for auth patterns)
    │       │
    │       └── Timeout exceeded       → SIGTERM → 5s → SIGKILL
    │                                    status = "error"
    │                                    error_code = ERR_TIMEOUT
    │
    ├── Exception in dispatch code     → status = "error"
    │                                    error_code = ERR_INTERNAL
    │                                    full traceback in error_message
    │
    └── Result saved to JSON file      → ALWAYS (even on error)
```

---

## Stderr Pattern Matching

Rondo checks stderr to distinguish error subtypes:

| Pattern in stderr | Error Code | Action |
|-------------------|-----------|--------|
| `"Credit balance is too low"` | `ERR_AUTH` | Flag for human attention |
| `"cannot be launched inside another"` | `ERR_NESTED_SESSION` | Bug in env stripping |
| `"Rate limit"` or `"rate_limit"` | `ERR_RATE_LIMIT` | Pause before next task |
| `"Invalid API key"` | `ERR_AUTH` | Stop phase |
| Everything else | `ERR_SUBPROCESS` | Generic subprocess failure |

---

## Credential Safety in Errors

| Data | Allowed In | NEVER In |
|------|-----------|----------|
| API keys | Environment (stripped per auth mode) | Result files, logs, prompts, reports, error messages |
| Task prompts | Result file `prompt_sent` field | Reports (too long, may contain sensitive paths) |
| Stderr | Result file `stderr` field | Morning reports (may contain auth tokens) |
| File paths | Result file, logs | Reports (truncate to basename) |

**Rule:** If in doubt, exclude it. A missing detail is better than a leaked credential.

---

## Timeout Kill Sequence

```
1. Timer expires (default: 300 seconds)
2. Send SIGTERM to subprocess
3. Wait 5 seconds for graceful shutdown
4. If still running: send SIGKILL
5. Record:
   - status = "error"
   - error_code = "ERR_TIMEOUT"
   - duration_sec = actual elapsed time
   - raw_output = whatever was captured before timeout
```

---

## Change History

| Version | Date | What Changed |
|---------|------|-------------|
| 0.1 | 2026-03-13 | Initial draft — 10 rules, 7 error categories |
| 0.2 | 2026-03-14 | Beefed up: error codes, result structure, flow diagram, stderr patterns, credential safety, timeout sequence |
