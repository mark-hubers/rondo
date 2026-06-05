# Rondo-STD-110: Concurrency & Safety

*How Rondo runs tasks in parallel safely — no injection, no leaks, no corruption.*

**Created:** 2026-03-13 | **Updated:** 2026-06-03 | **Status:** DRAFT
**Classification:** open
**Version:** 0.6
**Owner:** Mark G. Hubers
**Reviewed:** not-yet
**Supersedes:** none
**Depends on:** Rondo-STD-108 (Error Handling), Rondo-STD-109 (Configuration) | **Blocks:** Rondo-REQ-101 (Parallel)
**Author:** Mark Hubers — HubersTech

---

## 1. Purpose & Scope

**What this spec does (plain English):**
Defines the rules for running multiple Claude dispatches in parallel without
command injection, credential leaks, file corruption, or unbounded resource use.
These rules apply to every line of Rondo code — they are not optional.

**IN scope:**
- Thread safety rules for parallel dispatch
- Subprocess security (injection prevention)
- Credential handling rules
- Resource bounding (files, threads, time)
- File permission rules
- Conflict detection pattern

**OUT of scope:**
- Parallel scheduling logic (Rondo-REQ-101)
- Error recovery (Rondo-STD-108)
- Config values for workers/throttle (Rondo-STD-109 — this spec defines HOW, Rondo-STD-109 defines WHAT values)

---

## Principle

Rondo dispatches subprocesses that can modify files. Parallel execution means
multiple processes running at once. Safety means: no command injection, no
credential leaks, no file corruption from concurrent writes, no unbounded
resource consumption.

---

## Concurrency Rules

### C1: ThreadPoolExecutor for I/O-bound work

```python
# -- CORRECT: bounded thread pool
from concurrent.futures import ThreadPoolExecutor, as_completed

with ThreadPoolExecutor(max_workers=config.workers) as pool:
    futures = {
        pool.submit(dispatch_task, task): task
        for task in round.tasks
    }
    for future in as_completed(futures):
        task = futures[future]
        result = future.result()   # -- never raises (dispatch catches all)
```

**Why threads, not processes:** Rondo's work is I/O-bound (waiting for
subprocess). Threads share memory for result collection. ProcessPool would
add serialization overhead for no benefit.

### C2: No shared mutable state

Each task gets its own result dict. No locks needed because nothing is shared.

```python
# -- CORRECT: each task returns its own result
def dispatch_task(task: Task, config: RondoConfig) -> TaskResult:
    """Each thread gets its own task and config (frozen). Returns a new result."""
    # -- config is frozen dataclass (Rondo-STD-109) — safe to share
    # -- task is read-only during dispatch
    # -- result is created here, returned to caller
    return TaskResult(task_name=task.name, ...)

# -- WRONG: never do this
shared_results = []  # -- mutable shared state across threads
def dispatch_task(task):
    shared_results.append(result)  # -- race condition!
```

### C3: Throttle between launches

```python
# -- Space out task launches to respect rate limits
for i, task in enumerate(tasks):
    if i > 0:
        time.sleep(config.throttle_sec)   # -- default 2.0s
    pool.submit(dispatch_task, task)
```

**Why:** Claude Code may rate-limit rapid sequential requests. Throttle
prevents hitting the rate limit on the first burst.

### C4: Conflict detection

After all tasks complete, check for files modified by 2+ tasks:

```python
def detect_conflicts(results: list[TaskResult]) -> list[str]:
    """Find files touched by multiple tasks."""
    file_tasks: dict[str, list[str]] = {}
    for result in results:
        for filepath in result.files_modified:
            file_tasks.setdefault(filepath, []).append(result.task_name)

    return [
        f"{path} modified by: {', '.join(tasks)}"
        for path, tasks in file_tasks.items()
        if len(tasks) > 1
    ]
```

### C5: Conflict is advisory, not blocking

