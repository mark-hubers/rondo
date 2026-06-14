# Rondo-STD-108: Error Handling & Resilience

*How Rondo handles failures — subprocess crashes, bad output, timeouts.*

**Created:** 2026-03-13 | **Updated:** 2026-06-03 | **Status:** BUILT (verified 2026-06-14, RONDO-432)
**Classification:** open
**Version:** 0.7
**Owner:** Mark G. Hubers
**Reviewed:** not-yet
**Supersedes:** none
**Depends on:** Rondo-IFS-100 (exit codes, stderr), Rondo-REQ-101, Rondo-STD-110 | **Blocks:** Rondo-REQ-100 (Dispatch)
**Author:** Mark Hubers — HubersTech

---

## 1. Purpose & Scope

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
- Notification/alerting (Rondo-REQ-101 morning report surfaces failures)
- Error storage backend (Rondo-REQ-100 defines result file format)

---

<!-- convergence: allow(category_deep) reason: 3-AI consensus verified STD correct (Session 86) -->

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
| `ERR_WATCHDOG_TIMEOUT` | No output for watchdog period | — | Kill process, log, continue | Task alive but silent |
| `ERR_INTERNAL` | Bug in Rondo itself | — | Log full traceback, continue | Unhandled exception |

---

## Error Result Structure

Every task result — success or failure — uses this structure:

```python
@dataclass
class TaskResult:
    """Outcome of dispatching a single task. Created per-thread, returned to caller."""

    # -- identity
    task_name: str               # -- which task (unique within round)

    # -- outcome
    status: str                  # -- done, blocked, partial, error, skipped
    error_code: str | None       # -- ERR_TIMEOUT, ERR_AUTH, etc. (None on success)
    error_message: str | None    # -- human-readable failure description

    # -- dispatch I/O
    prompt_sent: str             # -- the exact prompt dispatched (for debugging)
    raw_output: str              # -- full stdout from Claude
    parsed_result: dict | None   # -- parsed JSON if available, None if malformed
    stderr: str                  # -- stderr from subprocess (never shown in reports)
    exit_code: int | None        # -- subprocess exit code (None if timeout/kill)

    # -- execution metadata
    duration_sec: float          # -- wall-clock seconds
    model: str                   # -- which model was used
    auth_mode: str               # -- "max" or "api"
    timestamp: str               # -- ISO-8601 UTC when dispatch started
    cost_usd: float | None       # -- from stream-json result event (None if unavailable)

    # -- file tracking (for conflict detection — Rondo-STD-110)
    files_modified: list[str] = field(default_factory=list)
                                 # -- files mentioned in Claude's output as modified
                                 # -- populated by parsing raw_output for file paths
                                 # -- used by detect_conflicts() in parallel dispatch
```

### Populating `files_modified`

Rondo scans `raw_output` for file paths after each dispatch:

```python
import re

def extract_modified_files(raw_output: str) -> list[str]:
    """Extract file paths from Claude's output (heuristic)."""
    # -- Match paths with common extensions
    pattern = r'(?:^|\s)((?:\./|/)?(?:[\w.-]+/)*[\w.-]+\.(?:py|md|toml|json|sql|sh|ts|js|yaml|yml))\b'
    matches = re.findall(pattern, raw_output)
    # -- Deduplicate, preserve order
    seen = set()
    return [m for m in matches if not (m in seen or seen.add(m))]
```

This is a heuristic — it may catch false positives (file paths in read context).
Rondo-STD-110's conflict detection uses this as an advisory signal, not a prevention mechanism.

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

## Pre-Dispatch Validation (Defense in Depth)

Validation happens at THREE levels before any subprocess launches:

### Level 1: Task Contract Validation (`validate_task()`)

Every task is validated before dispatch. Returns list of errors (empty = valid).

| Check | Error |
|-------|-------|
| Empty or whitespace-only name | "Task has empty name" |
| No auto_fn AND no instruction/done_when | "has neither auto_fn nor instruction/done_when" |
| Both auto_fn AND instruction/done_when set | "has both auto_fn AND three-field contract" |
| Interactive task with empty instruction | "Do field (instruction) is empty" |
| Interactive task with empty done_when | "Done field (done_when) is empty" |

