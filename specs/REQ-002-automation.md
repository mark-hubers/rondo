# REQ-002: Automation — Parallel + Overnight + Report

*Run many tasks fast, schedule them overnight, get a morning report.*

**Created:** 2026-03-13 | **Status:** DRAFT
**Depends on:** REQ-001 (Core) | **Blocks:** Nothing
**Author:** Mark Hubers — HubersTech

---

## Item 1: Purpose & Scope

**What this spec does (plain English):**
Adds parallel execution, overnight batch scheduling, and morning reports on top of REQ-001's core. REQ-001 dispatches one task at a time. REQ-002 dispatches many tasks at once, chains rounds into overnight phases, and summarizes results for the morning.

**IN scope:**
- Parallel dispatch: concurrent task execution with throttling
- Conflict detection: flag files touched by multiple parallel tasks
- Overnight scheduler: phased batch execution with configurable modes
- Morning report: aggregated results with health indicators
- Event logging: rolling log for overnight post-mortem

**OUT of scope:**
- Engine, dispatch, auth, model routing (REQ-001: Core)
- Specific round definitions (consumer's responsibility)
- System-level scheduling (cron/LaunchAgent config — platform-specific)
- Real-time monitoring / dashboards (future work)

---

## The Problem

REQ-001 runs tasks sequentially — one at a time. A round with 8 tasks at 3 minutes each takes 24 minutes. Running 32 specs through that takes 12+ hours. That exceeds overnight capacity.

**Parallel execution** solves throughput: 4 workers cut wall time by ~4x. But parallel introduces risks — two tasks modifying the same file, rate limiting from too many concurrent Claude sessions, results arriving out of order.

**Overnight scheduling** solves automation: define which rounds run in what order, handle phase failures gracefully, produce a summary before morning. The human defines the schedule. Rondo runs it unattended.

**Morning reports** solve visibility: "what happened last night?" must be answerable in 30 seconds by reading one file.

---

## Requirements

### Parallel Execution

1. Parallel dispatch MUST use `concurrent.futures.ThreadPoolExecutor` with configurable worker count.
2. Worker count MUST be configurable via CLI (`--workers N`) and config file. Default: 4.
3. Parallel dispatch MUST support a configurable throttle delay between task launches. Default: 2 seconds.
4. Results MUST be collected as futures complete (not in submission order).
5. Parallel dispatch MUST detect potential file conflicts: files mentioned in output by 2+ concurrent tasks.
6. Detected conflicts MUST be listed in the round summary (not silently ignored).
7. Parallel dispatch MUST report: done count, error count, wall time, sum of task times, speedup ratio.
8. If a single task fails or raises an exception, other tasks MUST NOT be affected.
9. Parallel results MUST be saved to the same JSON format as sequential results (REQ-001 compatibility).

### Overnight Scheduler

10. The overnight scheduler MUST accept a list of round definitions to execute in order (phases).
11. Phases MUST execute sequentially (one completes before next starts). Tasks within a phase MAY be parallel.
12. Phase failures MUST NOT block subsequent phases. Log the error, continue to next phase.
13. The scheduler MUST support configurable modes that select which phases run.
14. At minimum, 3 modes MUST be supported: minimal (1-2 phases), standard (3-4 phases), full (all phases).
15. Mode names and phase assignments MUST be configurable (not hardcoded to OB/ACE rounds).
16. The scheduler MUST be invocable from command line with no interactive input required.
17. The scheduler MUST log start and end events with timestamps and mode.
18. The event log MUST be a rolling JSON file that keeps the last 100 entries.

### Morning Report

19. The morning report MUST aggregate results from all phases in one document.
20. Results MUST be grouped by round type (one section per round).
21. Each round section MUST show: tasks done, tasks failed, total duration.
22. The report MUST use health indicators: pass (all tasks succeeded), partial (some failed), fail (majority failed).
23. The report MUST list action items: tasks that failed or returned "blocked" status.
24. The report MUST save to a dated file: `rondo-morning-YYYYMMDD.md` (or configurable pattern).
25. The report MUST include: total duration, total tasks run, total errors, timestamp.

---

## Assumptions

| # | Assumption | If Wrong |
|---|-----------|----------|
| A1 | ThreadPoolExecutor is sufficient (I/O-bound, not CPU-bound) | ProcessPoolExecutor if CPU work needed — unlikely for subprocess dispatch |
| A2 | 4 concurrent Claude sessions won't trigger rate limiting | Reduce workers or increase throttle if throttled |
| A3 | File conflict detection via output parsing is sufficient | May need explicit file locking for write-heavy rounds |
| A4 | 100-entry rolling log is sufficient for post-mortem | Increase if overnight runs generate more events |
| A5 | Phases are independent enough to continue after failure | Some phases may depend on prior phase output — caller's responsibility to handle |

---

## Success Criteria

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

### Architecture (REQ-002 on top of REQ-001)

```
┌────────────────────────────────────────────────────┐
│                   REQ-002: AUTOMATION                   │
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
│         ▼ Uses REQ-001: Engine + Dispatch + Runner ▼    │
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

## Rules & Constraints

| Rule | Rationale |
|------|-----------|
| Phases don't block each other | One bad phase must not kill the whole overnight run. Resilience over strictness. |
| Parallel is opt-in | Default is sequential (REQ-001). Parallel requires explicit --workers flag. |
| Conflict detection is advisory | Flags potential issues but doesn't prevent execution. Consumer decides. |
| No interactive input in overnight | Must run unattended from cron/LaunchAgent. Zero stdin. |
| Morning report is always generated | Even if all phases fail. "Everything failed" is still a useful report. |

---

## Quality Attributes

| Attribute | Target | How Measured |
|-----------|--------|-------------|
| Throughput | 4x speedup with 4 workers vs sequential | Speedup ratio in summary |
| Resilience | 95%+ overnight runs complete all phases | Event log analysis |
| Visibility | Morning report readable in <30 seconds | Inspection |
| Isolation | Single task failure never affects other tasks | Exception handling test |

---

## Foundations Applied

| Standard | How Applied |
|---------|-------------|
| STD-001 Error & Resilience | Phase failures logged and continued. Task exceptions isolated. Overnight always produces a report. |
| STD-002 Configuration | Worker count, throttle, modes all configurable via TOML + CLI. |
| STD-003 Concurrency & Safety | ThreadPoolExecutor with throttle. Conflict detection for parallel writes. No shared mutable state between tasks. |

---

## Decisions

| # | Decision | Date | Why |
|---|----------|------|-----|
| D1 | ThreadPoolExecutor over ProcessPool | 2026-03-13 | Dispatch is I/O-bound (waiting on subprocess). Threads are simpler. |
| D2 | Configurable modes, not hardcoded phases | 2026-03-13 | Rondo is generic. OB/ACE/others define their own phase lists. |
| D3 | Conflict detection is advisory only | 2026-03-13 | Prevention would require file locking — too complex for v1. Warnings are enough. |
| D4 | Morning report always generated | 2026-03-13 | "Everything failed" is still valuable information at 6am. |
| D5 | Rolling event log (100 entries) | 2026-03-13 | Simple, bounded, sufficient for post-mortem without growing unbounded. |

---

## Open Questions

| # | Question | Status |
|---|----------|--------|
| Q1 | Should parallel support a max-concurrent-per-model limit? (e.g., max 2 opus at once) | Open |
| Q2 | Should overnight support `--resume` from a failed phase? | Open |
| Q3 | Should the morning report support multiple output formats (markdown, JSON, HTML)? | Open |
| Q4 | How should the scheduler handle system-level scheduling (cron vs LaunchAgent vs systemd)? | Deferred — platform-specific |

---

## Change History

| Version | Date | What Changed |
|---------|------|-------------|
| 0.1 | 2026-03-13 | Split from monolithic RONDO-01. Parallel + overnight + report as optional layer. |