```python
conflicts = detect_conflicts(results)
if conflicts:
    # -- WARN, don't fail
    for conflict in conflicts:
        log.warning(f"CONFLICT: {conflict}")
    # -- include in summary for human review
    summary.conflicts = conflicts
```

**Why advisory:** Rondo can't know if the modifications conflict semantically
(two tasks editing different parts of the same file is fine). The human or
the round definition decides whether conflicts are a problem.

### C6: Bounded workers

```python
# -- max_workers comes from config (validated 1-32 by Rondo-STD-109)
# -- NEVER create unbounded threads
with ThreadPoolExecutor(max_workers=config.workers) as pool:
    ...
```

### C7: Task thread isolation

```python
# -- If a task raises, the future captures it — other tasks continue
for future in as_completed(futures):
    try:
        result = future.result()
    except Exception as exc:
        # -- This should never happen if dispatch catches all (Rondo-STD-108 rule 9)
        # -- But defense-in-depth: log and continue
        result = TaskResult(
            task_name=futures[future].name,
            status="error",
            error_code="ERR_INTERNAL",
            error_message=str(exc),
            ...
        )
```

---

## Security Rules

### S1: List arguments, never shell=True

```python
# -- CORRECT: list args — each element is a separate argv entry
cmd = ["claude", "-p", prompt, "--model", model]
result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

# -- WRONG: shell=True — prompt could contain shell metacharacters
result = subprocess.run(f"claude -p '{prompt}'", shell=True, ...)
```

**Attack:** If `prompt` contains `'; rm -rf /; '`, shell=True executes it.
List args pass it as a literal string to the subprocess.

### S2: Credential stripping

```python
# -- Build child environment
child_env = os.environ.copy()

# -- ALWAYS strip CLAUDECODE (prevents nested session guard)
child_env.pop("CLAUDECODE", None)

# -- Strip API key when using Max plan subscription
if config.auth == "max":
    child_env.pop("ANTHROPIC_API_KEY", None)
# -- Keep API key when using pay-per-token
# elif config.auth == "api":
#     pass  (key stays in env)
```

### S3: Credentials never in output

```python
from dataclasses import replace as dc_replace

# -- Before writing result to file, verify no credentials leaked
def sanitize_result(result: TaskResult) -> TaskResult:
    """Remove any credential patterns from result fields.
    Returns a NEW TaskResult (dataclass may be frozen).
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return result

    replacements = {}
    for field_name in ("raw_output", "stderr", "error_message"):
        value = getattr(result, field_name, "") or ""
        if api_key in value:
            replacements[field_name] = value.replace(api_key, "[REDACTED]")

    if replacements:
        return dc_replace(result, **replacements)
    return result
```

**Rule:** API keys, tokens, and credentials MUST NEVER appear in:
- Result JSON files
- Log output
- Error messages
- Prompts sent to Claude
- Morning reports

### S4: Prompts must not contain secrets

Round definitions are responsible for excluding sensitive files from the
Read (context) field. Rondo does not inspect prompt content — but the
standard is documented:

```python
# -- CORRECT: context files are code, specs, configs (no secrets)
task = Task(
    context_files=["src/engine.py", "specs/Rondo-REQ-100.md"],
    ...
)

# -- WRONG: never include files with credentials
task = Task(
    context_files=[".env", "secrets.yaml"],   # -- NEVER
    ...
)
```

### S5: Restrictive file permissions

```python
import stat

def write_result_file(path: str, content: str) -> None:
    """Write result with owner-only permissions."""
    with open(path, "w") as f:
        f.write(content)
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)   # -- 0o600: owner rw only
```

---

## Resource Rules

### R1: Subprocess timeout with SIGTERM-first kill sequence

MUST use `subprocess.Popen()` with a manual timer thread. MUST NOT use
`subprocess.run(timeout=)` which sends SIGKILL directly, skipping graceful shutdown.
Matches Rondo-STD-108 kill sequence: SIGTERM → 5s grace → SIGKILL.