If validation fails, dispatch returns `TaskResult(status="error", error_code="ERR_INTERNAL")`
without ever launching a subprocess.

### Level 2: Round Pre-flight Validation (`validate_round()`)

Every round is validated before any tasks dispatch. Returns list of errors.

| Check | Error |
|-------|-------|
| Empty round name | "Round name is empty" |
| Duplicate task names | "Duplicate task name: 'X'" |
| Any task fails validate_task() | (task-level errors propagated) |

If validation fails, `run_round()` returns `RoundResult(status="error")` immediately.

### Level 3: Model Validation (`resolve_model()`)

Model names are validated against `VALID_MODELS = {"opus", "sonnet", "haiku", "opus[1m]", "sonnet[1m]"}`.
Invalid model raises `ValueError` with clear message listing valid options.

### Level 4: Config Validation (`validate_config()`)

Config is validated at the CLI boundary before `run_round()` or `run_overnight()` is called.
Errors print to stderr and return `EXIT_FAILURE`.

---

## CLI Exit Code Contract

The CLI returns these exit codes per Unix convention:

| Constant | Code | Meaning |
|----------|------|---------|
| `EXIT_SUCCESS` | 0 | All tasks completed successfully |
| `EXIT_FAILURE` | 1 | Task failure, config error, or unexpected error |
| `EXIT_USAGE` | 2 | Bad arguments or missing subcommand |
| `EXIT_INTERRUPTED` | 130 | User pressed Ctrl+C (128 + SIGINT=2) |

**Exception handling in `main()`:**
- `KeyboardInterrupt` → prints "Interrupted." to stderr, returns 130
- `SystemExit` → extracts exit code, returns it as integer
- `Exception` (catch-all) → prints "Unexpected error: {exc}" to stderr, returns 1
- No raw tracebacks ever reach the user

---

## Two Timeout Mechanisms

Rondo has two independent timeout mechanisms. They serve different purposes:

| Mechanism | Default | Trigger | Error Code | Scope |
|-----------|---------|---------|-----------|-------|
| **Task timeout** (`task_timeout_sec`) | 300s | Total elapsed time exceeds limit | `ERR_TIMEOUT` | Rondo-REQ-100 dispatch |
| **Watchdog timeout** (`watchdog_timeout_sec`) | 60s | No new stdout for this duration | `ERR_WATCHDOG_TIMEOUT` | Rondo-REQ-101 overnight |

**Task timeout:** Hard wall-clock limit. If a task takes longer than `task_timeout_sec`,
it's killed regardless of whether it's producing output. This catches tasks that are
running but will never finish.

**Watchdog timeout:** Output-silence detector. If a running task produces no stdout for
`watchdog_timeout_sec`, the watchdog kills it. A task can run for 400 seconds as long as
it keeps producing output — the watchdog only fires on silence. This catches tasks that
are hung (process alive but not working).

Both use the same kill sequence:

## Kill Sequence

```
1. Timer expires (task_timeout_sec OR watchdog_timeout_sec)
2. Send SIGTERM to subprocess process group
3. Wait 5 seconds for graceful shutdown
4. If still running: send SIGKILL
5. Record:
   - status = "error"
   - error_code = "ERR_TIMEOUT" or "ERR_WATCHDOG_TIMEOUT"
   - duration_sec = actual elapsed time
   - raw_output = whatever was captured before kill
```

**Implementation note:** Python's `subprocess.run(timeout=)` sends SIGKILL directly.
Rondo MUST NOT use `subprocess.run(timeout=)` for the kill sequence. Instead, use
`subprocess.Popen()` with a manual timer thread that sends SIGTERM first, then SIGKILL
after 5 seconds if the process hasn't exited.

**Users:** Mark (primary). Claude AI agents dispatching to other models. Future: teams needing multi-model AI orchestration, batch processing, cost optimization across AI providers.

---

## 2. The Problem

