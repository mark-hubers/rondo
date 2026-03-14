# REQ-001: Core — Engine + Dispatch

*Define AI tasks in Python, send them to Claude, get structured results back.*

**Created:** 2026-03-13 | **Status:** DRAFT
**Depends on:** Claude Code CLI (`claude -p`) | **Blocks:** REQ-002 (Automation)
**Author:** Mark Hubers — HubersTech

---

## Item 1: Purpose & Scope

**What this spec does (plain English):**
Defines Rondo's core: the data model for describing AI work (Rounds, Tasks, Gates) and the dispatch layer that sends tasks to Claude Code via `claude -p`. This is the minimum viable Rondo — everything else builds on it.

**IN scope:**
- Engine: Round, Task, Gate data model and state machine
- Three-field contract: Do, Read, Done
- Dispatch: `claude -p` subprocess orchestration
- Auth switching: Max plan vs API key
- Model routing: opus/sonnet/haiku per task
- Result capture: structured JSON from Claude
- Dry-run mode
- Round state serialization (JSON, for recovery)

**OUT of scope:**
- Parallel execution (REQ-002: Automation)
- Overnight scheduling (REQ-002: Automation)
- Morning reports (REQ-002: Automation)
- Specific round definitions (consumer's responsibility — e.g., OB defines its own rounds)
- Claude Code internals (Anthropic's product)
- Alternative AI backends (future work)

---

## The Problem

AI work can be decomposed into tasks with clear inputs, instructions, and completion criteria. Today, that work is done manually — a human types prompts, reads output, decides what's next. This doesn't scale.

**What's needed:** A way to define AI tasks in Python, group them into rounds with guardrails, dispatch them to Claude Code programmatically, and collect structured results. The human defines the work. Python orchestrates it. Claude executes it.

**Why Python, not shell:**
- Shell can't implement gate logic (pre-conditions that block a round)
- Shell can't parse structured JSON results
- Shell can't manage task state machines
- Python's `subprocess`, `json`, and `dataclasses` are purpose-built for this

**The core insight:** Python is the conductor. Claude is the orchestra.

---

## Requirements

### Engine — Data Model

1. A **Round** MUST contain: a name, zero or more pre-gates, one or more tasks, zero or more post-gates.
2. A **Task** MUST have: a name, a mode (auto or interactive), and a status.
3. An **interactive task** MUST have three fields: instruction (Do), context_files (Read), done_when (Done). This is the **three-field contract**.
4. An **auto task** MUST have: a Python callable that returns `(passed: bool, detail: str)`.
5. A **Gate** MUST have: a name, a check function, and a blocking flag. Blocking gates halt the round on failure.
6. Pre-gates MUST run before any task dispatch. If a blocking pre-gate fails, no tasks run.
7. Post-gates MUST run only after all tasks complete.

### Engine — State Machine

8. Task status MUST follow this state machine: `pending → running → passed | failed | skipped`. No other transitions.
9. A round is "complete" when all tasks are in a terminal state (passed, failed, or skipped).
10. Round state (task statuses, gate results) MUST be serializable to JSON for recovery after interruption.
11. A round MUST be resumable from serialized state — load JSON, skip completed tasks, continue from next pending.

### Dispatch — Subprocess

12. Dispatch MUST invoke `claude -p` as a subprocess with the task's three-field contract formatted as the prompt.
13. Dispatch MUST strip the `CLAUDECODE` environment variable from child processes to prevent the nested-session guard.
14. Dispatch MUST capture stdout, stderr, exit code, and wall-clock duration from each subprocess.
15. Dispatch MUST save each task result to a JSON file in a configurable results directory.
16. Dispatch MUST support dry-run mode: show the prompt without invoking Claude.

### Dispatch — Auth

17. When auth is "max", dispatch MUST strip `ANTHROPIC_API_KEY` from the child environment so Claude uses the subscription plan.
18. When auth is "api", dispatch MUST preserve `ANTHROPIC_API_KEY` in the child environment for pay-per-token billing.
19. Auth mode MUST be selectable via CLI flag (`--auth max|api`). Default: max.

### Dispatch — Model Routing

20. Dispatch MUST pass `--model` to the subprocess to select opus, sonnet, or haiku.
21. Model selection MUST follow the COALESCE pattern: CLI override → task.model hint → default.
22. Default model MUST be sonnet (best balance of cost and capability).
23. Round definitions MUST be able to tag each task with a recommended model.

### Dispatch — Result Contract

24. The prompt MUST instruct Claude to return structured JSON: `{status, confidence, result, question}`.
25. If Claude returns valid JSON matching the contract, dispatch MUST parse and store it.
26. If Claude returns malformed or missing JSON, dispatch MUST fall back to raw output with status "partial".
27. If the subprocess returns exit code != 0 or empty stdout, dispatch MUST record status "error" with stderr content.
28. Every result (success or failure) MUST include: task name, status, model used, auth mode, duration, timestamp.

### Round Definitions — The Pattern

29. A round definition MUST be a Python function that returns a `Round` object.
30. Round definitions MUST be self-contained: all tasks, gates, and metadata in one function call.
31. Round definitions MAY accept parameters (e.g., a file path, a spec ID) to customize their tasks.
32. Round definitions MUST NOT import Rondo internals beyond the engine module (Round, Task, Gate).
33. A new round definition SHOULD be writable in under 50 lines of Python.

---

## Assumptions

| # | Assumption | If Wrong |
|---|-----------|----------|
| A1 | `claude -p` accepts arbitrary text prompts and returns text to stdout | Rondo cannot function — hard dependency |
| A2 | `CLAUDECODE` env var is the nested-session guard | Other guards may block dispatch — test each Claude version |
| A3 | Stripping `ANTHROPIC_API_KEY` causes Claude to use subscription auth | May need explicit flag — test empirically |
| A4 | Claude reliably returns structured JSON when instructed | If unreliable, parsing fallback must handle diverse output formats |
| A5 | `claude -p` is available on the system PATH | May need configurable binary path |
| A6 | Python 3.12+ is available (for `tomllib` in stdlib) | Could fall back to `tomli` package for 3.11 |

---

## Success Criteria

| Scenario | Expected Result | Verification |
|----------|----------------|--------------|
| Define a round with 3 tasks and 1 gate | Round object created with correct structure | Test |
| Dispatch single task (auth=max) | Claude runs, JSON result saved to disk | Test |
| Dispatch single task (auth=api) | Uses API key, result saved | Test |
| Model routing: opus task | `--model opus` passed to subprocess | Test |
| Model routing: CLI override | CLI flag overrides task hint | Test |
| Dry-run mode | Prompt displayed, no subprocess launched | Test |
| Blocking pre-gate fails | Round halts, no tasks dispatched | Test |
| Non-blocking pre-gate fails | Warning logged, tasks proceed | Test |
| Subprocess exit code 1 | Error recorded with stderr, round continues | Test |
| Malformed JSON response | Raw output stored, status "partial" | Test |
| Serialize round state to JSON | All task statuses and gate results preserved | Test |
| Resume round from JSON | Completed tasks skipped, next pending task dispatched | Test |
| New round definition | Written in <50 lines, accepted by runner | Demonstration |

---

## Design

### Architecture

```
┌────────────────────────────────────────────────────┐
│                     REQ-001: CORE                       │
│                                                     │
│  ┌──────────────────────────────────────────────┐  │
│  │              ENGINE (L0)                      │  │
│  │   Round ─── Task ─── Gate                     │  │
│  │   State machine, serialization, enums         │  │
│  └──────────────────────────────────────────────┘  │
│                        │                            │
│  ┌──────────────────────────────────────────────┐  │
│  │             DISPATCH (L1)                     │  │
│  │   claude -p subprocess                        │  │
│  │   Auth switching, model routing               │  │
│  │   Result capture, JSON parsing                │  │
│  └──────────────────────────────────────────────┘  │
│                        │                            │
│  ┌──────────────────────────────────────────────┐  │
│  │              RUNNER (L2)                      │  │
│  │   Sequential: pre-gates → tasks → post-gates  │  │
│  │   Result collection, summary                  │  │
│  └──────────────────────────────────────────────┘  │
│                                                     │
│         ▲ REQ-002 builds on top of this ▲               │
└────────────────────────────────────────────────────┘
```

### Three-Field Contract

Every interactive task is defined by exactly three fields:

```
Read:  [files to read first — gives Claude context]
Do:    [what Claude should do — the instruction]
Done:  [how to know it's complete — success criteria]
```

This is the API between Python and Claude. The prompt template wraps these three fields with output format instructions. Anyone writing a round definition only needs to fill in these three fields per task.

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
   Strip ANTHROPIC_API_KEY   Keep ANTHROPIC_API_KEY
   Strip CLAUDECODE          Strip CLAUDECODE
         │                         │
   Uses subscription         Uses API credits
   ($0 marginal cost)        (pay-per-token)
```

### Model Routing (COALESCE)

```
effective_model = cli_flag  or  task.model  or  config.default_model  or  "sonnet"
                  ────────      ──────────      ──────────────────      ─────────
                  operator      round author    project config          hardcoded
```

### Task Result Contract

Claude returns:
```json
{"status": "done|blocked", "confidence": 0.0-1.0,
 "result": "what was accomplished", "question": "if blocked, what is needed"}
```

Rondo wraps that with execution metadata:
```json
{"task_name": "...", "status": "done|blocked|error",
 "model": "opus|sonnet|haiku", "auth": "max|api",
 "duration_sec": 42.3, "confidence": 0.85,
 "result": "...", "raw_output": "...", "prompt": "...",
 "timestamp": "2026-03-13T22:00:00Z"}
```

### Round Definition Example

```python
from rondo.engine import Round, Task, Gate

def build_my_round(target_file: str) -> Round:
    return Round(
        name="my-check",
        pre_gates=[
            Gate("File exists", check_fn=lambda **kw: (Path(target_file).exists(), "Found")),
        ],
        tasks=[
            Task(
                name="Analyze file",
                instruction=f"Read {target_file} and list all public functions.",
                context_files=[target_file],
                done_when="List of public functions with line numbers",
                model="sonnet",
            ),
        ],
    )
```

---

## States & Modes

### Task State Machine

```
pending ──→ running ──→ passed   (terminal)
                   ├──→ failed   (terminal)
                   └──→ skipped  (terminal)
```

No backward transitions. No re-running. A failed task stays failed for this round.

---

## Rules & Constraints

| Rule | Rationale |
|------|-----------|
| Python is conductor, Claude is orchestra | Python manages state and scheduling. Claude does the thinking. Never mix roles. |
| Three-field contract is mandatory | Do, Read, Done. Every interactive task needs all three. Prevents vague instructions. |
| CLAUDECODE env var always stripped | Claude Code blocks nested sessions. This is non-negotiable. |
| Results always saved to disk | Even on error. Can't rely on terminal output or memory. |
| Sequential is the safe default | Parallel is opt-in (REQ-002). One task at a time is predictable. |
| Zero external dependencies | stdlib only. Maximizes portability and ease of installation. |
| Round definitions import only engine | Keeps definitions portable. They shouldn't know about dispatch internals. |

---

## Quality Attributes

| Attribute | Target | How Measured |
|-----------|--------|-------------|
| Simplicity | New round definition in <50 lines | Measure file sizes |
| Transparency | Every result traceable to its prompt | JSON files with full prompt capture |
| Resilience | Task failure never crashes framework | Exception handling around every dispatch |
| Portability | Works on any system with Python 3.12 + Claude Code | Zero pip dependencies |

---

## Data Boundary: Rondo Produces, Consumer Stores

**Rondo has no database.** It is a dispatch framework, not a data store.
Rondo produces structured output (JSON files, return objects). The consumer
(OB, ACE, or any project) decides what to persist.

### What Rondo Returns

Every round execution returns a `RoundResult` to the caller:

```python
@dataclass
class RoundResult:
    """Everything a consumer needs to know about a round execution."""

    # -- identity
    round_name: str                        # -- which round ran
    started_at: str                        # -- ISO-8601 UTC
    completed_at: str                      # -- ISO-8601 UTC
    duration_sec: float                    # -- wall-clock total

    # -- task results (one per task)
    task_results: list[TaskResult]         # -- see STD-001 for TaskResult fields

    # -- gate results
    pre_gate_results: list[GateResult]     # -- name, passed, detail
    post_gate_results: list[GateResult]

    # -- parallel execution info (if applicable)
    conflicts: list[str]                   # -- files touched by 2+ tasks
    parallelism: int                       # -- workers used (1 = sequential)

    # -- usage metadata (from stream-json, per dispatch)
    usage: list[DispatchUsage]             # -- one per task dispatch

    # -- overall
    status: str                            # -- "passed", "failed", "partial"
    summary: str                           # -- one-line human summary
```

### Usage Metadata Per Dispatch

```python
@dataclass
class DispatchUsage:
    """Stream-json metadata captured from each claude -p call."""

    task_name: str
    model: str                             # -- claude-sonnet-4-6, etc.
    cost_usd: float                        # -- total_cost_usd from result event
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_create_tokens: int
    duration_ms: int                       # -- wall-clock
    duration_api_ms: int                   # -- API time only
    num_turns: int                         # -- tool-use loops
    context_window: int                    # -- 200000 or 1000000
    rate_limit_status: str                 # -- "allowed" or "blocked"
    is_using_overage: bool                 # -- past plan allocation?
    rate_limit_resets_at: int              # -- epoch timestamp
```

### How OB/ACE Gets Total Visibility

The consumer calls Rondo and receives `RoundResult`. From that single object:

| Consumer Wants | Where In RoundResult |
|---------------|---------------------|
| What tasks ran | `task_results[*].task_name` |
| What passed/failed | `task_results[*].status` (done/blocked/partial/error/skipped) |
| What each task returned | `task_results[*].parsed_result` (the AI's JSON response) |
| What errors happened | `task_results[*].error_code` + `error_message` |
| Full AI output | `task_results[*].raw_output` |
| What prompt was sent | `task_results[*].prompt_sent` |
| How long each task took | `task_results[*].duration_sec` |
| How much it cost | `usage[*].cost_usd` (per task) |
| Token breakdown | `usage[*].input_tokens`, `output_tokens`, cache fields |
| Rate limit status | `usage[*].rate_limit_status`, `is_using_overage` |
| File conflicts | `conflicts` list |
| Gate results | `pre_gate_results`, `post_gate_results` |
| Overall pass/fail | `status` |
| Wall-clock total | `duration_sec` |

**The consumer stores whatever they want.** OB might write everything to
`sprint_results` and `round_states`. ACE might feed it to the knowledge engine.
A simple script might just print the summary. Rondo doesn't care — it returns
the data and moves on.

### Result Files (Backup)

In addition to the return object, Rondo writes each task result to a JSON file
in `results_dir` (STD-002). These files are a backup — the consumer should use
the return object as the primary data source. Result files persist across crashes
and let consumers replay results without re-dispatching.

```
reports/rondo-results/
├── 2026-03-14T03-00-00Z/              # -- one dir per round execution
│   ├── round-summary.json             # -- RoundResult as JSON
│   ├── task-01-spec-health.json       # -- TaskResult + DispatchUsage
│   ├── task-02-digest-refresh.json
│   └── task-03-convention-check.json
```

---

## Foundations Applied

| Standard | How Applied |
|----------|-------------|
| STD-001 Error & Resilience | Every failure includes task name, error, duration, prompt. Subprocess errors vs logic errors distinguished. |
| STD-002 Configuration | TOML config. COALESCE: CLI → config → default. Zero-config works out of the box. |
| STD-003 Concurrency & Safety | (REQ-001 is sequential only. STD-003 applied fully in REQ-002.) Subprocess args as list, never shell=True. API keys stripped from result files. |

---

## Dependencies

| Depends On | Why |
|------------|-----|
| Claude Code CLI (`claude -p`) | Execution backend — the one external dependency |
| Python 3.12+ | `tomllib`, `dataclasses`, `subprocess`, `json`, `pathlib` (all stdlib) |
| No pip packages | Zero external dependencies |

---

## Decisions

| # | Decision | Date | Why |
|---|----------|------|-----|
| D1 | Python over shell | 2026-03-13 | Shell can't manage state machines, parse JSON, or implement gate logic |
| D2 | Three-field contract (Do/Read/Done) | 2026-03-13 | Self-describing tasks. Prevents vague prompts. The API between conductor and orchestra |
| D3 | Dual auth via env stripping | 2026-03-13 | Subscription = free capacity. API = pay-per-token. Same code, different env |
| D4 | COALESCE for model routing | 2026-03-13 | Round authors describe intent. Operators override. Config sets project default |
| D5 | Results always to JSON files | 2026-03-13 | Files survive crashes, restarts, compaction. Terminal output doesn't |
| D6 | Zero external dependencies | 2026-03-13 | stdlib only. Anyone with Python + Claude Code can use Rondo |
| D7 | Rondo is its own product | 2026-03-13 | Not an OB feature. Not an ACE feature. A standalone framework |
| D8 | Sequential default | 2026-03-13 | Parallel is REQ-002's concern. REQ-001 is simple and predictable |

---

## Open Questions

| # | Question | Status |
|---|----------|--------|
| Q1 | Should Rondo have its own lightweight DB for run history? | **Answered: No.** Rondo produces structured output (RoundResult). Consumer stores it. See "Data Boundary" section. |
| Q2 | What's the rate limit on Max plan `claude -p`? | **Partially answered.** rate_limit_event gives 5-hour window status. Weekly % not available programmatically. (Spike: Session 76) |
| Q3 | Should the binary path for `claude` be configurable? | **Answered: Yes.** `claude_binary` in STD-002 config. Default: "claude" |
| Q4 | Should round definitions live in TOML or Python? | **Answered: Python** — they need logic |
| Q5 | Should Rondo support alternative backends (Ollama, API-direct)? | Deferred |

---

## Glossary

| Term | Definition |
|------|-----------|
| **Round** | A collection of tasks with pre/post gates. The unit of work. |
| **Task** | A single unit of AI work: automated (Python) or interactive (Claude). |
| **Gate** | A boolean check that guards round entry or exit. |
| **Three-field contract** | Do (instruction), Read (context), Done (criteria). The task API. |
| **Dispatch** | Invoking `claude -p` with a task prompt as a subprocess. |
| **Conductor** | Python — manages scheduling, state, errors. |
| **Orchestra** | Claude — does the thinking work. |
| **COALESCE** | First non-null wins: CLI → config → task → default. |
| **Capacity mining** | Using idle subscription capacity for automated AI work at $0 extra cost. |

---

## Risk / Criticality

| Req # | Criticality | Failure Consequence |
|-------|-------------|-------------------|
| 13 (CLAUDECODE strip) | HIGH | All dispatch fails — complete blocker |
| 17-18 (auth) | HIGH | Wrong billing — charges API when should use subscription |
| 27 (error on bad exit) | HIGH | Silent failures — tasks appear to run but produce nothing |
| 10 (serialization) | MEDIUM | Can't recover after crash or compaction |
| 26 (malformed JSON) | MEDIUM | Good results discarded because parsing fails |

---

## Change History

| Version | Date | What Changed |
|---------|------|-------------|
| 0.1 | 2026-03-13 | Initial draft from spike learnings (Session 75) |
| 0.2 | 2026-03-13 | Split from monolithic spec. REQ-001=core, REQ-002=automation. Removed OB/ACE references. Own foundations. |
| 0.3 | 2026-03-14 | Added Data Boundary section: RoundResult, DispatchUsage, result file structure. Answered Q1 (no DB), Q2 (rate_limit_event), Q3 (configurable binary). |