```python
import threading

proc = subprocess.Popen(
    cmd,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
    env=child_env,
)

timed_out = threading.Event()

def kill_on_timeout():
    """SIGTERM → 5s → SIGKILL. Matches Rondo-STD-108 kill sequence."""
    timed_out.set()
    proc.terminate()               # -- SIGTERM (graceful)
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()                # -- SIGKILL (force)

timer = threading.Timer(config.task_timeout_sec, kill_on_timeout)
timer.start()
try:
    stdout, stderr = proc.communicate()
finally:
    timer.cancel()

if timed_out.is_set():
    return TaskResult(
        status="error",
        error_code="ERR_TIMEOUT",
        raw_output=stdout or "",
        stderr=stderr or "",
        duration_sec=config.task_timeout_sec,
        ...
    )
```

### R2: Bounded result files

```python
MAX_RESULT_SIZE = 1_048_576   # -- 1MB default

def truncate_output(output: str, max_size: int = MAX_RESULT_SIZE) -> str:
    """Truncate large output with a note."""
    if len(output) <= max_size:
        return output
    return output[:max_size] + f"\n\n[TRUNCATED: {len(output)} bytes, limit {max_size}]"
```

### R3: Rolling event log

```python
MAX_LOG_ENTRIES = 100

def append_event_log(log_path: str, entry: dict) -> None:
    """Append to event log, trim to last MAX_LOG_ENTRIES."""
    entries = []
    if os.path.exists(log_path):
        with open(log_path) as f:
            entries = json.load(f)

    entries.append(entry)

    # -- Keep only the last N entries
    if len(entries) > MAX_LOG_ENTRIES:
        entries = entries[-MAX_LOG_ENTRIES:]

    with open(log_path, "w") as f:
        json.dump(entries, f, indent=2)
```

---

## Why These Rules

| Rule | Attack / Failure It Prevents |
|------|------------------------------|
| No shell=True (S1) | Command injection via task name or file path |
| Credential stripping (S2) | API key passed to wrong auth mode |
| No credentials in output (S3) | Credential leak in result files shared or committed to git |
| CLAUDECODE stripping (S2) | Nested session guard blocks all dispatch |
| No shared mutable state (C2) | Race condition corrupting results |
| Subprocess timeout (R1) | Hung process blocks worker thread forever |
| Bounded result files (R2) | One verbose Claude response fills disk |
| Rolling event log (R3) | Months of overnight runs exhaust disk |
| Conflict detection (C4) | Two tasks overwrite each other's output |
| Restrictive permissions (S5) | Other users reading result files with API call data |

---

## Thread Safety Summary

| Component | Thread-Safe? | Why |
|-----------|-------------|-----|
| `RondoConfig` | ✓ | Frozen dataclass — immutable |
| `Task` | ✓ | Read-only during dispatch |
| `TaskResult` | ✓ | Created per-thread, returned to caller |
| `results list` | ✓ | Built from `as_completed` — no shared mutation |
| `subprocess.run` | ✓ | Each call is independent |
| `file writes` | ✓ | Each task writes to its own result file |
| `event log` | ✗ | Written after all tasks complete (sequential) |

**Users:** Mark (primary). Claude AI agents dispatching to other models. Future: teams needing multi-model AI orchestration, batch processing, cost optimization across AI providers.

---

## 2. The Problem

REQUIRED — fill before build.

---

## 3. Requirements

*All requirements use MUST/SHOULD priority per CORE-STD-012.*

### Concurrency

| ID | Requirement | Priority |
|----|-------------|----------|
| 001 | Parallel dispatch SHALL use `concurrent.futures.ThreadPoolExecutor` (I/O-bound, not CPU-bound) | MUST |
| 002 | No shared mutable state between task threads — each task gets its own result dict | MUST |
| 003 | System SHALL throttle between subprocess launches (configurable delay, default 0.5s) | MUST |
| 004 | Conflict detection SHALL identify tasks that touch the same files and warn before dispatch | MUST |
| 005 | Conflict detection SHALL be advisory, not blocking — warn and proceed unless `--strict` | MUST |
| 006 | Worker count SHALL be bounded and configurable (`config.workers`, default 4) | MUST |
| 007 | Each task thread SHALL have its own working directory via git worktree for file isolation | MUST |