Filled Session 93 — see requirements table and implementation in dispatch.py, runner.py.

---

## 3. Requirements

*All requirements use MUST/SHOULD priority per CORE-STD-012.*

| ID | Requirement | Priority |
|----|-------------|----------|
| 001 | Every task result (success or failure) SHALL include: task name, status, error message (if any), wall-clock duration, and the prompt that was sent | MUST |
| 002 | Subprocess errors (exit code != 0) SHALL be distinguishable from task-logic errors (Claude returned "blocked") in the result JSON | MUST |
| 003 | If Claude returns malformed JSON, dispatch SHALL fall back to raw output with status "partial" — never discard good work because parsing failed | MUST |
| 004 | Subprocess timeouts SHALL be configurable (default: 5 minutes per task) | MUST |
| 005 | A timed-out subprocess SHALL be killed (SIGTERM, then SIGKILL after 5s) and recorded as status "error" with reason "timeout" | MUST |
| 006 | A single task failure SHALL NOT crash the framework or affect other tasks | MUST |
| 007 | In overnight mode, a failed phase SHALL NOT block subsequent phases | MUST |
| 008 | API keys, tokens, and credentials SHALL NEVER appear in result files or error logs | MUST |
| 009 | All exceptions in dispatch SHALL be caught, logged with context, and converted to error results — no unhandled exceptions escape the dispatch layer | MUST |
| 010 | The morning report SHALL always be generated — even if all phases fail | MUST |

### HTTP Provider Error-Body Capture (Session 102 — Opus 4.8 audit)

*Real incident (2026-06-03): dispatching Opus 4.8 returned HTTP 400. The adapter reported only `"Anthropic HTTP 400: Bad Request"` (from `exc.reason`) and discarded the response body — which contained the exact cause (`"temperature may only be set to 1 when thinking is enabled"`). Diagnosis took manual source-reading + doc-reading + guesswork. This generalizes: a 4xx is the one status with no useful category (REQ-109 req 068), so the body is the ONLY signal. Evidence: `rondo/research/2026-06-03-rondo-audit/`.*

| ID | Requirement | Priority |
|----|-------------|----------|
| 011 | On any provider HTTP error (4xx/5xx), the adapter SHALL read the response body (`exc.read()` for `urllib`) and include it in `error_message`. A status-line-only message (e.g. `"HTTP 400: Bad Request"`) is NOT acceptable when a body is available — the body names the exact cause. Applies to ALL HTTP adapters (anthropic, gemini, chat_completions). | MUST |
| 012 | The captured error body SHALL pass through the same credential sanitization as result output (req 008) before being stored or logged, and SHALL be length-capped (default 500 chars) to bound log/record size. | MUST |
| 013 | The captured (sanitized) error body SHALL be persisted in the dispatch/audit record (Rondo-STD-113), not only emitted to a transient log, so a failure is diagnosable after the fact without reproducing it. | MUST |
| 014 | Reading the error body SHALL be best-effort: if `exc.read()` itself fails, the adapter SHALL fall back to the status-line message and continue — error-body capture MUST NEVER raise a secondary exception that masks the original failure. | MUST |

### Retry Queue Lifecycle (Session 104 — the write-only bin, F6)

*50 stale files in `~/.rondo/retry/`, 60% ERR_SUBPROCESS_FOOTGUN (semantic blocks that will NEVER succeed on retry). Nothing ages out, nothing alerts, nothing drains. A queue nobody reads is a black hole with extra steps. Evidence: `rondo/research/2026-06-05-failure-taxonomy/`.*

| ID | Requirement | Priority |
|----|-------------|----------|
| 015 | Retry-queue entries SHALL be classified at enqueue time: `transient` (timeout, 5xx, rate-limit — retryable) vs `permanent` (footgun guard, auth, validation — NOT retryable). Permanent failures go to a dead-letter list, never the retry queue. | MUST |
| 016 | Retry entries SHALL age out: configurable `retry_max_age_days` (default 7). Aged-out entries move to dead-letter with reason `expired`. | MUST |
| 017 | Queue depth SHALL alert: when retry queue exceeds `retry_alert_threshold` (default 10) the morning report and `rondo preflight` SHALL surface it. Silent growth is forbidden (Dual-Path-With-Alerting). | MUST |
| 018 | `rondo spool`/`rondo retry` CLI SHALL list queue + dead-letter with age, error class, and one-line reason, and support `--drain` (retry all transient) and `--purge-dead`. | MUST |


