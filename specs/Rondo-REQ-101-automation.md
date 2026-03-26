# Rondo-REQ-101: Automation — Parallel + Overnight + Report

*Run many tasks fast, schedule them overnight, get a morning report.*

**Created:** 2026-03-13 | **Status:** DRAFT
**Classification:** open
**Version:** 0.7
**Owner:** Mark G. Hubers
**Reviewed:** not-yet
**Supersedes:** none
**Depends on:** Rondo-REQ-100, Rondo-REQ-109 (Provider Adapters — dispatch uses adapter interface, not claude -p directly) (Core) v1.0+, Rondo-STD-108, Rondo-STD-109, Rondo-STD-110, CORE-STD-001 (Data Standards), Python 3.12+ | **Blocks:** Nothing
**Author:** Mark Hubers — HubersTech

---

## 1. Purpose & Scope

**What this spec does (plain English):**
Adds parallel execution, overnight batch scheduling, and morning reports on top of Rondo-REQ-100's core. Rondo-REQ-100 dispatches one task at a time. Rondo-REQ-101 dispatches many tasks at once, chains rounds into overnight phases, and summarizes results for the morning.

**IN scope:**
- Parallel dispatch: concurrent task execution with throttling
- Conflict detection: flag files touched by multiple parallel tasks
- Self-healing watchdog: auto-kill hung tasks, rate limit backoff
- Usage threshold gating: react to overage/blocked status from stream-json
- Worktree isolation: optional per-task git worktree for parallel safety
- Overnight scheduler: phased batch execution with configurable modes
- Morning report: aggregated results with health indicators and usage summary
- Event logging: rolling log for overnight post-mortem

