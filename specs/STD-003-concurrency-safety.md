# STD-003: Concurrency & Safety

*How Rondo runs tasks in parallel safely — no injection, no leaks, no corruption.*

**Created:** 2026-03-13 | **Updated:** 2026-03-14 | **Status:** DRAFT
**Depends on:** STD-001 (Error Handling), STD-002 (Configuration) | **Blocks:** REQ-002 (Parallel)
**Author:** Mark Hubers — HubersTech

---

## Item 1: Purpose & Scope

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
- Parallel scheduling logic (REQ-002)
- Error recovery (STD-001)
- Config values for workers/throttle (STD-002 — this spec defines HOW, STD-002 defines WHAT values)

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
    # -- config is frozen dataclass (STD-002) — safe to share
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
# -- max_workers comes from config (validated 1-32 by STD-002)
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
        # -- This should never happen if dispatch catches all (STD-001 rule 9)
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
# -- Before writing result to file, verify no credentials leaked
def sanitize_result(result: TaskResult) -> TaskResult:
    """Remove any credential patterns from result fields."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if api_key:
        # -- Check all string fields
        for field in ["raw_output", "stderr", "error_message"]:
            value = getattr(result, field, "")
            if api_key in value:
                setattr(result, field, value.replace(api_key, "[REDACTED]"))
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
    context_files=["src/engine.py", "specs/REQ-001.md"],
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

### R1: Subprocess timeout with kill sequence

```python
try:
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=config.task_timeout_sec,   # -- default 300s
        env=child_env,
    )
except subprocess.TimeoutExpired as exc:
    # -- subprocess.run sends SIGKILL on timeout by default
    # -- but we want the graceful SIGTERM first pattern from STD-001
    return TaskResult(
        status="error",
        error_code="ERR_TIMEOUT",
        raw_output=exc.stdout or "",
        stderr=exc.stderr or "",
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

---

## Change History

| Version | Date | What Changed |
|---------|------|-------------|
| 0.1 | 2026-03-13 | Initial draft — 15 rules in 3 categories |
| 0.2 | 2026-03-14 | Beefed up: code patterns for every rule, attack prevention table, thread safety matrix, conflict detection pattern |
