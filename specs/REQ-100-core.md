# REQ-100: Core — Engine + Dispatch

*Define AI tasks in Python, send them to Claude, get structured results back.*

**Created:** 2026-03-13 | **Status:** DRAFT
**Classification:** open
**Version:** 0.8
**Owner:** Mark G. Hubers
**Reviewed:** not-yet
**Supersedes:** none
**Depends on:** Claude Code CLI (`claude -p`) | **Blocks:** REQ-101 (Automation)
**Author:** Mark Hubers — HubersTech

---

## 1. Purpose & Scope

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
- Parallel execution (REQ-101: Automation)
- Overnight scheduling (REQ-101: Automation)
- Morning reports (REQ-101: Automation)
- Specific round definitions (consumer's responsibility — e.g., OB defines its own rounds)
- Claude Code internals (Anthropic's product)
- Alternative AI backends (future work)

**Users:** Mark (primary). Claude AI agents dispatching to other models. Future: teams needing multi-model AI orchestration, batch processing, cost optimization across AI providers.

---

## 2. The Problem

AI work can be decomposed into tasks with clear inputs, instructions, and completion criteria. Today, that work is done manually — a human types prompts, reads output, decides what's next. This doesn't scale.

**What's needed:** A way to define AI tasks in Python, group them into rounds with guardrails, dispatch them to Claude Code programmatically, and collect structured results. The human defines the work. Python orchestrates it. Claude executes it.

**Why Python, not shell:**
- Shell can't implement gate logic (pre-conditions that block a round)
- Shell can't parse structured JSON results
- Shell can't manage task state machines
- Python's `subprocess`, `json`, and `dataclasses` are purpose-built for this

**The core insight:** Python is the conductor. Claude is the orchestra.

---

## 3. Requirements

*All requirements use MUST/SHOULD priority per CORE-STD-012.*

### Engine — Data Model
| ID | Requirement | Priority |
|----|-------------|----------|
| 001 | A **Round** MUST contain: a name, zero or more pre-gates, one or more tasks, zero or more post-gates | MUST |
| 002 | A **Task** MUST have: a name, a mode (auto or interactive), a status, and an optional description and model hint | MUST |
| 003 | An **interactive task** MUST have three fields: instruction (Do), context_files (Read), done_when (Done). This is the **three-field contract** | MUST |
| 004 | An **auto task** MUST have: a Python callable that returns `(passed: bool, detail: str)` | MUST |
| 005 | A **Gate** MUST have: a name, a check function, and a blocking flag. Blocking gates halt the round on failure | MUST |
| 006 | Pre-gates MUST run before any task dispatch. If a blocking pre-gate fails, no tasks run | MUST |
| 007 | Post-gates MUST run only after all tasks complete | MUST |

### Engine — State Machine
| ID | Requirement | Priority |
|----|-------------|----------|
| 008 | Task status MUST follow this state machine: `pending → running → done | blocked | partial | error | skipped`. No other transitions. See "Task State Machine" below and STD-108 for definitions | MUST |
| 009 | System SHALL a round is "complete" when all tasks are in a terminal state (done, blocked, partial, error, or skipped) | MUST |
| 010 | Round state (task statuses, gate results) MUST be serializable to JSON for recovery after interruption | MUST |
| 011 | A round MUST be resumable from serialized state — load JSON, skip completed tasks, continue from next pending | MUST |

### Dispatch — Subprocess
| ID | Requirement | Priority |
|----|-------------|----------|
| 012 | Dispatch MUST invoke `claude -p` as a subprocess with the task's three-field contract formatted as the prompt | MUST |
| 013 | Dispatch MUST strip the `CLAUDECODE` environment variable from child processes to prevent the nested-session guard | MUST |
| 014 | Dispatch MUST capture stdout, stderr, exit code, and wall-clock duration from each subprocess | MUST |
| 015 | Dispatch MUST use `--output-format stream-json` to capture real token counts, cost, cache stats, and API timing per call. Text mode cannot capture these. (ACE-STD-020 — Session 78: estimated costs were inaccurate without stream-json.) | MUST |
| 016 | System SHALL from stream-json, dispatch extracts: input_tokens, output_tokens, cache_read_tokens, cache_create_tokens, cost_usd, duration_ms (API), num_turns. These populate DispatchUsage | MUST |
| 017 | Dispatch MUST save each task result to a JSON file in a configurable results directory | MUST |
| 018 | Dispatch MUST support dry-run mode: show the prompt without invoking Claude | MUST |

### Dispatch — Auth
| ID | Requirement | Priority |
|----|-------------|----------|
| 019 | When auth is "max", dispatch MUST strip `ANTHROPIC_API_KEY` from the child environment so Claude uses the subscription plan | MUST |
| 020 | When auth is "api", dispatch MUST preserve `ANTHROPIC_API_KEY` in the child environment for pay-per-token billing | MUST |
| 021 | Auth mode MUST be selectable via CLI flag (`--auth max|api`). Default: max | MUST |

### Dispatch — Tool Control (Session 78 — NEW)
| ID | Requirement | Priority |
|----|-------------|----------|
| 022 | For code generation tasks (output to stdout): dispatch MUST pass `--tools ""` to disable file tools. Without this, Claude tries to write files and hangs on permission prompts | MUST |
| 023 | For code fixing tasks (needs file access in sandbox): dispatch MUST pass `--dangerously-skip-permissions` (only in containers with no internet) | MUST |
| 024 | Task definition MUST include `tool_mode: "none" | "sandbox" | "default"` to control which flag is used | MUST |

### Dispatch — Model Routing
| ID | Requirement | Priority |
|----|-------------|----------|
| 025 | Dispatch MUST pass `--model` to the subprocess to select opus, sonnet, or haiku | MUST |
| 026 | Model selection MUST follow the COALESCE pattern: CLI override → task.model hint → default | MUST |
| 027 | Default model MUST be sonnet (best balance of cost and capability) | MUST |
| 028 | Round definitions MUST be able to tag each task with a recommended model | MUST |

### Dispatch — Result Contract
| ID | Requirement | Priority |
|----|-------------|----------|
| 029 | The prompt MUST instruct Claude to return structured JSON: `{status, confidence, result, question}` | MUST |
| 030 | If Claude returns valid JSON matching the contract, dispatch MUST parse and store it | MUST |
| 031 | If Claude returns malformed or missing JSON, dispatch MUST fall back to raw output with status "partial" | MUST |
| 032 | If the subprocess returns exit code != 0 or empty stdout, dispatch MUST record status "error" with stderr content | MUST |
| 033 | Every result (success or failure) MUST include: task name, status, model used, auth mode, duration, timestamp | MUST |

### Round Definitions — The Pattern
| ID | Requirement | Priority |
|----|-------------|----------|
| 034 | A round definition MUST be a Python function that returns a `Round` object | MUST |
| 035 | Round definitions MUST be self-contained: all tasks, gates, and metadata in one function call | MUST |
| 036 | System SHALL round definitions MAY accept parameters (e.g., a file path, a spec ID) to customize their tasks | SHOULD |
| 037 | Round definitions MUST NOT import Rondo internals beyond the engine module (Round, Task, Gate) | MUST |
| 038 | A new round definition SHOULD be writable in under 50 lines of Python | SHOULD |

### Package Structure & Public API
| ID | Requirement | Priority |
|----|-------------|----------|
| 039 | Rondo MUST be an importable Python package: `from rondo import run_round, RoundResult` | MUST |
| 040 | The public API (`rondo/__init__.py`) MUST export: `Round`, `Task`, `Gate`, `GateResult`, `TaskResult`, `RoundResult`, `DispatchUsage`, `RondoConfig`, `run_round` | MUST |
| 041 | Rondo MUST provide a CLI entry point: `rondo <subcommand> [options]` | MUST |
| 042 | CLI subcommands MUST include: `run` (execute a round), `overnight` (batch scheduler), `report` (generate morning report). Dry-run is a `--dry-run` flag on `run`, not a separate subcommand (STD-109) | MUST |
| 043 | The `run` subcommand MUST accept a path to a Python file containing a `build_round()` function that returns a `Round` object | MUST |
| 044 | Round definition files MUST be loadable by path — Rondo dynamically imports the file and calls `build_round()` | MUST |
| 045 | Rondo MUST auto-detect sequential vs parallel: `workers == 1` uses `runner.py`, `workers > 1` uses `parallel.py` | MUST |
| 046 | All CLI flags from STD-109 (--workers, --model, --auth, etc.) MUST be available on the `run` subcommand | MUST |

### Dispatch — Permission Mode
| ID | Requirement | Priority |
|----|-------------|----------|
| 047 | Dispatch MUST pass `--permission-mode` to the subprocess from the config's `permission_mode` field | MUST |
| 048 | Permission mode MUST follow the COALESCE pattern: CLI flag → config file → default `"auto"` | MUST |
| 049 | Valid permission modes MUST be: `default`, `acceptEdits`, `plan`, `auto`, `bypassPermissions` (matches Claude Code CLI) | MUST |

### Package Layout
```
rondo/
├── src/
│   └── rondo/                    # -- Python package (importable)
│       ├── __init__.py           # -- public API exports
│       ├── engine.py             # -- Round, Task, Gate, GateResult, state machine
│       ├── config.py             # -- RondoConfig, TOML loading, COALESCE, validation
│       ├── dispatch.py           # -- claude -p subprocess, stream-json, TaskResult
│       ├── runner.py             # -- sequential: pre-gates → tasks → post-gates → RoundResult
│       ├── parallel.py           # -- ThreadPoolExecutor, throttle, conflicts
│       ├── overnight.py          # -- phase scheduler, watchdog, usage gating
│       ├── report.py             # -- morning report generator
│       └── cli.py                # -- CLI entry point (argparse)
├── tests/                        # -- pytest test suite (VER-100)
│   ├── test_engine.py
│   ├── test_config.py
│   ├── test_dispatch.py
│   ├── test_cli.py
│   ├── test_examples.py
│   ├── test_parallel.py
│   ├── test_overnight.py
│   └── test_report.py
├── examples/                     # -- living example rounds (also used as test fixtures)
│   ├── round_hello.py            # -- simplest possible round (1 task, no gates)
│   ├── round_file_check.py       # -- auto task + gate example
│   └── round_multi_task.py       # -- 3 tasks with model hints, pre/post gates
├── specs/                        # -- specification documents
├── spikes/                       # -- prototypes (reference only, not production)
└── rondo.toml                    # -- example config file
```
### Call Chain
```
CLI: rondo run rounds/my_round.py --workers 4 --auth max
cli.py (entry point)
  │
  ├── config.py: load_config()
  │     Find rondo.toml → parse TOML → COALESCE(CLI, config, defaults)
  │     Return frozen RondoConfig
  │
  ├── Dynamic import: load round definition file
  │     importlib.util.spec_from_file_location(path)
  │     Call module.build_round() → returns Round object
  │
  ├── Pick runner based on config.workers:
  │     workers == 1 → runner.run_sequential(round, config)
  │     workers > 1  → parallel.run_parallel(round, config)
  │
  ├── Runner dispatches each task:
  │     For each task: dispatch.dispatch_task(task, config) → TaskResult
  │     dispatch.py: subprocess Popen → stream-json parsing → TaskResult
  │
  ├── Runner assembles RoundResult:
  │     task_results + gate_results + usage + conflicts + summary
  │
  └── Output: print summary + save result files + return RoundResult
```
### Library Usage (for OB/ACE integration)
```python
from rondo import run_round, Round, Task, Gate, RondoConfig, RoundResult
# -- Consumer defines their round
def build_health_check(spec_id: str) -> Round:
    return Round(
        name=f"health-{spec_id}",
        pre_gates=[
            Gate("Spec exists", check_fn=lambda: (Path(f"specs/{spec_id}.md").exists(), "Found")),
        ],
        tasks=[
            Task(
                name="Check spec completeness",
                description=f"Verify {spec_id} has all required sections",
                instruction=f"Read specs/{spec_id}.md and check for: Purpose, Requirements, Assumptions, Decisions.",
                context_files=[f"specs/{spec_id}.md"],
                done_when="List of present/missing sections with pass/fail per section",
            ),
        ],
    )
# -- Consumer runs it
config = RondoConfig(auth="max", workers=1)
result: RoundResult = run_round(build_health_check("R027"), config=config)
# -- Consumer stores whatever they want
print(f"Status: {result.status}")
print(f"Cost: ${sum(u.cost_usd for u in result.usage):.4f}")
for tr in result.task_results:
    print(f"  {tr.task_name}: {tr.status}")
```
### Living Example Rounds
Example rounds in `examples/` serve dual purpose: documentation for users AND
test fixtures for Rondo's own test suite. They MUST be real, runnable rounds.
### Public API Contract
| ID | Requirement | Priority |
|----|-------------|----------|
| 050 | `run_round(round: Round, config: RondoConfig | None = None) -> RoundResult` MUST be the primary library entry point. It accepts a Round object and optional config (defaults to `RondoConfig()` zero-config), picks sequential or parallel runner based on `config.workers`, executes the round, and returns a RoundResult | MUST |
| 051 | `RoundResult.status` MUST be calculated from task statuses using these rules: | MUST |

    - `"done"` — all tasks have status `done`
    - `"partial"` — at least one task `done` and at least one `blocked`, `partial`, or `error`
    - `"error"` — all tasks are `error` or `blocked` (none succeeded)
    - `"skipped"` — a blocking pre-gate failed, no tasks were dispatched
    - Note: `"blocked"` is a task-level status only. At round level, blocked tasks contribute to `"partial"` or `"error"`.
### Living Example Rounds
Example rounds in `examples/` serve dual purpose: documentation for users AND
test fixtures for Rondo's own test suite. They MUST be real, runnable rounds.
| ID | Requirement | Priority |
|----|-------------|----------|
| 052 | Example rounds MUST be valid Python files with a `build_round()` function | MUST |
| 053 | Example rounds MUST be used as test fixtures in the test suite (living tests, not dead docs) | MUST |
| 054 | At minimum 3 examples MUST ship: minimal (1 task), gated (auto tasks + gates), multi-task (parallel-ready with model hints) | MUST |

#### Example: `examples/round_hello.py` — Simplest Possible Round
```python
"""Rondo example: simplest possible round — one task, no gates."""
from rondo.engine import Round, Task
def build_round() -> Round:
    return Round(
        name="hello",
        tasks=[
            Task(
                name="Say hello",
                description="Verify Rondo can dispatch a task to Claude",
                instruction="Say 'Hello from Rondo!' and confirm you received this prompt.",
                done_when="Response contains 'Hello from Rondo' or equivalent greeting",
            ),
        ],
    )
```
#### Example: `examples/round_file_check.py` — Auto Tasks + Gates
```python
"""Rondo example: auto task gate + interactive task."""
from pathlib import Path
from rondo.engine import Round, Task, Gate
TARGET = "README.md"
def build_round() -> Round:
    return Round(
        name="file-check",
        pre_gates=[
            Gate(
                "Target file exists",
                check_fn=lambda: (Path(TARGET).exists(), f"{TARGET} {'found' if Path(TARGET).exists() else 'missing'}"),
            ),
        ],
        tasks=[
            Task(
                name="Count lines",
                description=f"Auto-count lines in {TARGET}",
                auto_fn=lambda: (True, f"{sum(1 for _ in open(TARGET))} lines"),
            ),
            Task(
                name="Summarize file",
                description=f"Ask Claude to summarize {TARGET}",
                instruction=f"Read {TARGET} and write a 2-sentence summary.",
                context_files=[TARGET],
                done_when="2-sentence summary of the file's purpose",
                model="haiku",
            ),
        ],
    )
```
#### Example: `examples/round_multi_task.py` — Parallel-Ready
```python
"""Rondo example: 3 tasks with model hints, pre/post gates. Parallel-safe."""
from pathlib import Path
from rondo.engine import Round, Task, Gate
def build_round(target_dir: str = "src/") -> Round:
    return Round(
        name="code-survey",
        pre_gates=[
            Gate(
                "Directory exists",
                check_fn=lambda: (Path(target_dir).is_dir(), f"{target_dir} exists"),
            ),
        ],
        tasks=[
            Task(
                name="Count Python files",
                description="Auto-count .py files",
                auto_fn=lambda: (True, f"{len(list(Path(target_dir).rglob('*.py')))} files"),
            ),
            Task(
                name="Find TODOs",
                description="Search for TODO comments in source",
                instruction=f"Search all .py files under {target_dir} for TODO comments. List each with file and line number.",
                context_files=[target_dir],
                done_when="List of TODOs with file:line, or 'No TODOs found'",
                model="haiku",
            ),
            Task(
                name="Architecture summary",
                description="Describe the module structure",
                instruction=f"Read the top-level .py files in {target_dir} and describe the architecture in 5 bullet points.",
                context_files=[target_dir],
                done_when="5-bullet architecture summary",
                model="sonnet",
            ),
        ],
        post_gates=[
            Gate(
                "All tasks complete",
                check_fn=lambda: (True, "Post-gate placeholder"),
                blocking=False,
            ),
        ],
    )
```
---
## 16. Assumptions

| # | Assumption | If Wrong |
|---|-----------|----------|
| A1 | `claude -p` accepts arbitrary text prompts and returns text to stdout | Rondo cannot function — hard dependency |
| A2 | `CLAUDECODE` env var is the nested-session guard | Other guards may block dispatch — test each Claude version |
| A3 | Stripping `ANTHROPIC_API_KEY` causes Claude to use subscription auth | May need explicit flag — test empirically |
| A4 | Claude reliably returns structured JSON when instructed | If unreliable, parsing fallback must handle diverse output formats |
| A5 | `claude -p` is available on the system PATH | May need configurable binary path |
| A6 | Python 3.12+ is available (for `tomllib` in stdlib) | Could fall back to `tomli` package for 3.11 |

---

## 17. Success Criteria

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
│                     REQ-100: CORE                       │
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
│         ▲ REQ-101 builds on top of this ▲               │
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

Rondo wraps that with execution metadata (see STD-108 `TaskResult` for full structure):
```json
{"task_name": "...", "status": "done|blocked|partial|error|skipped",
 "model": "opus|sonnet|haiku", "auth_mode": "max|api",
 "duration_sec": 42.3, "confidence": 0.85,
 "result": "...", "raw_output": "...", "prompt_sent": "...",
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
                description="Find all public functions in the target file",
                instruction=f"Read {target_file} and list all public functions.",
                context_files=[target_file],
                done_when="List of public functions with line numbers",
                model="sonnet",
            ),
        ],
    )
```

---

## 8. States & Modes

### Core Dataclasses

```python
@dataclass
class Task:
    """A single unit of AI work."""

    # -- identity
    name: str                              # -- unique within round
    description: str = ""                  # -- brief human summary (for prompts + reports)

    # -- three-field contract (interactive tasks)
    instruction: str = ""                  # -- Do: what Claude should do
    context_files: list[str] = field(default_factory=list)  # -- Read: files for context
    done_when: str = ""                    # -- Done: completion criteria

    # -- auto task (alternative to three-field)
    auto_fn: Callable | None = None        # -- returns (passed: bool, detail: str)

    # -- dispatch hints
    model: str | None = None               # -- recommended model (COALESCE chain)
    mode: str = "interactive"              # -- "interactive" or "auto"

    @property
    def is_auto(self) -> bool:
        return self.auto_fn is not None


@dataclass
class Gate:
    """Boolean check that guards round entry or exit."""

    name: str
    check_fn: Callable[..., tuple[bool, str]]  # -- returns (passed, detail)
    blocking: bool = True                  # -- if False, failure is a warning only


**Gate calling convention:** The runner calls `gate.check_fn()` with **no arguments**.
Gates that need external context (e.g., task results for post-gates, config values)
MUST capture it via closure at round-definition time. The `Callable[..., tuple[bool, str]]`
type allows any signature, but the runner always invokes with zero args.

```python
# -- CORRECT: closure captures what the gate needs
results = []  # -- runner appends TaskResults before calling post-gates
Gate("All passed", check_fn=lambda: (all(r.status == "done" for r in results), "checked"))

# -- WRONG: gate expects arguments the runner won't pass
Gate("Needs args", check_fn=lambda results: (...))  # -- runner calls with 0 args → crash
```

@dataclass
class GateResult:
    """Outcome of running a gate check."""

    gate_name: str
    passed: bool
    detail: str                            # -- human-readable reason


@dataclass
class Round:
    """A collection of tasks with pre/post gates. The unit of work."""

    name: str
    tasks: list[Task] = field(default_factory=list)
    pre_gates: list[Gate] = field(default_factory=list)
    post_gates: list[Gate] = field(default_factory=list)
```

### Task State Machine

```
pending ──→ running ──→ done     (terminal — task completed successfully)
                   ├──→ blocked  (terminal — Claude said it can't proceed)
                   ├──→ partial  (terminal — got output, couldn't parse JSON)
                   ├──→ error    (terminal — dispatch-level failure)
                   └──→ skipped  (terminal — pre-gate blocked the round)
```

**Status vocabulary is shared with STD-108.** These 5 values are the only valid
task statuses across all of Rondo: `done`, `blocked`, `partial`, `error`, `skipped`.

No backward transitions. No re-running. A failed task stays failed for this round.

**State Machine Type:** FORWARD-ONLY
**Rationale:** Tasks move pending → running → terminal state (done/blocked/partial/error/skipped). All terminal states are final within a round. No re-running, no backward transitions.
**Rollback:** Not applicable — a new round creates new task instances. Failed tasks stay failed.

---

### Live Mode (Session 79-80 — NEW)

*Rondo in the conversation, not just overnight. Human reviews, AI executes, step by step.*

47. `rondo live <round-file>` executes a round definition INSIDE the current Claude session, not as a subprocess.
48. Live mode presents ONE task at a time. Claude reads the instruction, executes it, proves done_when. Mark reviews. Then next task.
49. Tasks with `human_input="ask"` PAUSE and present the question to Mark. Mark answers. Task continues.
50. Tasks with `human_input="defer"` log the finding and move to next task (Mark reviews later).
51. Live mode uses the SAME round definitions as batch mode. No separate format. `rondo run task.json` and `rondo live task.json` read the same file.
52. Live mode tracks execution in the event system: creates event, logs each task start/complete/skip, captures timeline.
53. Live mode output goes to terminal (not spool). Results visible immediately.
54. If Claude's context is getting large, live mode can `--checkpoint` to save progress and resume after compaction.
55. Live mode is for ORB-02 through ORB-04 (spec work with human review). Batch mode is for ORB-05+ (code building, overnight).
56. `rondo live --resume` continues from last completed task (if interrupted by compaction or session end).

**When to use which mode:**

| Mode | Command | Human Present | Use For |
|------|---------|--------------|---------|
| **Live** | `rondo live round.py` | YES — Mark reviews | Spec review, design decisions, fix approval |
| **Batch** | `rondo run round.py` | NO — overnight | Code building, test runs, check scans |
| **Dry-run** | `rondo run --dry-run round.py` | Either | Preview what would run |

---

## 10. Rules & Constraints

| Rule | Rationale |
|------|-----------|
| Python is conductor, Claude is orchestra | Python manages state and scheduling. Claude does the thinking. Never mix roles. |
| Three-field contract is mandatory | Do, Read, Done. Every interactive task needs all three. Prevents vague instructions. |
| CLAUDECODE env var always stripped | Claude Code blocks nested sessions. This is non-negotiable. |
| Results always saved to disk | Even on error. Can't rely on terminal output or memory. |
| Sequential is the safe default | Parallel is opt-in (REQ-101). One task at a time is predictable. |
| Zero external dependencies | stdlib only. Maximizes portability and ease of installation. |
| Round definitions import only engine | Keeps definitions portable. They shouldn't know about dispatch internals. |

---

## 11. Quality Attributes

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
    task_results: list[TaskResult]         # -- see STD-108 for TaskResult fields

    # -- gate results
    pre_gate_results: list[GateResult]     # -- name, passed, detail
    post_gate_results: list[GateResult]

    # -- parallel execution info (if applicable)
    conflicts: list[str]                   # -- files touched by 2+ tasks
    parallelism: int                       # -- workers used (1 = sequential)

    # -- usage metadata (from stream-json, per dispatch)
    usage: list[DispatchUsage]             # -- one per task dispatch

    # -- overall (see req 46 for calculation rules)
    status: str                            # -- "done", "partial", "error", "skipped" (4 values — no "blocked" at round level)
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
    duration_ms: int                       # -- wall-clock (ms — from stream-json, matches result event)
    duration_api_ms: int                   # -- API time only (ms — from stream-json)
    num_turns: int                         # -- tool-use loops
    context_window: int                    # -- 200000 or 1000000
    rate_limit_status: str = "unknown"     # -- "allowed", "blocked", or "unknown" (default per IFS-100 req 9)
    is_using_overage: bool = False         # -- past plan allocation? (default per IFS-100 req 9)
    rate_limit_resets_at: int = 0          # -- epoch timestamp (0 = not available)
```

### How OB/ACE Gets Total Visibility

The consumer calls Rondo and receives `RoundResult`. From that single object:

| Consumer Wants | Where In RoundResult |
|---------------|---------------------|
| What tasks ran | `task_results[*].task_name` |
| What passed/failed | `task_results[*].status` — done, blocked, partial, error, skipped (STD-108) |
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
in `results_dir` (STD-109). These files are a backup — the consumer should use
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

## 14. Standards Applied

| Standard | How Applied |
|----------|-------------|
| STD-108 Error & Resilience | Every failure includes task name, error, duration, prompt. Subprocess errors vs logic errors distinguished. |
| STD-109 Configuration | TOML config. COALESCE: CLI → config → default. Zero-config works out of the box. |
| STD-110 Concurrency & Safety | (REQ-100 is sequential only. STD-110 applied fully in REQ-101.) Subprocess args as list, never shell=True. API keys stripped from result files. |
| CORE-STD-012 | Requirement readiness tracking |
| CORE-STD-013 | TrackerData — universal tracking |
| CORE-IFS-005 | MCP standard — AI tool access |

---

## 21. Dependencies + Used By

| Depends On | Why |
|------------|-----|
| Claude Code CLI (`claude -p`) | Execution backend — the one external dependency |
| Python 3.12+ | `tomllib`, `dataclasses`, `subprocess`, `json`, `pathlib` (all stdlib) |
| No pip packages | Zero external dependencies |

---

## 22. Decisions

| # | Decision | Date | Why |
|---|----------|------|-----|
| D1 | Python over shell | 2026-03-13 | Shell can't manage state machines, parse JSON, or implement gate logic |
| D2 | Three-field contract (Do/Read/Done) | 2026-03-13 | Self-describing tasks. Prevents vague prompts. The API between conductor and orchestra |
| D3 | Dual auth via env stripping | 2026-03-13 | Subscription = free capacity. API = pay-per-token. Same code, different env |
| D4 | COALESCE for model routing | 2026-03-13 | Round authors describe intent. Operators override. Config sets project default |
| D5 | Results always to JSON files | 2026-03-13 | Files survive crashes, restarts, compaction. Terminal output doesn't |
| D6 | Zero external dependencies | 2026-03-13 | stdlib only. Anyone with Python + Claude Code can use Rondo |
| D7 | Rondo is its own product | 2026-03-13 | Not an OB feature. Not an ACE feature. A standalone framework |
| D8 | Sequential default | 2026-03-13 | Parallel is REQ-101's concern. REQ-100 is simple and predictable |

---

## 23. Open Questions

| # | Question | Status |
|---|----------|--------|
| Q1 | Should Rondo have its own lightweight DB for run history? | **Answered: No.** Rondo produces structured output (RoundResult). Consumer stores it. See "Data Boundary" section. |
| Q2 | What's the rate limit on Max plan `claude -p`? | **Partially answered.** rate_limit_event gives 5-hour window status. Weekly % not available programmatically. (Spike: Session 76) |
| Q3 | Should the binary path for `claude` be configurable? | **Answered: Yes.** `claude_binary` in STD-109 config. Default: "claude" |
| Q4 | Should round definitions live in TOML or Python? | **Answered: Python** — they need logic |
| Q5 | Should Rondo support alternative backends (Ollama, API-direct)? | Deferred |

---

## 24. Glossary

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
| **GateResult** | Outcome of a gate check: gate_name, passed, detail. |
| **TaskResult** | Full outcome of a dispatched task. Defined in STD-108. |
| **RoundResult** | Aggregate of all task + gate results. Returned to consumer. |
| **DispatchUsage** | Per-dispatch metadata from stream-json (cost, tokens, rate limit). |
| **Capacity mining** | Using idle subscription capacity for automated AI work at $0 extra cost. |

---

## 25. Risk / Criticality

| Req # | Criticality | Failure Consequence |
|-------|-------------|-------------------|
| 13 (CLAUDECODE strip) | HIGH | All dispatch fails — complete blocker |
| 17-18 (auth) | HIGH | Wrong billing — charges API when should use subscription |
| 27 (error on bad exit) | HIGH | Silent failures — tasks appear to run but produce nothing |
| 10 (serialization) | MEDIUM | Can't recover after crash or compaction |
| 26 (malformed JSON) | MEDIUM | Good results discarded because parsing fails |

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

— if applicable.

---

## 9. Configuration

— if applicable.

---

## 12. Shared Patterns

— if applicable.

---

## 13. Integration Points

REQUIRED — fill before build.

---

## 15. Self-Correction

— if applicable.

---

## 18. Build Notes / Estimate

— filled during build.

---

## 19. Test Categories

— filled during build.

---

## 20. Failure Modes

— if applicable.

---

## 26. External Scan

— if applicable.

---

## 27. Security Considerations

— if applicable.

---

## 28. Performance / Resource

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

### Feature Maturity

| Feature | Maturity | Evidence | Retest |
|---------|----------|----------|--------|
| Round/Task/Gate data model | SPIKED | Spike prototyped engine with dataclasses | Phase 1 build |
| Three-field contract (Do/Read/Done) | SPIKED | Spike validated claude -p with 3-field prompts | Phase 1 build |
| Task state machine | THEORY | Specced: pending/running/done/blocked/partial/error/skipped | Phase 1 build |
| Auth switching (Max plan vs API key) | WORKING | API key regenerated, Max plan active | After plan changes |
| Model routing (opus/sonnet/haiku) | THEORY | Specced for per-task model selection | Phase 1 build |
| Round state serialization | THEORY | Specced for JSON-based recovery | Phase 1 build |


## 35. Change History

| Version | Date | What Changed |
|---------|------|-------------|
| 0.1 | 2026-03-13 | Initial draft from spike learnings (Session 75) |
| 0.2 | 2026-03-13 | Split from monolithic spec. REQ-100=core, REQ-101=automation. Removed OB/ACE references. Own foundations. |
| 0.3 | 2026-03-14 | Added Data Boundary section: RoundResult, DispatchUsage, result file structure. Answered Q1 (no DB), Q2 (rate_limit_event), Q3 (configurable binary). |
| 0.4 | 2026-03-14 | Deep review fixes: formal Task/Gate/GateResult/Round dataclasses, aligned status vocabulary (done/blocked/partial/error/skipped) with CORE-IFS-001 reqs 53-54 (status vocabulary), added description field to Task, added model hint to Task, RoundResult.status uses same vocabulary, duration units clarified (ms from stream-json, sec for wall-clock) |
| 0.5 | 2026-03-14 | Added reqs 34-44: package structure, CLI entry point (run/overnight/report/dry-run subcommands), dynamic round loading, auto sequential/parallel detection, living example rounds (3 examples as test fixtures), library usage pattern, call chain diagram |
| 0.6 | 2026-03-14 | Deep review v2 fixes: added reqs 45-46 (run_round contract, RoundResult.status calculation), gate calling convention documented, DispatchUsage defaults for rate limit fields, dry-run changed from subcommand to --dry-run flag on run, test_cli.py + test_examples.py added to package layout |
| 0.7 | 2026-03-14 | Added reqs 47-49: `--permission-mode` dispatch flag — controls Claude Code tool access prompts in non-interactive subprocess dispatch |
| 0.8 | 2026-03-14 | Defense in depth: validate_task() + validate_round() pre-flight in engine.py, VALID_MODELS fail-fast in dispatch, CLI exit code contract (0/1/2/130), validate_config() at CLI boundary, KeyboardInterrupt + catch-all exception handling. Cross-ref CORE-IFS-001 reqs 53-54 (status vocabulary). |