**OUT of scope:**
- Engine, dispatch, auth, model routing (Rondo-REQ-100: Core)
- Specific round definitions (consumer's responsibility)
- System-level scheduling (cron/LaunchAgent config — platform-specific)
- Real-time monitoring / dashboards (future work)

**Users:** Mark (primary). Claude AI agents dispatching to other models. Future: teams needing multi-model AI orchestration, batch processing, cost optimization across AI providers.

---

## 2. The Problem

Rondo-REQ-100 runs tasks sequentially — one at a time. A round with 8 tasks at 3 minutes each takes 24 minutes. Running 32 specs through that takes 12+ hours. That exceeds overnight capacity.

**Parallel execution** solves throughput: 4 workers cut wall time by ~4x. But parallel introduces risks — two tasks modifying the same file, rate limiting from too many concurrent Claude sessions, results arriving out of order.

**Overnight scheduling** solves automation: define which rounds run in what order, handle phase failures gracefully, produce a summary before morning. The human defines the schedule. Rondo runs it unattended.

**Morning reports** solve visibility: "what happened last night?" must be answerable in 30 seconds by reading one file.

---

## 3. Requirements

*All requirements use MUST/SHOULD priority per CORE-STD-012.*

### Parallel Execution
| ID | Requirement | Priority |
|----|-------------|----------|
| 001 | Parallel dispatch MUST use `concurrent.futures.ThreadPoolExecutor` with configurable worker count | MUST |
| 002 | Worker count MUST be configurable via CLI (`--workers N`) and config file. Default: 4 | MUST |
| 003 | Parallel dispatch MUST support a configurable throttle delay between task launches. Default: 2 seconds | MUST |
| 004 | Results MUST be collected as futures complete (not in submission order) | MUST |
| 005 | Parallel dispatch MUST detect potential file conflicts: files mentioned in output by 2+ concurrent tasks | MUST |
| 006 | Detected conflicts MUST be listed in the round summary (not silently ignored) | MUST |
| 007 | Parallel dispatch MUST report: done count, error count, wall time, sum of task times, speedup ratio | MUST |
| 008 | If a single task fails or raises an exception, other tasks MUST NOT be affected | MUST |
| 009 | Parallel results MUST be saved to the same JSON format as sequential results (Rondo-REQ-100 compatibility) | MUST |

### Overnight Scheduler
| ID | Requirement | Priority |
|----|-------------|----------|
| 010 | The overnight scheduler MUST accept a list of round definitions to execute in order (phases) | MUST |
| 011 | Phases MUST execute sequentially (one completes before next starts). Tasks within a phase MAY be parallel | MUST |
| 012 | Phase failures MUST NOT block subsequent phases. Log the error, continue to next phase | MUST |
| 013 | The scheduler MUST support configurable modes that select which phases run | MUST |
| 014 | At minimum, 3 modes MUST be supported: minimal (1-2 phases), standard (3-4 phases), full (all phases) | MUST |
| 015 | Mode names and phase assignments MUST be configurable (not hardcoded to OB/ACE rounds) | MUST |
| 016 | The scheduler MUST be invocable from command line with no interactive input required | MUST |
| 017 | The scheduler MUST log start and end events with timestamps and mode | MUST |
| 018 | The event log MUST be a rolling JSON file that keeps the last 100 entries | MUST |

### Self-Healing Watchdog
| ID | Requirement | Priority |
|----|-------------|----------|
| 019 | The overnight scheduler MUST monitor each dispatch for stuck/hung conditions using a separate watchdog timer independent of the task timeout (Rondo-STD-108). The task timeout is a hard wall-clock limit. The watchdog detects output silence | MUST |
| 020 | If a dispatch subprocess does not produce new stdout for a configurable duration (`watchdog_timeout_sec`, default: 60 seconds), the watchdog MUST kill it and record status "error" with error_code "ERR_WATCHDOG_TIMEOUT". A task producing output can run longer than `watchdog_timeout_sec` — the watchdog only fires on silence | MUST |
| 021 | After a watchdog kill, the scheduler MUST continue to the next task — never halt the pipeline | MUST |
| 022 | If a dispatch fails with a rate limit error (ERR_RATE_LIMIT), the watchdog MUST pause for a configurable backoff duration (default: 60 seconds) before the next dispatch | MUST |
| 023 | The watchdog MUST log every intervention (kill, pause, skip) to the event log with timestamp and reason | MUST |

### Usage Threshold Gating
| ID | Requirement | Priority |
|----|-------------|----------|
| 024 | Before each phase, the scheduler MUST check the most recent `rate_limit_event` from the previous dispatch | MUST |
| 025 | If `isUsingOverage` is `true`, the scheduler MUST take a configurable action: `continue` (default), `pause` (wait for reset), or `stop` (end overnight run early) | MUST |
| 026 | If `rate_limit_status` is `"blocked"`, the scheduler MUST pause until `resetsAt` epoch and then retry the phase | MUST |
| 027 | The overage action MUST be configurable via CLI (`--on-overage`) and config file (`on_overage`). Default: `continue` | MUST |
| 028 | Usage threshold decisions MUST be logged to the event log with the rate_limit_event data that triggered them | MUST |

### Morning Report
| ID | Requirement | Priority |
|----|-------------|----------|
| 029 | The morning report MUST aggregate results from all phases in one document | MUST |
| 030 | Results MUST be grouped by round type (one section per round) | MUST |
| 031 | Each round section MUST show: tasks done, tasks failed, total duration | MUST |
| 032 | The report MUST use health indicators: pass (all tasks succeeded), partial (some failed), fail (majority failed) | MUST |
| 033 | The report MUST list action items: tasks that failed or returned "blocked" status | MUST |
| 034 | The report MUST save to a dated file: `rondo-morning-YYYYMMDD.md` (or configurable pattern) | MUST |
| 035 | The report MUST include: total duration, total tasks run, total errors, timestamp | MUST |
| 036 | The report MUST include a usage summary: total cost, total tokens, overage status, watchdog interventions | MUST |

### Parallel Safety Contract
| ID | Requirement | Priority |
|----|-------------|----------|
| 058 | System SHALL default to sequential execution unless all tasks in the round declare `safe_parallel: true`. Tasks without explicit `safe_parallel` annotation MUST be executed sequentially even when `--workers > 1`. Violation ID: `REQ101-PARALLEL-SAFETY` | MUST |
| 059 | Parallel-safe tasks MUST either be read-only (no file writes) OR use explicit worktree isolation (reqs 037-041). File locking or atomic commit is required for shared filesystem writes outside of worktree isolation. Violation ID: `REQ101-PARALLEL-WRITE-SAFETY` | MUST |
| 060 | When `--workers > 1` and any task lacks `safe_parallel: true`, the runner MUST log a WARNING identifying which tasks will run sequentially and why | SHOULD |

### Worktree Isolation (Parallel Safety)
| ID | Requirement | Priority |
|----|-------------|----------|
| 037 | Parallel dispatch MUST support optional git worktree isolation: each worker gets its own worktree copy of the repo. Worktree isolation is the only guaranteed way to prevent file conflicts in parallel execution. Conflict detection (reqs 005-006) is advisory only | MUST |
| 038 | System SHALL when worktree isolation is enabled, each task runs in its own worktree. After all tasks complete, results are merged back to the main worktree | MUST |
| 039 | Worktree isolation MUST be opt-in via config (`worktree_isolation = true`) or CLI (`--worktree`). Default: off | MUST |
| 040 | System SHALL when worktree isolation is off, conflict detection (reqs 5-6) remains the safety mechanism | MUST |
| 041 | Worktrees MUST be cleaned up after the round completes (success or failure) | MUST |

### Result Spool (stateless persistence)
| ID | Requirement | Priority |
|----|-------------|----------|
| 042 | Rondo MUST maintain a spool directory (`~/.rondo/spool/`) for result files waiting for consumer pickup. Location configurable via `[spool] path` in config | MUST |
| 043 | After each task or round completes, Rondo MUST write a result JSON file to the spool directory with filename format `{ISO-timestamp}-{task_name}.json` (e.g., `2026-03-18T042315-forward-review.json`) | MUST |
| 044 | System SHALL consumers (OB, ACE, scripts) read and delete spool files — mailbox pattern. Once a consumer picks up a file, it is gone from the spool | MUST |
| 045 | If a consumer is connected at run time (e.g., OB calling Rondo via API), the result MUST go directly to the consumer — no spool file written. Spool is only for unattended/disconnected runs | MUST |
| 046 | System SHALL spool files have a configurable TTL: files older than N days are auto-cleaned on next Rondo invocation. Default: 7 days. Configurable via `[spool] ttl_days` | MUST |
| 047 | `rondo spool list` MUST show all pending result files: filename, age, size, task name. Sorted newest first | MUST |
| 048 | `rondo spool clean` MUST delete all expired files (older than TTL). With `--all` flag: delete everything regardless of age | MUST |
| 049 | `rondo spool export --since YYYY-MM-DD` MUST dump all spool files since the given date to a single JSON array on stdout — for manual import into OB or other tools | MUST |
| 050 | System SHALL the spool is NOT a database — no queries, no indexes, no schema migrations. Just JSON files with timestamps in a directory. Rondo stays stateless; the spool is a buffer between stateless Rondo and stateful consumers | MUST |
| 051 | Spool directory MUST be created automatically on first write if it does not exist. Permissions: user-only (0700) | MUST |
| 052 | If spool write fails (disk full, permissions), Rondo MUST log a WARNING and continue — never fail a task because the spool is broken. The task result is still returned to stdout/caller | MUST |

### Headless Dispatch

| ID | Requirement | Priority |
|----|-------------|----------|
| 053 | Rondo dispatch SHALL use --bare flag for headless Claude Code execution | MUST |
| 054 | --bare mode SHALL strip all hooks, LSP, and plugins from dispatched sessions | MUST |
| 055 | Rondo SHALL inject ONLY task-specific context (no global hooks) into --bare sessions | MUST |
| 056 | --bare sessions SHALL write JSONL transcript for collection (per CORE-IFS-006) | MUST |
| 057 | Rondo SHALL support both --bare (headless) and normal (interactive) dispatch modes | SHOULD |

---
## 4. Architecture / Design

### Layer Architecture (Rondo-REQ-101 on top of Rondo-REQ-100)

```
┌──────────────────────────────────────────────────────────────┐
│                   Rondo-REQ-101: AUTOMATION                        │
│                                                              │
│  L3: OVERNIGHT (overnight.py)                                │
│    Phase list → mode selection → sequential phase execution   │
│    Self-healing watchdog: kills hung tasks on output silence  │
│    Usage threshold gating: checks rate_limit_event per phase  │
│    Event log: rolling JSON (last 100 entries)                 │
│                                                              │
│  L2: PARALLEL (parallel.py)                                  │
│    ThreadPoolExecutor with configurable worker count          │
│    Throttle delay between task launches (default: 2s)         │
│    Conflict detection: files mentioned by 2+ tasks flagged    │
│    Results collected as futures complete (not submission order)│
│                                                              │
│  L3: REPORT (report.py)                                      │
│    Morning report: aggregates all phase results               │
│    Health indicators: pass/partial/fail per round             │
│    Action items: failed/blocked tasks listed                  │
│    Usage summary: cost, tokens, overage, watchdog events      │
│                                                              │
│  L4: SPOOL (spool.py)                                        │
│    Mailbox-pattern persistence for unattended runs            │
│    Result files with ISO-timestamp filenames                  │
│    TTL cleanup, CLI commands (list/clean/export)              │
│    Falls back gracefully on write failure (WARNING, not ERROR)│
│                                                              │
│         ▼ Uses Rondo-REQ-100: Engine + Dispatch + Runner ▼         │
└──────────────────────────────────────────────────────────────┘
```

### How Rondo-REQ-101 Extends Rondo-REQ-100

Rondo-REQ-101 builds on top of Rondo-REQ-100's sequential core by adding:

| Rondo-REQ-100 Provides | Rondo-REQ-101 Adds |
|-------------------|-------------|
| `engine.py` — Round, Task, Gate dataclasses | No changes — same data model |
| `dispatch.py` — single task dispatch | No changes — same dispatch, called from parallel workers |
| `runner.py` — sequential execution | `parallel.py` — wraps runner with ThreadPoolExecutor |
| `RoundResult` return object | `overnight.py` — chains multiple rounds into phases |
| Result JSON files in `results_dir` | `spool.py` — mailbox persistence for unattended runs |
| `cli.py` — `rondo run` | Adds `rondo overnight`, `rondo report`, `rondo spool` subcommands |

### Headless Dispatch (Claude Code --bare flag, v2.1.81+)

The `--bare` flag strips hooks, LSP, and plugins for clean headless execution. Rondo uses
this for all automated dispatch (both Rondo-REQ-100 batch and Rondo-REQ-101 overnight) to prevent
Caliber hooks, statusline, and other interactive-only features from interfering with
batch tasks. Task-specific context is injected via `--print-system-prompt` or CLAUDE.md
in the working directory.

**Interaction with Rondo-REQ-100 dispatch:** When `--bare` is available (Claude Code v2.1.81+),
Rondo-REQ-100's `dispatch.py` MUST add `--bare` to the subprocess command for all automated
(non-interactive) dispatches. Rondo-REQ-100 req 012 (`claude -p`) is the base command; `--bare`
is added alongside `--output-format stream-json` and `--model`.

### Timeout Coordination (Rondo-REQ-100 + Rondo-REQ-101)

Rondo-REQ-100 defines `task_timeout_sec` (hard wall-clock limit, default 300s) and
`round_timeout_sec` (default 3600s). Rondo-REQ-101 adds `watchdog_timeout_sec` (output
silence detector, default 60s).

```
                      Time →
Task starts
    │
    ├── Watchdog fires if no stdout for 60s ──→ kills task (ERR_WATCHDOG_TIMEOUT)
    │   (watchdog resets each time output is produced)
    │
    └── Task timeout fires at 300s ──→ kills task unconditionally (ERR_TIMEOUT)
        (hard limit regardless of output)
```

**Rules:**
1. `watchdog_timeout_sec` MUST be less than `task_timeout_sec` (watchdog fires first on silence)
2. `task_timeout_sec` is the absolute upper bound — watchdog cannot extend it
3. Both produce `error` status but with different `error_code` values for diagnostics

---

## 5. Data Model

Rondo-REQ-101 adds no database tables. All data structures extend Rondo-REQ-100's in-memory dataclasses:

| Dataclass | Module | Purpose |
|-----------|--------|---------|
| `ParallelResult` | parallel.py | Extends RoundResult with conflict list, speedup ratio, worker count |
| `OvernightResult` | overnight.py | Aggregates multiple RoundResults across phases |
| `PhaseResult` | overnight.py | One phase's execution: round name, status, duration, errors |
| `MorningReport` | report.py | Formatted aggregation of OvernightResult for human reading |
| `SpoolEntry` | spool.py | Metadata for a spool file: path, age, size, task name |
| `WatchdogEvent` | overnight.py | Kill/pause/skip event: timestamp, reason, task name |
| `EventLogEntry` | overnight.py | Rolling log entry: timestamp, event type, mode, phase |

**No tables owned.** Rondo-REQ-101 inherits Rondo-REQ-100's "no database" principle.
Spool files are JSON on disk, not database records.

---

## 6. Data Boundary

### What Rondo-REQ-101 Produces

| Output | Format | Consumer |
|--------|--------|----------|
| `OvernightResult` | Python dataclass | Calling code or spool |
| Spool files | JSON in `~/.rondo/spool/` (configurable) | Consumer pickup via mailbox pattern |
| Morning report | Markdown file `rondo-morning-YYYYMMDD.md` | Human reader |
| Event log | Rolling JSON (last 100 entries) | Post-mortem analysis |

### What Rondo-REQ-101 Consumes

| Input | Format | Producer |
|-------|--------|----------|
| Rondo-REQ-100 RoundResult | Python dataclass | runner.py / dispatch.py |
| Overnight config | TOML (modes, phases, thresholds) | User / project config |
| Rate limit data | `rate_limit_event` from stream-json | Previous dispatch result |

### Spool vs results_dir

| Attribute | `results_dir` (Rondo-REQ-100) | `spool/` (Rondo-REQ-101) |
|-----------|------------------------|---------------------|
| Purpose | Backup for crash recovery | Mailbox for unattended pickup |
| Lifetime | Permanent (user manages) | TTL-based cleanup (default 7 days) |
| When written | Always (every round) | Only when no consumer connected |
| Consumer reads | Replay / debugging | Consumer picks up and deletes |

**Two distinct storage paths (neither is a database):**

1. **`results_dir`** — Consumer-owned backup. Write-once archive of RoundResults.
   Immutable after write. Consumer manages retention. Always written (every round).
2. **`spool/`** — Rondo-owned mailbox. Stateful buffer with TTL/CLEAN/EXPORT lifecycle
   for disconnected consumers. Written only when no consumer is connected at runtime.

Both exist. They serve different purposes. Neither supports queries, indexes, or
schema migrations. `results_dir` is permanent backup. Spool is a transient mailbox.

---

## 7. MCP / API Interface

Not applicable for this spec type — see related sections for details.

---

## 8. States & Modes

### Overnight Scheduler States

```
idle ──→ preflight ──→ running_phases ──→ reporting ──→ done
                  │                  │
                  └──→ aborted       └──→ partial (some phases failed)
                       (RED preflight)
```

### Phase States

```
pending ──→ in_progress ──→ done | error | partial
```

Phase failures do NOT block subsequent phases (req 012). A phase with status `error`
is logged and the scheduler proceeds to the next phase.

---

## 9. Configuration

Configuration follows Rondo-STD-109 conventions. Extends Rondo-REQ-100's config:

| Setting | CLI Flag | Config Key | Default | Description |
|---------|----------|------------|---------|-------------|
| Workers | `--workers N` | `workers` | 4 (overnight) | Parallel worker count |
| Throttle | `--throttle N` | `throttle_sec` | 2 | Seconds between task launches |
| Mode | `--mode M` | `overnight_mode` | `standard` | Phase selection: minimal, standard, full |
| Overage action | `--on-overage` | `on_overage` | `continue` | Action on overage: continue, pause, stop |
| Watchdog timeout | `--watchdog-timeout` | `watchdog_timeout_sec` | 60 | Seconds of output silence before kill |
| Spool path | `--spool-path` | `spool.path` | `~/.rondo/spool/` | Spool directory location |
| Spool TTL | `--spool-ttl` | `spool.ttl_days` | 7 | Days before spool files are auto-cleaned |
| Worktree isolation | `--worktree` | `worktree_isolation` | `false` | Enable git worktree per worker |
| Report pattern | `--report-pattern` | `report_pattern` | `rondo-morning-YYYYMMDD.md` | Morning report filename |
| Event log size | — | `event_log_max_entries` | 100 | Rolling event log capacity |

All settings follow COALESCE: CLI flag → config file → built-in default.

---

## 10. Rules & Constraints

| Rule | Rationale |
|------|-----------|
| Phases don't block each other | One bad phase must not kill the whole overnight run. Resilience over strictness. |
| Parallel is opt-in | Default is sequential (Rondo-REQ-100). Parallel requires explicit --workers flag. |
| Conflict detection is advisory | Flags potential issues but doesn't prevent execution. Consumer decides. |
| No interactive input in overnight | Must run unattended from cron/LaunchAgent. Zero stdin. |
| Morning report is always generated | Even if all phases fail. "Everything failed" is still a useful report. |

---

## 11. Quality Attributes

| Attribute | Target | How Measured |
|-----------|--------|-------------|
| Throughput | 4x speedup with 4 workers vs sequential | Speedup ratio in summary |
| Resilience | 95%+ overnight runs complete all phases | Event log analysis |
| Visibility | Morning report readable in <30 seconds | Inspection |
| Isolation | Single task failure never affects other tasks | Exception handling test |

---

## 12. Shared Patterns / Tactical Solutions

### Tactical Solutions (per CORE-STD-022)

| TAC ID | Title | Dependency | Break Risk | Status |
|--------|-------|------------|------------|--------|
| TAC-RON-001 | `claude -p` non-interactive mode | Relies on `claude -p` behaving predictably; no formal API contract | CLI changes break all overnight dispatch | active |
| TAC-RON-002 | JSONL as primary storage | No formal schema; parsing relies on line-by-line JSON | Schema changes break result parsing | active |

### Shared Patterns

- **Phase-continue-on-failure:** Each phase logs errors and continues to the next. One bad phase does not kill the run.
- **Mailbox spool:** Consumer picks up and deletes spool files. No query interface — just files in a directory.
- **Watchdog-then-timeout:** Watchdog detects silence; task_timeout is the hard upper bound.

---

## 13. Integration Points

| Integration | Spec | Direction | Contract |
|-------------|------|-----------|----------|
| Core engine | Rondo-REQ-100 | Depends on | Imports Round, Task, Gate, RoundResult, dispatch_task, run_round |
| Preflight | Rondo-REQ-103 | Depends on | Cached PreflightResult used for overnight batch (run once at start) |
| Configuration | Rondo-STD-109 | Depends on | Worker count, throttle, modes, spool path, TTL from TOML config |
| Error handling | Rondo-STD-108 | Shared | TaskResult error codes, status vocabulary |
| Concurrency | Rondo-STD-110 | Applies | ThreadPoolExecutor safety, no shared mutable state between tasks |
| OB integration | Rondo-IFS-102 | Outbound | OvernightResult returned for OB storage |
| Morning report | Consumer | Outbound | Markdown file readable by human or downstream tools |
| Spool | Consumer | Outbound | JSON files in spool directory for consumer pickup |

---

## 14. Standards Applied

| Standard | How Applied |
|---------|-------------|
| Rondo-STD-108 Error & Resilience | Phase failures logged and continued. Task exceptions isolated. Overnight always produces a report. |
| Rondo-STD-109 Configuration | Worker count, throttle, modes all configurable via TOML + CLI. |
| Rondo-STD-110 Concurrency & Safety | ThreadPoolExecutor with throttle. Conflict detection for parallel writes. No shared mutable state between tasks. |
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
| A1 | ThreadPoolExecutor is sufficient (I/O-bound, not CPU-bound) | ProcessPoolExecutor if CPU work needed — unlikely for subprocess dispatch |
| A2 | 4 concurrent Claude sessions won't trigger rate limiting | Reduce workers or increase throttle if throttled |
| A3 | File conflict detection via output parsing is sufficient | May need explicit file locking for write-heavy rounds |
| A4 | 100-entry rolling log is sufficient for post-mortem | Increase if overnight runs generate more events |
| A5 | Phases are independent enough to continue after failure | Some phases may depend on prior phase output — caller's responsibility to handle |
| A6 | Python 3.12+ is available (inherited from Rondo-REQ-100 for `tomllib`) | Fall back to `tomli` package for 3.11. See Rondo-REQ-100 assumption A6 |

---

## 17. Success Criteria

| Scenario | Expected Result | Verification |
|----------|----------------|--------------|
| 4-worker parallel dispatch | 4 tasks run concurrently, all results collected | Demonstration |
| Throttle between launches | 2-second gap between task starts | Test (check timestamps) |
| Conflict detection | Two tasks mentioning same file flagged in summary | Test |
| Single task failure in parallel | Other tasks complete normally | Test |
| Speedup ratio reported | Ratio > 1.0 for multi-task rounds | Test |
| Overnight 3 phases, 1 fails | Failed phase logged, other 2 complete, report generated | Test |
| Mode selection | Minimal runs fewer phases than full | Test |
| Morning report generated | File exists, grouped by round, health indicators present | Inspection |
| Action items listed | Failed/blocked tasks appear in report | Test |
| Event log rolling | After 101 events, oldest dropped, file has 100 entries | Test |
| No interactive input | Overnight completes without stdin | Demonstration |

---

## Design

### Architecture (Rondo-REQ-101 on top of Rondo-REQ-100)

```
┌────────────────────────────────────────────────────┐
│                   Rondo-REQ-101: AUTOMATION                   │
│                                                     │
│  ┌──────────────────────────────────────────────┐  │
│  │           OVERNIGHT (L3)                      │  │
│  │   Phase list, mode selection, event log       │  │
│  └──────────────────────────────────────────────┘  │
│                        │                            │
│  ┌──────────────────────────────────────────────┐  │
│  │           PARALLEL (L2)                       │  │
│  │   ThreadPoolExecutor, throttle, conflicts     │  │
│  └──────────────────────────────────────────────┘  │
│                        │                            │
│  ┌──────────────────────────────────────────────┐  │
│  │            REPORT (L3)                        │  │
│  │   Aggregation, health indicators, actions     │  │
│  └──────────────────────────────────────────────┘  │
│                                                     │
│         ▼ Uses Rondo-REQ-100: Engine + Dispatch + Runner ▼    │
└────────────────────────────────────────────────────┘
```

### Overnight Phase Flow

```
overnight(mode, phases)
    │
    ├── Phase 1: round_a (all specs)
    │     ├── pre-gates
    │     ├── tasks (sequential or parallel)
    │     ├── post-gates
    │     └── results → collector
    │
    ├── Phase 2: round_b (project-wide)
    │     ├── ... (same pattern)
    │     └── results → collector
    │
    ├── Phase N: ...
    │     └── (if error: log, continue)
    │
    └── generate_report(collector) → morning file
```

### Conflict Detection

Simple heuristic: scan each task's raw output for file paths (words containing `/` and common extensions). If the same path appears in 2+ task outputs, flag as potential conflict.

This is a warning system, not a prevention system. The consumer decides how to handle conflicts.

### Configurable Modes

The overnight scheduler doesn't hardcode which rounds go in which mode. The caller provides:

```python
overnight_config = {
    "minimal": [round_a],
    "standard": [round_a, round_b, round_c],
    "full": [round_a, round_b, round_c, round_d, round_e],
}

run_overnight(mode="standard", config=overnight_config)
```

This keeps Rondo generic — OB defines its phases, ACE defines its phases, a third-party project defines its own.

---

## 18. Build Notes / Estimate

Tracked during implementation. Cross-ref ACE-STD-019 for systematic self-correction.

---

## 19. Test Categories

Tracked during implementation. Cross-ref ACE-STD-019 for systematic self-correction.

---

## 20. Failure Modes

| Failure | Impact | Detection | Mitigation |
|---------|--------|-----------|------------|
| Watchdog kills healthy task (false positive) | Valid work lost, task marked error | Event log shows ERR_WATCHDOG_TIMEOUT on task that was producing output | Increase `watchdog_timeout_sec`. Review event log — if output was being produced, watchdog timer wasn't resetting (bug). |
| All workers rate-limited simultaneously | Overnight run stalls, phases timeout | Usage threshold gating detects `blocked` status | `on_overage: pause` waits for reset. Reduce worker count to stay under rate limits. |
| Spool directory fills disk | Subsequent spool writes fail (WARNING), tasks still succeed but results not persisted for pickup | Spool write failure logged as WARNING (req 052) | Reduce `spool.ttl_days`. Run `rondo spool clean --all`. Monitor disk space in preflight (Rondo-REQ-103 req 008). |
| Task timeout fires during valid long-running task | Work lost, task marked ERR_TIMEOUT | Task result shows error_code ERR_TIMEOUT | Increase `task_timeout_sec` for known long tasks. Use per-task timeout overrides. |
| Phase dependency not declared | Phase N+1 runs with incomplete input from failed Phase N | Morning report shows Phase N failed + Phase N+1 produced unexpected results | Phases are independent by design (req 012). If phases have dependencies, caller must encode them in phase ordering and check prior phase results. |
| Worktree merge conflict after parallel execution | Results from isolated worktrees can't merge cleanly | Git merge failure logged in event log | Manual conflict resolution. Consider making conflicting tasks sequential instead. |
| Morning report generation fails | No visibility into overnight results | Report generation error logged, raw OvernightResult still available | Fall back to raw JSON results in results_dir. Fix report template. |

---

## 21. Dependencies + Used By

| Depends On | Why |
|------------|-----|
| Rondo-REQ-100 (Core) v1.0+ | Engine, dispatch, runner — the entire execution substrate |
| Rondo-REQ-103 (Preflight) | Cached preflight for overnight batch |
| Rondo-STD-108 (Error & Resilience) | TaskResult fields, error codes |
| Rondo-STD-109 (Configuration) | TOML config loading, CLI flags (--workers, --model, etc.) |
| Rondo-STD-110 (Concurrency & Safety) | ThreadPoolExecutor patterns, no shared mutable state |
| CORE-STD-001 (Data Standards) | Status vocabulary alignment (7-value lifecycle) |
| Python 3.12+ | `tomllib` in stdlib (inherited from Rondo-REQ-100) |

| Used By | Why |
|---------|-----|
| Rondo-IFS-102 (OB Integration) | OB consumes OvernightResult for sprint tracking |
| Consumer scripts | Pick up spool files via mailbox pattern |

---

## 22. Decisions

| # | Decision | Date | Why |
|---|----------|------|-----|
| D1 | ThreadPoolExecutor over ProcessPool | 2026-03-13 | Dispatch is I/O-bound (waiting on subprocess). Threads are simpler. |
| D2 | Configurable modes, not hardcoded phases | 2026-03-13 | Rondo is generic. OB/ACE/others define their own phase lists. |
| D3 | Conflict detection is advisory only | 2026-03-13 | Prevention would require file locking — too complex for v1. Warnings are enough. |
| D4 | Morning report always generated | 2026-03-13 | "Everything failed" is still valuable information at 6am. |
| D5 | Rolling event log (100 entries) | 2026-03-13 | Simple, bounded, sufficient for post-mortem without growing unbounded. |

---

## 23. Open Questions

| # | Question | Status |
|---|----------|--------|
| Q1 | Should parallel support a max-concurrent-per-model limit? (e.g., max 2 opus at once) | Open |
| Q2 | Should overnight support `--resume` from a failed phase? | Open |
| Q3 | Should the morning report support multiple output formats (markdown, JSON, HTML)? | Open |
| Q4 | How should the scheduler handle system-level scheduling (cron vs LaunchAgent vs systemd)? | Deferred — platform-specific |
| Q5 | Should Rondo support alternative backends (Codex CLI, Ollama, direct API)? | Deferred — Rondo-IFS-100 isolates the interface. Adding Rondo-IFS-101 for other backends is architecturally possible without changing Rondo-REQ-100/002. |
| Q6 | Should worktree isolation use `git worktree` directly or Claude Code's `--worktree` flag? | Open — Claude Code has native worktree support via `--worktree` flag |

---

## 24. Glossary

Not applicable for this spec type — see related sections for details.

---

## 25. Risk / Criticality

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Rate limit exhaustion during overnight run | Medium | Overnight run stalls or produces partial results | Usage threshold gating (reqs 024-028). `on_overage: pause` waits for reset window. Reduce worker count. |
| Parallel file conflicts corrupt working tree | Low | Modified files in inconsistent state | Worktree isolation (reqs 037-041). Conflict detection (reqs 005-006) as advisory. `safe_parallel` annotation (req 058). |
| Watchdog false positives kill valid tasks | Low | Wasted API spend, lost results | Tunable `watchdog_timeout_sec`. Event log for post-mortem. Task-level timeout override. |
| Overnight run exceeds cost budget | Medium | Unexpected charges on API key auth | Usage summary in morning report (req 036). `on_overage: stop` halts early. Prefer Max plan auth for overnight. |
| Spool files accumulate without consumer pickup | Low | Disk space consumed, stale results | TTL cleanup (req 046). `rondo spool clean` command (req 048). Preflight disk check (Rondo-REQ-103 req 008). |
| Claude Code CLI breaking change between versions | Low | All overnight dispatch fails silently | Preflight smoke test (Rondo-REQ-103 reqs 017-024). Version-keyed cache invalidation (Rondo-REQ-103 req 020). |

---

## 26. External Scan

Not applicable for this spec type — see related sections for details.

---

## 27. Security Considerations

| Concern | Risk | Mitigation |
|---------|------|------------|
| API keys in overnight environment | Keys persist in env vars for hours during unattended runs | Auth switching (Rondo-REQ-100 reqs 019-021): Max plan auth strips API key entirely. API key auth preserves it only in child process env, never logged to result files. |
| Headless dispatch runs without human review | Automated tasks could modify files, execute code without oversight | `--bare` flag strips hooks/plugins. `tool_mode` controls file access (Rondo-REQ-100 reqs 022-024). `permission_mode` controls permission prompts. Read-only tasks should use `tool_mode: none`. |
| Spool files contain task results on disk | Sensitive AI output persists in plaintext JSON | Spool directory permissions: user-only 0700 (req 051). TTL cleanup limits exposure window. Consumer should encrypt/redact sensitive results after pickup. |
| CLAUDECODE env var nesting trap | Nested subprocess hangs indefinitely | Always stripped (Rondo-REQ-100 req 013). Preflight detects presence (Rondo-REQ-103 req 010). Smoke test verifies stripping works (Rondo-REQ-103 req 023). |
| Overnight runs with `--dangerously-skip-permissions` | Full file system access without human approval | Only for containerized/sandboxed environments with no network. Task `tool_mode: sandbox` must be explicitly set. Never default to sandbox mode. |
| Event log contains dispatch metadata | Timestamps, models, task names could reveal project structure | Event log is local-only (not transmitted). Rolling window limits retention to 100 entries. No API keys or response content in event log. |

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
| Parallel task execution | THEORY | Specced for concurrent task dispatch | Phase 2 build |
| Overnight scheduling | THEORY | Specced for unattended batch processing | Phase 2 build |
| Morning reports | THEORY | Specced for overnight result summaries | Phase 2 build |
| Task queue management | THEORY | Specced for priority-based execution | Phase 2 build |


## 35. Change History

| Version | Date | What Changed |
|---------|------|-------------|
| 0.1 | 2026-03-13 | Split from monolithic RONDO-01. Parallel + overnight + report as optional layer. |
| 0.2 | 2026-03-14 | Added: self-healing watchdog (reqs 19-23), usage threshold gating (reqs 24-28), morning report usage summary (req 36), worktree isolation (reqs 37-41). 25→41 requirements. |
| 0.3 | 2026-03-14 | Deep review fixes: clarified watchdog vs task timeout relationship (reqs 19-20), cross-referenced CORE-IFS-001 reqs 53-54 (status vocabulary) |
| 0.4 | 2026-03-18 | Result Spool — stateless persistence (reqs 42-52). Mailbox-pattern spool directory for disconnected runs. TTL cleanup, CLI commands, export for manual import. 52 requirements total. |
| 0.5 | 2026-03-23 | Added Headless Dispatch group (reqs 053-057). --bare flag for clean headless execution (Claude Code v2.1.81+). Architecture note for dispatch modes. 57 requirements total. |
| 0.6 | 2026-03-25 | 4-AI cross-review fixes (OpenAI/Gemini/Mistral/Grok): Filled §4 Architecture/Design (layer diagram, how Rondo-REQ-101 extends Rondo-REQ-100, headless dispatch interaction, timeout coordination diagram). Filled §5 Data Model (7 dataclasses). Filled §6 Data Boundary (spool vs results_dir clarification). Filled §13 Integration Points (8 integrations). Filled §21 Dependencies + Used By (added CORE-STD-001, Python 3.12+, Rondo-STD-110). Upgraded req 037 worktree isolation from SHOULD to MUST. Added §12 Tactical Solutions (TAC-RON-001, TAC-RON-002). Added assumption A6 (Python 3.12+). Updated dependencies header. |
| 0.7 | 2026-03-25 | Grok cross-review fixes: (M4) §6 Data Boundary clarified two distinct storage paths with owner/purpose/lifecycle. (M5) Added reqs 058-060: parallel safety contract — `safe_parallel: true` annotation required, read-only or worktree isolation enforced, sequential fallback with WARNING. (M6) Filled §20 Failure Modes (7 scenarios with detection/mitigation). Filled §25 Risk/Criticality (6 risks with likelihood/impact). Filled §27 Security Considerations (6 concerns with mitigations). 60 requirements total. |