### Security

| ID | Requirement | Priority |
|----|-------------|----------|
| 008 | Subprocess invocation SHALL use list arguments, never `shell=True` | MUST |
| 009 | System SHALL strip credentials (`ANTHROPIC_API_KEY`, `CLAUDECODE`) from child process env unless explicitly needed | MUST |
| 010 | Credentials SHALL never appear in task output, logs, or result files | MUST |
| 011 | Prompts sent to AI SHALL NOT contain secrets — validate before dispatch | MUST |
| 012 | Result files and spool directories SHALL use restrictive file permissions (0o600 files, 0o700 dirs) | MUST |

### Resources

| ID | Requirement | Priority |
|----|-------------|----------|
| 013 | Subprocess SHALL have a configurable timeout with SIGTERM-first, SIGKILL-after kill sequence | MUST |
| 014 | Result files SHALL be bounded — truncate output exceeding configurable max size | MUST |
| 015 | Event log SHALL be rolling — oldest entries removed when log exceeds configurable max entries | MUST |

### Cross-Process State Safety (Session 102 — auto_reconcile race, Finding #257)

> ✅ **VERIFY-FIRST CONCLUDED (Session 104, RONDO-310):** req 020's stress test
> was built and run — 25 concurrent processes × 8 dispatches each, every worker
> reconciling mid-flight (the exact #257 attack). Result: ZERO false-stuck, ZERO
> torn JSONL lines, ZERO duplicate outcomes. The STD-113 017-019 age-threshold
> mitigation is SUFFICIENT. **The flock layer (reqs 016-019) is NOT built** —
> `tests/unit/test_audit_stress.py` stands as the permanent guard; if it ever
> fails, reqs 016-019 become a build order.

*Finding #257 (flagged HIGH independently by Gemini and Grok during RONDO-210 Phase D review): the audit trail's INTENT→IN-FLIGHT→DONE state machine is filesystem-backed (JSONL) with no distributed lock. Concurrent workers see a stale mid-transition view; a worker's `reconcile_stuck_intents()` marks another worker's VALID in-flight dispatch as "stuck" and re-dispatches it → duplicate cost + confusing results. STD-110 owns locks; the audit record schema is STD-113. Evidence: `rondo/research/2026-06-03-rondo-audit/`.*

| ID | Requirement | Priority |
|----|-------------|----------|
| 016 | Cross-process audit state transitions (INTENT→IN-FLIGHT→DONE, and stuck reconciliation) SHALL be atomic w.r.t. other workers: a worker SHALL hold an exclusive `fcntl.flock` on the audit file before any read-modify-write of a dispatch's state. Unlocked read-then-write of shared state is forbidden. | MUST |
| 017 | `reconcile_stuck_intents()` SHALL mark an INTENT "stuck" ONLY when it holds the lock AND the INTENT's age exceeds `stuck_after_sec` (default 300s). A peer worker's in-flight dispatch younger than the threshold SHALL NEVER be declared stuck or re-dispatched. | MUST |
| 018 | Reconciliation SHALL be idempotent: re-running it SHALL NOT create duplicate OUTCOME records nor re-dispatch a dispatch already completed by another worker. Check-then-act SHALL be guarded by the lock held in req 016. | MUST |
| 019 | Lock acquisition SHALL degrade gracefully where `flock` is unavailable (NFS / Windows): fall back to single-writer mode and emit a WARNING — NEVER silently skip the safety check. (Dual-Path-With-Alerting.) | MUST |
| 020 | Concurrency safety for state transitions SHALL be verified by a stress test at ≥20 concurrent dispatches. Prior tests (10-20 concurrent) were insufficient to expose the TOCTOU window in Finding #257. | MUST |

---

## 4. Architecture / Design

REQUIRED — fill before build.

---

## 5. Data Model

REQUIRED — fill before build.

---

## 6. Data Boundary

REQUIRED — fill before build.

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

## 10. Rules
**Conflict detection timing (CRIT fix — reconciled):** Conflict detection runs at TWO points: (1) PRE-DISPATCH: check for conflicting file paths in the task queue (fast, prevents obvious conflicts). (2) POST-TASK: validate worktree state matches expected state (catches unexpected mutations). These are COMPLEMENTARY checks, not contradicting. Pre = prevention, Post = verification.
**Worktree vs conflict detection (CRIT fix):** When `workers > 1`, each task gets its own git worktree (req 007). This ELIMINATES file-level conflicts — worktrees are isolated by definition. The conflict detection mechanism (Section C4/C5) applies to SEQUENTIAL mode only (workers=1, shared working directory). In parallel mode: worktrees prevent conflicts. In sequential mode: conflict detection catches shared-state issues.

**Conflict detection timing (CRIT fix):** Conflict detection runs BEFORE dispatch (req 004 is canonical). Section C4 description of 'after task complete' refers to VALIDATION of results, not detection of conflicts. Pre-dispatch: check for conflicting file paths. Post-task: validate results haven't corrupted shared state.
**Sanitization ownership (CRIT fix):** Rondo-STD-114 is the CANONICAL output sanitization spec. Rondo-STD-110's `sanitize_result` is DEPRECATED — all sanitization MUST go through Rondo-STD-114's pipeline. STD-110 handles concurrency ONLY (locks, worktrees, conflict detection). STD-114 handles output ONLY (redaction, filtering, format validation). & Constraints

Not applicable for this spec type — see related sections for details.

---

## 11. Quality Attributes

Not applicable for this spec type — see related sections for details.

---

## 12. Shared Patterns

Not applicable for this spec type — see related sections for details.

---

## 13. Integration Points

REQUIRED — fill before build.

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

REQUIRED — fill before build.

---

## 17. Success Criteria

REQUIRED — fill before build.

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

REQUIRED — fill before build.

---

## 22. Decisions

REQUIRED — fill before build.

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
| Concurrency patterns | THEORY | Specced for parallel task safety | Phase 2 build |
| Lock management | THEORY | Specced for resource locking during dispatch | Phase 2 build |
| Race condition prevention | THEORY | Specced for safe concurrent task execution | Phase 2 build |


## 35. Change History

| Version | Date | What Changed |
|---------|------|-------------|
| 0.1 | 2026-03-13 | Initial draft — 15 rules in 3 categories |
| 0.2 | 2026-03-14 | Beefed up: code patterns for every rule, attack prevention table, thread safety matrix, conflict detection pattern |
| 0.3 | 2026-03-14 | Deep review fix: sanitize_result() uses dc_replace() instead of setattr (frozen dataclass safe) |
| 0.4 | 2026-03-14 | Deep review v2: R1 subprocess timeout rewritten from subprocess.run(timeout=) to Popen + SIGTERM-first kill sequence (matches CORE-IFS-001 reqs 53-54 (status vocabulary)) |
| 0.6 | 2026-06-05 | Verify-first concluded: 25-worker stress test PASSED (zero false-stuck/torn/dup) — flock layer not built; stress test = permanent guard. |
| 0.5 | 2026-06-03 | **Cross-process state safety (Session 102 — auto_reconcile race).** Added reqs 016-020: flock-guarded atomic state transitions (016), age-gated stuck reconciliation (017), idempotent reconcile (018), graceful flock degradation w/ alert (019), ≥20-concurrent stress test (020). Driver: Finding #257 (RONDO-210 Phase D) — Gemini+Grok both flagged HIGH; INTENT/IN-FLIGHT/DONE not atomic across workers → valid in-flight marked stuck → duplicate re-dispatch. Pairs with STD-113 (audit record schema). Evidence: `rondo/research/2026-06-03-rondo-audit/`. |
