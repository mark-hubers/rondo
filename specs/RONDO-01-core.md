# RONDO-01: Core Framework

*Python-orchestrated AI task dispatch — the conductor that runs Claude overnight.*

**Created:** 2026-03-13 | **Status:** DRAFT
**Depends on:** Claude Code CLI (`claude -p`) | **Blocks:** RONDO-02 (Round Catalog)
**Author:** Mark Hubers — HubersTech

---

## Item 1: Purpose & Scope

**What this spec does (plain English):**
Defines the Rondo framework — a Python program that dispatches tasks to Claude Code, runs them in parallel, chains them into rounds, and schedules overnight batch work. Python is the conductor. Claude is the orchestra.

**IN scope:**
- Engine: Round, Task, Gate data model
- Dispatch: `claude -p` subprocess orchestration
- Auth: Max plan vs API key switching
- Model routing: opus/sonnet/haiku per task
- Parallel execution: concurrent task dispatch
- Overnight scheduler: phased batch runs
- Morning report: result aggregation
- Round definitions: the pattern (not individual round content)
- Configuration: how Rondo is configured
- Error handling: what happens when tasks fail

**OUT of scope:**
- Individual round definitions (RONDO-02: Round Catalog)
- Claude Code internals (Anthropic's product)
- OB database integration (OB-01: Orbital Database)
- ACE2 internals (separate product)
- Ollama/local LLM backend (future — RONDO-03 when needed)

---

## The Problem

Claude Code's Max plan ($200/month) includes unlimited usage — but only while a human is typing. Every night, 8+ hours of AI capacity sits idle. That's ~240 hours/month of wasted compute.

Meanwhile, real work piles up:
- 136 specs need health checks (staleness, missing sections, broken cross-refs)
- Digests go stale within days of spec changes
- Convention violations accumulate between manual scans
- Knowledge from conversations evaporates after compaction
- PR reviews happen manually or not at all
- Test coverage gaps grow invisibly

Manual AI work is expensive in human attention. Mark runs opus all day for real work. Using that same capacity at 10pm for automated QA costs $0 extra but delivers real value every morning.

**The core insight:** AI work can be decomposed into tasks with clear inputs, instructions, and completion criteria. If those tasks can be dispatched programmatically, they can run unsupervised overnight.

**Why Python, not shell scripts:**
- Shell scripts can't manage 4 concurrent Claude processes
- Shell can't parse JSON results, detect conflicts, or generate reports
- Shell can't implement gate logic (pre-conditions that block a round)
- Python's `subprocess`, `concurrent.futures`, and `json` are purpose-built for this

---

## Requirements

### Engine (Round/Task/Gate pattern)

1. A **Round** MUST contain: a name, zero or more pre-gates, one or more tasks, zero or more post-gates.
2. A **Task** MUST have: a name, a mode (auto or interactive), and a status (pending/running/passed/failed/skipped).
3. An **interactive task** MUST have: an instruction (what to do), context files (what to read), and a done-when (completion criteria). This is the **three-field contract**: Do, Read, Done.
4. An **auto task** MUST have: a Python callable that returns (passed: bool, detail: str).
5. A **Gate** MUST have: a name, a check function, and a blocking flag. Blocking gates halt the round on failure.
6. Pre-gates MUST run before any task dispatch. If a blocking pre-gate fails, no tasks run.
7. Post-gates MUST run only after all tasks complete.
8. Task status transitions MUST follow: pending → running → passed|failed|skipped. No other transitions allowed.
9. Round state (task statuses, gate results) MUST be serializable to JSON for compaction recovery.

### Dispatch (claude -p orchestration)

10. Dispatch MUST invoke `claude -p` as a subprocess with the task's three-field contract as the prompt.
11. Dispatch MUST strip the `CLAUDECODE` environment variable from child processes to prevent the nested-session guard.
12. When auth is "max", dispatch MUST strip `ANTHROPIC_API_KEY` from the child environment so Claude uses the subscription plan.
13. When auth is "api", dispatch MUST preserve `ANTHROPIC_API_KEY` in the child environment.
14. Dispatch MUST pass `--model` to select opus, sonnet, or haiku per task.
15. Model selection MUST follow the COALESCE pattern: CLI override → task hint → default (sonnet).
16. Dispatch MUST capture stdout, stderr, exit code, and duration from each subprocess.
17. Dispatch MUST request structured JSON output from Claude: `{status, confidence, result, question}`.
18. If a subprocess returns exit code != 0 or empty stdout, dispatch MUST record status "error" with stderr content.
19. Dispatch MUST save each task result to a JSON file in the results directory.
20. Dispatch MUST support dry-run mode that shows the prompt without invoking Claude.

### Parallel Execution

21. Parallel dispatch MUST use `concurrent.futures.ThreadPoolExecutor` with configurable worker count.
22. Parallel dispatch MUST support a configurable throttle delay between task launches to respect rate limits.
23. Parallel dispatch MUST collect results as futures complete (not in submission order).
24. Parallel dispatch MUST detect potential file conflicts: files mentioned by 2+ concurrent tasks.
25. Parallel dispatch MUST report speedup ratio: sum(task durations) / wall clock time.
26. Worker count MUST default to 4. Throttle MUST default to 2 seconds.

### Overnight Scheduler

27. The overnight scheduler MUST support 3 modes: quick (health only), default (health + convention + digest), full (all phases).
28. The overnight scheduler MUST execute phases in dependency order: spec-health → convention → digest-refresh → knowledge-mine → test-gaps.
29. Phase failures MUST NOT block subsequent phases (log error, continue).
30. The overnight scheduler MUST generate a morning report summarizing all phase results.
31. The overnight scheduler MUST maintain a rolling event log (last 100 entries) for post-mortem analysis.
32. The overnight scheduler MUST be invocable from cron/LaunchAgent with no interactive input required.

### Morning Report

33. The morning report MUST group results by round type.
34. The morning report MUST color-code health: GREEN (all pass), YELLOW (partial), RED (majority fail).
35. The morning report MUST list action items from blocked or failed tasks.
36. The morning report MUST save to a dated file: `rondo-morning-YYYYMMDD.md`.

### Configuration

37. Rondo MUST be configurable via a TOML file at `rondo/config.toml` (F05 pattern: file-based config).
38. Configurable values MUST include: default auth mode, default model, worker count, throttle delay, results directory, report directory.
39. CLI flags MUST override config file values. Config file MUST override defaults. (COALESCE: CLI → config → default.)

### Error Handling

40. Every task failure MUST include: task name, error message, duration, and the prompt that was sent.
41. Subprocess timeouts MUST be configurable (default: 5 minutes per task).
42. If Claude returns malformed JSON, dispatch MUST fall back to treating raw output as the result with status "partial".
43. Network/auth errors MUST be distinguishable from task-logic errors in the result JSON.

---

## Assumptions

| # | Assumption | If Wrong |
|---|-----------|----------|
| A1 | `claude -p` accepts arbitrary prompts via CLI and returns text to stdout | Rondo cannot function — core dependency |
| A2 | Max plan allows unlimited `claude -p` invocations (no hidden rate limit) | Overnight runs may hit throttling — need backoff strategy |
| A3 | `CLAUDECODE` env var is the only nested-session guard | Other guards may block child dispatch — test each Claude version |
| A4 | Stripping `ANTHROPIC_API_KEY` causes Claude to fall back to subscription auth | May need explicit flag instead — test empirically |
| A5 | Claude can return structured JSON when instructed in the prompt | If not reliable, need output parsing/extraction fallback |
| A6 | ThreadPoolExecutor threads are sufficient (no need for ProcessPoolExecutor) | CPU-bound work would need processes — but dispatch is I/O-bound (waiting on subprocess) |
| A7 | 4 concurrent Claude instances won't trigger rate limiting on Max plan | If throttled, reduce workers or increase throttle delay |
| A8 | `claude -p` is available on the system PATH | Need explicit path or config for Claude binary location |

---

## Success Criteria

| Scenario | Expected Result | Verification |
|----------|----------------|--------------|
| Single task dispatch (auth=max) | Claude runs, returns JSON, result saved | Test |
| Single task dispatch (auth=api) | Uses API key, charges account | Test |
| Model routing (opus/sonnet/haiku) | Correct --model flag passed to subprocess | Test |
| Dry-run mode | Prompt displayed, no subprocess launched | Test |
| Pre-gate failure (blocking) | Round halts, no tasks dispatched | Test |
| Pre-gate failure (non-blocking) | Warning logged, tasks proceed | Test |
| Parallel 4-worker dispatch | 4 tasks run concurrently, results collected | Demonstration |
| Conflict detection | Two tasks touching same file flagged | Test |
| Overnight quick mode | Only spec-health phase runs | Test |
| Overnight full mode | All 5 phases run in order | Demonstration |
| Subprocess error (exit code 1) | Error recorded with stderr, round continues | Test |
| Malformed JSON response | Falls back to raw output with status "partial" | Test |
| Morning report generation | Grouped by round, color-coded, action items listed | Inspection |
| Config file override | TOML values override defaults; CLI overrides TOML | Test |
| Compaction recovery | Round state loaded from JSON, resume from last task | Test |

---

## Design

### Architecture

```
┌──────────────────────────────────────────────────────┐
│                    OVERNIGHT                          │
│    Scheduler: phases, modes, morning report           │
│                                                       │
│  ┌─────────────────────────────────────────────────┐ │
│  │                  RUNNER                          │ │
│  │    Sequential: pre-gates → tasks → post-gates   │ │
│  │                                                  │ │
│  │  ┌───────────────────────────────────────────┐  │ │
│  │  │              PARALLEL                      │  │ │
│  │  │    ThreadPoolExecutor + throttle           │  │ │
│  │  │                                            │  │ │
│  │  │  ┌──────────────────────────────────────┐ │  │ │
│  │  │  │           DISPATCH                    │ │  │ │
│  │  │  │    claude -p + env + auth + model     │ │  │ │
│  │  │  └──────────────────────────────────────┘ │  │ │
│  │  └───────────────────────────────────────────┘  │ │
│  └─────────────────────────────────────────────────┘ │
│                                                       │
│  ┌─────────────────────────────────────────────────┐ │
│  │                  ENGINE                          │ │
│  │    Round, Task, Gate — data model + state        │ │
│  └─────────────────────────────────────────────────┘ │
│                                                       │
│  ┌─────────────────────────────────────────────────┐ │
│  │                  REPORT                          │ │
│  │    Aggregation, morning report, color-coding     │ │
│  └─────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────┘
```

### Layer Responsibilities

| Layer | Module | Responsibility | Depends On |
|-------|--------|---------------|------------|
| L0 | `engine` | Data model: Round, Task, Gate, enums, serialization | Nothing |
| L1 | `dispatch` | Subprocess invocation, env management, result capture | engine |
| L2 | `runner` | Sequential round execution: gates → tasks → summary | engine, dispatch |
| L2 | `parallel` | Concurrent dispatch with throttle and conflict detection | engine, dispatch |
| L3 | `overnight` | Phased batch scheduling, mode selection | runner, parallel |
| L3 | `report` | Result aggregation, morning report generation | engine |

### Three-Field Contract

Every interactive task is defined by exactly three fields:

```
Read:  [files to read first — context]
Do:    [what Claude should do — instruction]
Done:  [how to know it's complete — criteria]
```

This contract is the API between Python (the conductor) and Claude (the orchestra). The prompt template wraps these three fields with output format instructions.

### Auth Switching

```
                  ┌─────────────────┐
                  │   --auth flag    │
                  └────────┬────────┘
                           │
              ┌────────────┴────────────┐
              │                         │
         auth=max                  auth=api
              │                         │
    Strip ANTHROPIC_API_KEY    Keep ANTHROPIC_API_KEY
    Strip CLAUDECODE           Strip CLAUDECODE
              │                         │
    Uses subscription          Uses API credits
    ($0 extra cost)            (pay-per-token)
```

### Model Routing (COALESCE)

```python
effective_model = cli_override or task.model or "sonnet"
```

Round definitions tag each task with a recommended model:
- **opus** — judgment tasks (requirement quality, architecture impact, health scoring)
- **sonnet** — pattern tasks (section checks, cross-refs, code review)
- **haiku** — simple tasks (comment style, naming conventions)

### Task Result Contract

Claude returns:
```json
{
  "status": "done|blocked",
  "confidence": 0.0-1.0,
  "result": "what was accomplished",
  "question": "if blocked, what is needed"
}
```

Rondo captures:
```json
{
  "task_name": "...",
  "status": "done|blocked|error",
  "model": "opus|sonnet|haiku",
  "auth": "max|api",
  "duration_sec": 42.3,
  "confidence": 0.85,
  "result": "...",
  "raw_output": "...",
  "prompt": "...",
  "timestamp": "2026-03-13T22:00:00Z"
}
```

---

## States & Modes

### Task States

| State | Description | Transitions To |
|-------|-------------|---------------|
| pending | Not yet started | running |
| running | Subprocess active | passed, failed |
| passed | Completed successfully | (terminal) |
| failed | Error or bad result | (terminal) |
| skipped | Deliberately skipped | (terminal) |

### Overnight Modes

| Mode | Phases | Use Case |
|------|--------|----------|
| quick | spec-health only | Fast check, low cost |
| default | health + convention + digest | Normal nightly run |
| full | all 5 phases | Weekend deep analysis |

---

## Rules & Constraints

| Rule | Rationale |
|------|-----------|
| Python is conductor, Claude is orchestra | Python manages state, scheduling, error handling. Claude does the thinking. |
| Three-field contract is mandatory | Do, Read, Done — every task must have all three. Prevents vague instructions. |
| No nested Claude sessions | `CLAUDECODE` env var must be stripped. Claude Code blocks re-entry otherwise. |
| Results always saved to disk | Even on error. Overnight runs can't rely on memory. |
| Phases don't block each other | One failed phase must not prevent other phases from running. |
| Sequential is the safe default | Parallel requires explicit opt-in (--workers > 1). |
| Config file is optional | Rondo works with zero config. Defaults are sane. |

---

## Quality Attributes

| Attribute | Target | How Measured |
|-----------|--------|-------------|
| Reliability | 95%+ overnight runs complete without manual intervention | Track overnight_end events vs overnight_start |
| Transparency | Every task result traceable to its prompt + output | JSON result files with full prompt capture |
| Resilience | Single task failure never crashes the framework | Exception handling around every dispatch |
| Performance | 4x speedup from parallel (4 workers vs sequential) | Speedup ratio in parallel summary |
| Simplicity | New round definition in <50 lines | Measure new round file sizes |

---

## Foundations Applied

| F | How Applied |
|---|-------------|
| F01 Time | All timestamps UTC ISO 8601. `datetime.now(UTC)` throughout. |
| F03 Logging | Structured output: task name, status, duration in every log line. |
| F04 Error | Every failure includes: task name, error message, duration, prompt sent. Subprocess errors distinguished from logic errors. |
| F05 Config | TOML config file. COALESCE resolution: CLI → config → default. |
| F06 Paths | `pathlib.Path` for all file operations. No string concatenation for paths. |
| F07 Encoding | `encoding="utf-8"` on every file read/write. |
| F09 Naming | snake_case functions/variables. PascalCase for Round/Task/Gate classes. |
| F11 Status | Standard state machine: pending → running → passed/failed/skipped. |
| F13 Health | Overnight log tracks start/end events. Morning report flags failures. |
| F14 Abstraction | Dispatch layer is swappable — interface defined, implementation behind it. Future: Ollama backend, API-direct backend. |
| F18 Concurrency | ThreadPoolExecutor for I/O-bound dispatch. Throttle between launches. Conflict detection for parallel writes. |
| F22 Build/Test | `rondo/tests/` with pytest. Must pass `ace-build full` gates. |
| F23 Security | No command injection (subprocess with list args, never shell=True). API keys stripped from results/logs. Never log ANTHROPIC_API_KEY. |
| F24 Performance | Duration tracked per task. Speedup ratio reported for parallel. |
| F27 Contracts | Three-field contract (Do/Read/Done) is the API. Result JSON schema is the response contract. |

---

## Integration Points

| System | Relationship |
|--------|-------------|
| Claude Code CLI | `claude -p` is the execution backend — Rondo's only external dependency |
| ACE2 specs | Round definitions read spec files as context (read-only) |
| OB database | Round definitions may query OB data for gate checks (read-only) |
| Cron / LaunchAgent | Overnight scheduler invoked by system scheduler |
| Morning report | Human reads report at start of day |

---

## Dependencies

| Depends On | Why |
|------------|-----|
| Claude Code CLI (`claude -p`) | The execution backend — cannot function without it |
| Python 3.12+ | `concurrent.futures`, `pathlib`, `tomllib` (stdlib) |
| No external packages | Zero pip dependencies — stdlib only |

---

## Decisions

| # | Decision | Date | Why |
|---|----------|------|-----|
| D1 | Python over shell for orchestration | 2026-03-13 | Shell can't manage concurrent processes, parse JSON, or implement gate logic |
| D2 | ThreadPoolExecutor over ProcessPool | 2026-03-13 | Dispatch is I/O-bound (waiting on subprocess). Threads are simpler and sufficient |
| D3 | Dual auth (max vs api) via env stripping | 2026-03-13 | Max plan = free overnight capacity. API = overflow/CI. Same code path, different env |
| D4 | COALESCE for model routing | 2026-03-13 | CLI → task hint → default. Round authors describe intent; operators override when needed |
| D5 | Three-field contract (Do/Read/Done) | 2026-03-13 | Prevents vague tasks. Every task is self-describing. Prompt template wraps all three |
| D6 | Results always saved to JSON files | 2026-03-13 | Overnight runs can't rely on terminal output or memory. Files survive everything |
| D7 | Rondo is its own product (not an OB feature) | 2026-03-13 | Framework serves ACE, OB, and potentially any Claude Code user. Own specs, src, tests |
| D8 | Zero external dependencies | 2026-03-13 | stdlib only (subprocess, concurrent.futures, json, tomllib, pathlib). Maximizes portability |
| D9 | Sequential is the safe default | 2026-03-13 | Parallel requires explicit --workers flag. Prevents accidental rate limiting or conflicts |
| D10 | Phases don't block each other | 2026-03-13 | Overnight resilience: one failed phase must not prevent others from running |

---

## Open Questions

| # | Question | Status |
|---|----------|--------|
| Q1 | Should Rondo have its own lightweight DB (task history, run history)? | Open |
| Q2 | What's the rate limit on Max plan `claude -p` invocations? | Open — needs empirical testing |
| Q3 | Should Rondo support `--resume` (restart overnight from failed phase)? | Open |
| Q4 | LaunchAgent vs cron vs systemd for scheduling? | Open — platform-dependent |
| Q5 | Should round definitions live in config (TOML) or code (Python)? | Answered: Code — they need logic (dynamic file discovery, git diff) |
| Q6 | Should Rondo eventually support Ollama as an alternative backend? | Deferred — RONDO-03 when needed |
| Q7 | What is the right boundary between Rondo and OB? Rondo dispatches, OB tracks? | Open |

---

## Glossary

| Term | Definition |
|------|-----------|
| **Round** | A collection of tasks with pre/post gates. The unit of work. |
| **Task** | A single unit of AI work: either automated (Python) or interactive (Claude). |
| **Gate** | A boolean check that guards round entry (pre) or exit (post). |
| **Three-field contract** | Do (instruction), Read (context files), Done (completion criteria). |
| **Dispatch** | The act of invoking `claude -p` with a task prompt. |
| **Capacity mining** | Using idle Max plan capacity for automated overnight AI work at $0 cost. |
| **Morning report** | Aggregated summary of overnight results, ready at start of day. |
| **COALESCE** | Resolution pattern: first non-null wins. CLI → config → task → default. |
| **Conductor** | Python — manages scheduling, state, errors. |
| **Orchestra** | Claude — does the actual thinking work. |

---

## Risk / Criticality

| Req # | Criticality | Failure Consequence |
|-------|-------------|-------------------|
| R11 (CLAUDECODE strip) | HIGH | All dispatch fails — complete blocker |
| R12-13 (auth switching) | HIGH | Wrong billing — charges API when should use subscription |
| R18 (error handling) | HIGH | Silent failures — overnight appears to work but produces nothing |
| R29 (phase isolation) | MEDIUM | One bad phase kills entire overnight run |
| R24 (conflict detection) | MEDIUM | Parallel tasks corrupt each other's output |
| R41 (timeout) | MEDIUM | Hung subprocess blocks worker forever |

---

## Change History

| Version | Date | What Changed |
|---------|------|-------------|
| 0.1 | 2026-03-13 | Initial draft — full spec from spike learnings (Session 75) |