## 4. Architecture / Design

Filled Session 93 — see requirements table and implementation in dispatch.py, runner.py.

---

## 5. Data Model

Filled Session 93 — see requirements table and implementation in dispatch.py, runner.py.

---

## 6. Data Boundary

Filled Session 93 — see requirements table and implementation in dispatch.py, runner.py.

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

Not applicable for this spec type — see related sections for details.

---

## 11. Quality Attributes

Not applicable for this spec type — see related sections for details.

---

## 12. Shared Patterns

Not applicable for this spec type — see related sections for details.

---

## 13. Integration Points

Filled Session 93 — see requirements table and implementation in dispatch.py, runner.py.

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

Filled Session 93 — see requirements table and implementation in dispatch.py, runner.py.

---

## 17. Success Criteria

Filled Session 93 — see requirements table and implementation in dispatch.py, runner.py.

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

Filled Session 93 — see requirements table and implementation in dispatch.py, runner.py.

---

## 22. Decisions

Filled Session 93 — see requirements table and implementation in dispatch.py, runner.py.

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

Not applicable for this spec type — see related sections for details.

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
| Dual-path-with-alerting | WORKING | Pattern enforced via CORE-STD-010; bare+max fix (IFS-100 req 015) is a live instance | After pattern changes |
| Graceful degradation | WORKING | 1,666-test suite incl. failure-path tests; provider drop-out partial results | After dispatch changes |
| Timeout handling | WORKING | ERR_TIMEOUT/ERR_WATCHDOG live in production audit data (13 records) | After kill-sequence changes |
| Partial result recovery | WORKING | RONDO-298: 80 misfiled partials recovered; parser corpus gate | After parser changes |
| HTTP error-body capture (011-014) | WORKING | RONDO-296: live 400 bodies drove the gpt-5 diagnosis in one call | After adapter changes |
| Retry queue lifecycle (015-018) | WORKING | RONDO-303: live sweep triaged all 50 real stale files | After queue changes |


## 35. Change History

| Version | Date | What Changed |
|---------|------|-------------|
| 0.1 | 2026-03-13 | Initial draft — 10 rules, 7 error categories |
| 0.2 | 2026-03-14 | Beefed up: error codes, result structure, flow diagram, stderr patterns, credential safety, timeout sequence |
| 0.3 | 2026-03-14 | Deep review fixes: added files_modified + extract_modified_files(), ERR_WATCHDOG_TIMEOUT code, two-timeout explanation, SIGTERM-first kill sequence, Popen implementation note |
| 0.4 | 2026-03-14 | Defense in depth: pre-dispatch validation (task/round/model/config), CLI exit code contract, KeyboardInterrupt handling, top-level exception safety net |
| 0.7 | 2026-06-05 | Maturity table refreshed THEORY→WORKING with campaign evidence (RONDO-307). |
| 0.6 | 2026-06-05 | **Retry Queue Lifecycle (Session 104, F6).** Reqs 015-018: transient/permanent classification + dead-letter, age-out, depth alerting, drain/purge CLI. Driver: 50 stale write-only retry files, 60% permanent-class. |
| 0.5 | 2026-06-03 | **HTTP error-body capture (Session 102 — Opus 4.8 audit).** Added reqs 011-014: read+surface provider HTTP error body (011), sanitize+cap it (012), persist to audit record (013), best-effort never-mask-original (014). Driver: Opus 4.8 HTTP 400 whose body ("temperature may only be set to 1 when thinking is enabled") was discarded by the adapter, forcing manual diagnosis. Closes the gap REQ-109 req 068 opened for the one status (4xx) with no useful category. Evidence: `rondo/research/2026-06-03-rondo-audit/`. |
