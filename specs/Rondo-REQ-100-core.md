# Rondo-REQ-100: Core — Engine + Dispatch

*Define AI tasks in Python, send them to Claude, get structured results back.*

**Created:** 2026-03-13 | **Status:** DRAFT
**Classification:** open
**Version:** 1.3
**Owner:** Mark G. Hubers
**Reviewed:** not-yet
**Supersedes:** none
**Depends on:** Claude Code CLI (`claude -p`), Rondo-STD-108 (Error & Resilience), Rondo-STD-109 (Configuration), Rondo-IFS-100 (Provider Interface), CORE-STD-001 (Data Standards — status vocabulary), Python 3.12+ (for `tomllib`) | **Blocks:** Rondo-REQ-101 (Automation), Rondo-REQ-103 (Dispatch Preflight)
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
- Parallel execution (Rondo-REQ-101: Automation)
- Overnight scheduling (Rondo-REQ-101: Automation)
- Morning reports (Rondo-REQ-101: Automation)
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
| 003 | An **interactive task** MUST have three fields: instruction (Do), context_files (Read), done_when (Done). This is the **three-field contract**. **Sandboxing:** context_files paths MUST be resolved relative to the project root and validated: (1) no `..` traversal, (2) no symlinks outside project root, (3) no absolute paths, (4) total context size capped at `max_context_bytes` (default 500KB). Paths failing validation are rejected with `context_file_rejected` error. | MUST |
| 004 | An **auto task** MUST have: a Python callable that returns `(passed: bool, detail: str)` | MUST |
| 005 | A **Gate** MUST have: a name, a check function, and a blocking flag. Blocking gates halt the round on failure | MUST |
| 006 | Pre-gates MUST run before any task dispatch. If a blocking pre-gate fails, no tasks run | MUST |
| 007 | Post-gates MUST run only after all tasks complete | MUST |

### Engine — State Machine
| ID | Requirement | Priority |
|----|-------------|----------|
| 008 | Task status MUST follow this state machine: `pending → in_progress → done | blocked | partial | error | skipped`. No other transitions. The transient state `in_progress` aligns with CORE-STD-001 req 021 shared lifecycle vocabulary. See "Task State Machine" below and Rondo-STD-108 for definitions | MUST |
| 009 | System SHALL a round is "complete" when all tasks are in a terminal state (done, blocked, partial, error, or skipped) | MUST |
| 010 | Round state (task statuses, gate results) MUST be serializable to JSON for recovery after interruption | MUST |
| 011 | A round MUST be resumable from serialized state — load JSON, skip completed tasks, continue from next pending | MUST |

### Dispatch — Subprocess
| ID | Requirement | Priority |
|----|-------------|----------|
| 012 | Dispatch MUST invoke `claude -p` as a subprocess with the task's three-field contract formatted as the prompt. For automated (non-interactive) dispatch, `--bare` MUST be added when available (Claude Code v2.1.81+, see Rondo-REQ-101 reqs 053-054) to strip hooks, LSP, and plugins | MUST |
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
| 023 | For code fixing tasks (needs file access in sandbox): dispatch MUST pass `--dangerously-skip-permissions` (only in containers with no internet). **Safer variant:** `--allow-dangerously-skip-permissions` enables bypass as an option without it being the default — prefer this for sandbox environments where some permission control is desired. | MUST |
| 024 | Task definition MUST include `tool_mode: "none" | "sandbox" | "default"` to control which flag is used | MUST |

### Dispatch — Bare Flag (Headless Execution)
| ID | Requirement | Priority |
|----|-------------|----------|
| 071 | Dispatch MUST detect Claude Code version at startup (via `claude --version`) and add `--bare` flag when available (v2.1.81+). Violation ID: `REQ100-BARE-DETECT` | MUST |
| 072 | Flag precedence: `--output-format stream-json` is mandatory (req 015), `--bare` is additive. `--bare` skips hooks/plugins for speed but does not replace stream-json. The full command for automated dispatch is: `claude -p --output-format stream-json --bare --model M` | MUST |
| 073 | When `--bare` is used, Caliber guards (Check/Block/Brief) are bypassed — only use `--bare` for automated/read-only tasks. Tasks requiring Caliber enforcement MUST NOT use `--bare`. Task definition MAY include `bare: false` to opt out. Violation ID: `REQ100-BARE-CALIBER` | MUST |

### Dispatch — Inline Plan (Session 94 — MCP optimization)
| ID | Requirement | Priority |
|----|-------------|----------|
| 082 | When `rondo_run` is called via MCP with a Claude model name (sonnet/opus/haiku or empty) and `prompt` is provided, Rondo MUST return an `inline_dispatch_plan` JSON instead of spawning a subprocess. The host (Claude Code) executes the plan inline. This is the 90% case — callers want the current session's context. | MUST |
| 088 | To force a clean subprocess (separate context), callers MUST use the `:new` suffix: `model="sonnet:new"`. This strips the suffix and dispatches via subprocess with `--bare`. Use when you need isolated context or a different model than the current session. | MUST |
| 083 | `inline_dispatch_plan` schema: `{kind: "inline_dispatch_plan", prompt, done_when, model: "current", project, note}`. Host reads this and does the work in the current session. | MUST |
| 084 | When `model=""` and `file_path` is provided (round file mode), Rondo MUST dispatch normally (not return a plan). Round files need real dispatch infrastructure. | MUST |
| 085 | `background=True` is ignored when model is omitted — inline plans execute in the foreground by the host. No background job is created. | MUST |
| 086 | Inline dispatch plans skip audit/history/metrics (Rondo didn't do the work — the host did). The ai_help documentation MUST state this clearly. | MUST |
| 087 | `bare=True` is the default for subprocess dispatch (Session 94 — Finding #198). Subprocess startup drops from 70s to ~5s. Tasks requiring Caliber hooks MUST set `bare=False`. | MUST |

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

### Dispatch — Circuit Breaker
| ID | Requirement | Priority |
|----|-------------|----------|
| 057 | If 3 consecutive tasks fail with the same dispatch-level error (subprocess crash, auth failure, API timeout), the runner MUST halt the round and report `circuit_breaker_tripped` with the repeated error. | MUST |
| 058 | Circuit breaker resets when a task succeeds. Individual task failures (bad output, wrong result) do NOT trip the breaker — only systemic dispatch errors. | MUST |
| 059 | After circuit breaker trips, remaining tasks are marked `skipped` with reason `circuit_breaker`. Round status = `error`. | MUST |

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
| 042 | CLI subcommands MUST include: `run` (execute a round), `overnight` (batch scheduler), `report` (generate morning report). Dry-run is a `--dry-run` flag on `run`, not a separate subcommand (Rondo-STD-109). All subcommands are single-word. Multi-word subcommands, if added later, MUST use kebab-case per CORE-STD-001 req 019 | MUST |
| 043 | The `run` subcommand MUST accept a path to a Python file containing a `build_round()` function that returns a `Round` object | MUST |
| 044 | Round definition files MUST be loadable by path — Rondo dynamically imports the file and calls `build_round()` | MUST |
| 045 | Rondo MUST auto-detect sequential vs parallel: `workers == 1` uses `runner.py`, `workers > 1` uses `parallel.py` | MUST |
| 046 | All CLI flags from Rondo-STD-109 (--workers, --model, --auth, etc.) MUST be available on the `run` subcommand | MUST |

### Dispatch — Permission Mode
| ID | Requirement | Priority |
|----|-------------|----------|
| 047 | Dispatch MUST pass `--permission-mode` to the subprocess from the config's `permission_mode` field | MUST |
| 048 | Permission mode MUST follow the COALESCE pattern: CLI flag → config file → default `"auto"` | MUST |
| 049 | Valid permission modes MUST be: `default`, `acceptEdits`, `plan`, `auto`, `dontAsk`, `bypassPermissions` (matches Claude Code CLI v2.1.86+). `dontAsk` silently skips permission prompts without full bypass — safer than `bypassPermissions` for automated dispatch. | MUST |

### Dispatch — Cost & Output Control (Session 91 — CC v2.1.86 flags)
| ID | Requirement | Priority |
|----|-------------|----------|
| 078 | Dispatch SHOULD pass `--max-budget-usd` to cap per-task API cost. Value follows COALESCE: task field → config `max_budget_usd` → default `null` (no cap). When set, CC kills the subprocess if budget exceeded. | SHOULD |
| 079 | Dispatch SHOULD pass `--json-schema` with Rondo's result contract schema to enforce structured output at CC level. This eliminates the malformed-JSON fallback path. Schema: `{"type":"object","properties":{"status":{"enum":["done","error","partial","blocked"]},"confidence":{"type":"number"},"result":{"type":"string"},"question":{"type":"string"}},"required":["status","result"]}` | SHOULD |
| 080 | Dispatch MAY pass `--system-prompt` to set persistent dispatch context (e.g., "You are executing a Rondo automated task. Return JSON matching the result contract."). This improves result parsing reliability. Value from config `dispatch_system_prompt` field. | MAY |
| 081 | Dispatch MAY pass `--no-session-persistence` to prevent ephemeral dispatch sessions from cluttering CC's session store. Default: enabled for all automated dispatch. | MAY |

### Dispatch — Granular Tool Control (Session 91)
| ID | Requirement | Priority |
|----|-------------|----------|
| 082 | Dispatch MAY pass `--allowed-tools` and/or `--disallowed-tools` for per-tool control when `tool_mode` is `default`. These provide finer granularity than `tool_mode` (which is all-or-nothing). Example: `--allowed-tools "Read,Grep"` for review-only tasks. | MAY |
| 083 | `--allowed-tools`/`--disallowed-tools` MUST NOT be combined with `tool_mode: none` (redundant — no tools to filter). If `tool_mode` is `none`, these flags are ignored. | MUST |

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
│       ├── parallel.py           # -- (Rondo-REQ-101 scope) ThreadPoolExecutor, throttle, conflicts
│       ├── overnight.py          # -- (Rondo-REQ-101 scope) phase scheduler, watchdog, usage gating
│       ├── report.py             # -- (Rondo-REQ-101 scope) morning report generator
│       └── cli.py                # -- CLI entry point (argparse)
├── tests/                        # -- pytest test suite (Rondo-VER-100)
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

#### Example: `examples/rounds/round_hello.py` — Simplest Possible Round
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
## 4. Architecture / Design

### Layer Architecture

Rondo's core is three layers, each with a single responsibility:

```
┌──────────────────────────────────────────────────────────────┐
│                       Rondo-REQ-100: CORE                          │
│                                                              │
│  L0: ENGINE (engine.py)                                      │
│    Round, Task, Gate dataclasses + state machine              │
│    Pure data — no I/O, no subprocess, no side effects         │
│    Validates: task names unique, gates have check_fn,         │
│    status transitions follow CORE-STD-001 vocabulary          │
│                                                              │
│  L1: DISPATCH (dispatch.py)                                  │
│    Subprocess orchestration: claude -p with stream-json       │
│    Auth switching (Max plan vs API key via env stripping)     │
│    Model routing (COALESCE: CLI → task → config → default)   │
│    Result capture: stdout/stderr/exit code → TaskResult       │
│    Tool control: --tools "" | --dangerously-skip-permissions  │
│    Permission mode: --permission-mode (COALESCE pattern)      │
│                                                              │
│  L2: RUNNER (runner.py)                                      │
│    Sequential execution: pre-gates → tasks → post-gates       │
│    Assembles RoundResult from task + gate results              │
│    Saves result JSON files to results_dir                     │
│    Returns RoundResult to caller (primary data path)          │
│                                                              │
│         ▲ Rondo-REQ-101 adds: parallel.py, overnight.py, report.py │
└──────────────────────────────────────────────────────────────┘
```

### Component Interactions

```
Consumer (OB, ACE, script)
    │
    ├── Option A: CLI
    │   rondo run round.py --workers 1 --auth max --model sonnet
    │   → cli.py → config.py → dynamic import → runner.py → dispatch.py
    │
    └── Option B: Library
        from rondo import run_round, Round, Task, RondoConfig
        result = run_round(my_round, config)
        → runner.py → dispatch.py → returns RoundResult
```

### Dispatch Subprocess Detail

```
dispatch_task(task, config):
    1. Build prompt from three-field contract (Do/Read/Done)
    2. Select model: COALESCE(cli_flag, task.model, config.default_model, "sonnet")
    3. Select auth: strip ANTHROPIC_API_KEY (max) or preserve it (api)
    4. Strip CLAUDECODE env var (always — prevents nested session trap)
    5. Select tool_mode: --tools "" (none) | --dangerously-skip-permissions (sandbox) | default
    6. Select permission_mode: --permission-mode {mode} (COALESCE pattern)
    7. Invoke: subprocess.Popen(["claude", "-p", "--output-format", "stream-json",
                                 "--model", model, ...], env=clean_env, timeout=task_timeout_sec)
    8. Parse stream-json: extract tokens, cost, cache stats, rate_limit_event
    9. Parse Claude's JSON response: {status, confidence, result, question}
   10. Return TaskResult + DispatchUsage
```

### tool_mode vs permission_mode Interaction

These two settings control different aspects of Claude's tool access:

| Setting | Controls | Values | When to Use |
|---------|----------|--------|-------------|
| `tool_mode` (reqs 022-024) | Which file tools Claude has | `none` (--tools ""), `sandbox` (--dangerously-skip-permissions), `default` | Code generation (none), code fixing (sandbox), general (default) |
| `permission_mode` (reqs 047-049) | How Claude asks for permission | `default`, `acceptEdits`, `plan`, `auto`, `dontAsk`, `bypassPermissions` | Controls interactive prompts in subprocess. `dontAsk` is preferred for automated dispatch (skips prompts without full bypass). |

**Precedence:** `tool_mode` is applied first (determines available tools). `permission_mode` is applied second (determines permission prompts for available tools). If `tool_mode` is `none`, `permission_mode` is irrelevant (no tools to prompt for). Both follow the COALESCE pattern independently: CLI → config → default.

### Data Flow

```
Round Definition (Python)
    │
    ▼
Engine validates (L0)
    │
    ▼
Runner executes (L2)
    ├── Pre-gates: check_fn() → GateResult
    │   (blocking gate fails → all tasks skipped, round status = "skipped")
    ├── Tasks: dispatch_task() → TaskResult + DispatchUsage
    │   (each task independent — failure does not affect others)
    └── Post-gates: check_fn() → GateResult
    │
    ▼
RoundResult returned to caller
    ├── Primary: return object (consumer stores what they want)
    └── Backup: JSON files in results_dir (crash recovery)
```

---

## 5. Data Model

Rondo has no database tables. All data is in-memory Python dataclasses during execution
and JSON files on disk after execution. The core dataclasses are defined in §8 (States & Modes):

| Dataclass | Purpose | Lifecycle |
|-----------|---------|-----------|
| `Task` | Single unit of AI work (interactive or auto) | Created by round definition, consumed by dispatch |
| `Gate` | Boolean check guarding round entry/exit | Created by round definition, evaluated by runner |
| `Round` | Collection of tasks + gates | Created by round definition, consumed by runner |
| `GateResult` | Outcome of a gate check | Created by runner, stored in RoundResult |
| `TaskResult` | Full outcome of a dispatched task (per Rondo-STD-108) | Created by dispatch, stored in RoundResult |
| `RoundResult` | Aggregate of all results for a round execution | Created by runner, returned to consumer |
| `DispatchUsage` | Per-dispatch metadata from stream-json | Created by dispatch, stored in RoundResult |
| `RondoConfig` | Frozen configuration (TOML + CLI + defaults) | Created by config.py, consumed by all layers |

**No tables owned.** Rondo is a dispatch framework, not a data store.
The consumer (OB, ACE, scripts) decides what to persist from the returned RoundResult.

---

## 6. Data Boundary

**Rondo has no database.** It is a dispatch framework, not a data store.

### What Rondo Produces

| Output | Format | Consumer |
|--------|--------|----------|
| `RoundResult` | Python dataclass (primary) | Calling code (OB, ACE, scripts) |
| Result JSON files | JSON in `results_dir` (backup) | Crash recovery, replay |
| Spool files (Rondo-REQ-101) | JSON in `~/.rondo/spool/` (unattended runs) | Consumer pickup via mailbox pattern |

**Canonical data path:** The `RoundResult` return object is the primary output.

**Two distinct storage paths (neither is a database):**

| Path | Owner | Purpose | Lifecycle | Written When |
|------|-------|---------|-----------|-------------|
| `results_dir` | Consumer-owned | Write-once archive of RoundResults for crash recovery and replay | Permanent — consumer manages retention | Always (every round) |
| `spool/` (Rondo-REQ-101) | Rondo-owned | Stateful mailbox buffer for disconnected consumers | TTL-based cleanup (default 7 days), CLEAN/EXPORT lifecycle | Only when no consumer connected at runtime |

`results_dir` is a backup — immutable after write, consumer reads for replay/debugging.
`spool/` is a mailbox — consumer picks up and deletes, Rondo manages TTL and cleanup.
Neither is a database. Neither supports queries, indexes, or schema migrations.

When a consumer is connected (e.g., OB calling Rondo via library), the result goes
directly to the consumer — no spool file written. `results_dir` is still written as backup.

### What Rondo Consumes

| Input | Format | Producer |
|-------|--------|----------|
| Round definition | Python file with `build_round()` | Consumer |
| Config | TOML (`rondo.toml` or `.rondo/config.toml` per Rondo-STD-109) | User / project |
| Claude Code CLI | Binary on PATH | System |
| Environment variables | `ANTHROPIC_API_KEY`, `CLAUDECODE` | System |

### What Rondo Does NOT Own

Rondo does NOT interact with any database tables. The `tactical_solutions` and
`upstream_watches` tables defined in CORE-STD-022 are CORE tables accessed via
the `ob` CLI — not by Rondo's dispatch engine. Rondo overnight jobs (Rondo-REQ-101) may
run scripts that query those tables, but the scripts are the consumer's responsibility,
not Rondo's. Rondo dispatches the script; the script accesses the database.

### Configuration File Location

The Rondo configuration file follows Rondo-STD-109 conventions. The canonical locations are:

1. `rondo.toml` in the project root (project-specific config)
2. `.rondo/config.toml` in the project root (alternative location for projects that prefer dotfile directories)
3. `~/.config/rondo/config.toml` (user-level defaults)

COALESCE order: CLI flags → project `rondo.toml` → `.rondo/config.toml` → user config → built-in defaults.

---

## 7. MCP / API Interface

Not applicable for this spec type — see related sections for details.

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


**Gate calling convention:** The runner calls `gate.check_fn(ctx)` with a **GateContext** argument.
Gates MAY ignore the argument (backward-compatible with zero-arg lambdas via `*args` catch).
GateContext provides: `ctx.task_results` (list of completed TaskResults), `ctx.round_name`, `ctx.config` (Rondo config dict), `ctx.elapsed_seconds`. This replaces brittle closure-based state capture with explicit dependency injection.

```python
@dataclass
class GateContext:
    task_results: list[TaskResult]
    round_name: str
    config: dict
    elapsed_seconds: float
```

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
                         ┌──→ done     (terminal — task completed successfully)
                         ├──→ blocked  (terminal — Claude said it can't proceed)
pending ──→ in_progress ─┼──→ partial  (terminal — got output, couldn't parse JSON)
  │                      ├──→ error    (terminal — dispatch-level failure)
  │                      └──→ skipped  (terminal — pre-gate blocked the round)
  │
  └── Initial state for all tasks at round creation
```

**7-state vocabulary (per CORE-STD-001 req 021):**
`pending`, `in_progress`, `done`, `partial`, `error`, `skipped`, `blocked`.

Rondo uses all 7 values. `pending` is the initial state — every task starts here
when a Round is created. `in_progress` is the sole transient state (replaces the
earlier term `running`, changed in v1.0 for cross-product consistency). Terminal
task statuses are: `done`, `blocked`, `partial`, `error`, `skipped`.

**Transition restrictions: forward-only.** No backward transitions (e.g., no
`done → pending`, no `error → in_progress`). No re-running within a round. A
failed task stays failed. To retry, create a new round with new task instances.

**State Machine Type:** FORWARD-ONLY
**Rationale:** Tasks move pending → in_progress → terminal state (done/blocked/partial/error/skipped). All terminal states are final within a round. No re-running, no backward transitions.
**Rollback:** Not applicable — a new round creates new task instances. Failed tasks stay failed.

---

### Live Mode (Session 79-80)

*Rondo in the conversation, not just overnight. Human reviews, AI executes, step by step.*

**Live mode is human-in-loop — no subprocess dispatch.** The current Claude session
executes tasks directly via tool calls. There is no `dispatch.py` invocation, no
`ThreadPoolExecutor`, no spool writes. Live mode does NOT use `dispatch.py`,
`subprocess.Popen`, or the spool directory. Batch mode (`rondo run`) dispatches via
`claude -p` subprocess. The distinction is architectural: live = in-process tool
calls within the current session; batch = out-of-process subprocess dispatch.

**Architecture reconciliation:** These are TWO execution backends for the SAME round definitions. The `RondoEngine` interface is shared — only the executor differs (LiveExecutor vs BatchExecutor). The round definition format, gate interface, task contract, and event system are identical. Code sharing: ~80% shared (engine, gates, events, results), ~20% per-mode (executor, output, checkpointing).

| ID | Requirement | Priority |
|----|-------------|----------|
| 061 | `rondo live <round-file>` MUST execute a round definition INSIDE the current Claude session, not as a subprocess | MUST |
| 062 | Live mode MUST present ONE task at a time. Claude reads the instruction, executes it, proves done_when. Human reviews. Then next task | MUST |
| 063 | Tasks with `human_input="ask"` MUST PAUSE and present the question to the human. Human answers. Task continues | MUST |
| 064 | Tasks with `human_input="defer"` MUST log the finding and move to next task (human reviews later) | MUST |
| 065 | Live mode MUST use the SAME round definitions as batch mode. No separate format. `rondo run round.py` and `rondo live round.py` read the same file | MUST |
| 066 | Live mode MUST track execution in the event system: creates event, logs each task start/complete/skip, captures timeline | MUST |
| 067 | Live mode output MUST go to terminal (not spool). Results visible immediately | MUST |
| 068 | Live mode SHOULD support `--checkpoint` to save progress and resume after compaction | SHOULD |
| 069 | Live mode is for ORB-02 through ORB-04 (spec work with human review). Batch mode is for ORB-05+ (code building, overnight) | SHOULD |
| 070 | `rondo live --resume` MUST continue from last completed task (if interrupted by compaction or session end) | MUST |

**When to use which mode:**

| Mode | Command | Human Present | Use For |
|------|---------|--------------|---------|
| **Live** | `rondo live round.py` | YES — Mark reviews | Spec review, design decisions, fix approval |
| **Batch** | `rondo run round.py` | NO — overnight | Code building, test runs, check scans |
| **Dry-run** | `rondo run --dry-run round.py` | Either | Preview what would run |

### Task Safety (Gemini finding)

| ID | Requirement | Priority |
|----|-------------|----------|
| 074 | Every dispatched task MUST have a `task_timeout_sec` with default 300 seconds. This is the hard wall-clock limit. When Rondo-REQ-101's watchdog is active, `task_timeout_sec` is the upper bound — the watchdog fires on output silence, but the task timeout is the absolute maximum regardless of output | MUST |
| 075 | Every batch round MUST have a `round_timeout_sec` with default 3600 seconds | MUST |
| 076 | `subprocess.Popen` MUST be wrapped in strict timeout enforcement | MUST |
| 077 | On timeout, task status MUST become `error` with error_code `ERR_TIMEOUT` and reason `timeout_exceeded`. Round continues to next task | MUST |

---

## 9. Configuration

Configuration follows Rondo-STD-109 conventions. See §6 Data Boundary for file locations.

| Setting | CLI Flag | Config Key | Default | Description |
|---------|----------|------------|---------|-------------|
| Workers | `--workers N` | `workers` | 1 | Number of parallel workers (1 = sequential) |
| Model | `--model M` | `default_model` | `sonnet` | Default model for dispatch |
| Auth | `--auth max\|api` | `auth` | `max` | Auth mode (subscription vs API key) |
| Tool mode | `--tool-mode` | `tool_mode` | `default` | `none`, `sandbox`, `default` |
| Permission mode | `--permission-mode` | `permission_mode` | `auto` | Claude Code permission mode |
| Dry run | `--dry-run` | — | `false` | Show prompts without dispatching |
| Results dir | `--results-dir` | `results_dir` | `reports/rondo-results/` | Where to save result JSON files |
| Task timeout | `--task-timeout` | `task_timeout_sec` | 300 | Hard wall-clock limit per task (seconds) |
| Round timeout | `--round-timeout` | `round_timeout_sec` | 3600 | Hard wall-clock limit per round (seconds) |

All settings follow COALESCE: CLI flag → config file → built-in default.

---

## 10. Rules & Constraints

| Rule | Rationale |
|------|-----------|
| Python is conductor, Claude is orchestra | Python manages state and scheduling. Claude does the thinking. Never mix roles. |
| Three-field contract is mandatory | Do, Read, Done. Every interactive task needs all three. Prevents vague instructions. |
| CLAUDECODE env var always stripped | Claude Code blocks nested sessions. This is non-negotiable. |
| Results always saved to disk | Even on error. Can't rely on terminal output or memory. |
| Sequential is the safe default | Parallel is opt-in (Rondo-REQ-101). One task at a time is predictable. |
| Zero external dependencies (core engine) | The `rondo` Python package uses stdlib only. Maximizes portability. Rondo's core engine has no database dependency. Consumer scripts dispatched by Rondo may have their own dependencies (e.g., OB scripts query databases), but that is the consumer's concern, not Rondo's. |
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
    started_at: str                        # -- ISO-8601 UTC (domain name — not a DB table, so
                                           #    created_at/updated_at convention from STD-001 req 003
                                           #    does not apply. started_at/completed_at conveys
                                           #    execution semantics more clearly for a return object)
    completed_at: str                      # -- ISO-8601 UTC
    duration_sec: float                    # -- wall-clock total

    # -- task results (one per task)
    task_results: list[TaskResult]         # -- see Rondo-STD-108 for TaskResult fields

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
    rate_limit_status: str = "unknown"     # -- "allowed", "blocked", or "unknown" (default per Rondo-IFS-100 req 9)
    is_using_overage: bool = False         # -- past plan allocation? (default per Rondo-IFS-100 req 9)
    rate_limit_resets_at: int = 0          # -- epoch timestamp (0 = not available)
```

### How OB/ACE Gets Total Visibility

The consumer calls Rondo and receives `RoundResult`. From that single object:

| Consumer Wants | Where In RoundResult |
|---------------|---------------------|
| What tasks ran | `task_results[*].task_name` |
| What passed/failed | `task_results[*].status` — done, blocked, partial, error, skipped (Rondo-STD-108) |
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
in `results_dir` (Rondo-STD-109). These files are a backup — the consumer should use
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

## 12. Shared Patterns / Tactical Solutions

### Tactical Solutions (per CORE-STD-022)

| TAC ID | Title | Dependency | Break Risk | Status |
|--------|-------|------------|------------|--------|
| TAC-RON-001 | `claude -p` non-interactive mode | Relies on `claude -p` behaving predictably; no formal API contract | CLI changes could break all dispatch | active |
| TAC-RON-002 | JSONL as primary storage | No formal schema; parsing relies on line-by-line JSON | Schema changes break result parsing | active |

### Shared Patterns

- **Three-field contract (Do/Read/Done):** Every interactive task uses the same three fields. Adopted by all consumers.
- **COALESCE routing:** CLI → config → task → default. Used for model, auth, permission_mode, tool_mode.
- **Gate closures:** Gates capture context at definition time via closures. Runner calls with zero args.

---

## 13. Integration Points

| Integration | Spec | Direction | Contract |
|-------------|------|-----------|----------|
| Claude Code CLI | External | Outbound | `claude -p --output-format stream-json --model M` subprocess |
| Preflight | Rondo-REQ-103 | Inbound | PreflightResult (GREEN/YELLOW/RED) before dispatch |
| Parallel/Overnight | Rondo-REQ-101 | Builds on | Rondo-REQ-101 imports engine.py, dispatch.py, runner.py |
| OB integration | Rondo-IFS-102 | Outbound | RoundResult returned to OB for storage in sprint_results |
| ACE integration | ACE consumers | Outbound | RoundResult returned for knowledge engine ingestion |
| CORE-STD-022 | CORE-STD-022 | Indirect | Rondo overnight jobs may dispatch scripts that query tactical_solutions — but Rondo's core engine has no direct DB dependency |
| Configuration | Rondo-STD-109 | Inbound | TOML config loading, CLI flag definitions |
| Error handling | Rondo-STD-108 | Shared | TaskResult fields, error codes, status vocabulary |
| `ob` CLI | External | Integration | CORE-STD-022 tactical tracking exposed via `ob` CLI, not Rondo CLI. Rondo is standalone (D7) |

---

## 14. Standards Applied

| Standard | How Applied |
|----------|-------------|
| Rondo-STD-108 Error & Resilience | Every failure includes task name, error, duration, prompt. Subprocess errors vs logic errors distinguished. |
| Rondo-STD-109 Configuration | TOML config. COALESCE: CLI → config → default. Zero-config works out of the box. |
| Rondo-STD-110 Concurrency & Safety | (Rondo-REQ-100 is sequential only. Rondo-STD-110 applied fully in Rondo-REQ-101.) Subprocess args as list, never shell=True. API keys stripped from result files. |
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
│                     Rondo-REQ-100: CORE                       │
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
│         ▲ Rondo-REQ-101 builds on top of this ▲               │
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

Rondo wraps that with execution metadata (see Rondo-STD-108 `TaskResult` for full structure):
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
| D8 | Sequential default | 2026-03-13 | Parallel is Rondo-REQ-101's concern. Rondo-REQ-100 is simple and predictable |
| D9 | 7-state vocabulary subset per CORE-STD-001 | 2026-03-25 | Rondo uses the full 7-state vocabulary: pending, in_progress, done, partial, error, skipped, blocked. Transition restrictions: forward-only (no completed→pending, no error→in_progress). `pending` is initial state, `in_progress` is sole transient state, 5 terminal states. Vocabulary is a strict subset — no custom states invented. |
| D10 | Dataclass timestamps use domain semantics | 2026-03-25 | Rondo dataclass timestamps (started_at/completed_at) use domain semantics, not DB conventions (created_at/updated_at). Rondo dataclasses are NOT database tables — they're serialized to JSONL. Display format: ISO-8601 UTC per CORE-STD-001 req 001. DB naming conventions from STD-001 req 003 do not apply to in-memory return objects. |

---

## 23. Open Questions

| # | Question | Status |
|---|----------|--------|
| Q1 | Should Rondo have its own lightweight DB for run history? | **Answered: No.** Rondo produces structured output (RoundResult). Consumer stores it. See "Data Boundary" section. |
| Q2 | What's the rate limit on Max plan `claude -p`? | **Partially answered.** rate_limit_event gives 5-hour window status. Weekly % not available programmatically. (Spike: Session 76) |
| Q3 | Should the binary path for `claude` be configurable? | **Answered: Yes.** `claude_binary` in Rondo-STD-109 config. Default: "claude" |
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
| **TaskResult** | Full outcome of a dispatched task. Defined in Rondo-STD-108. |
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
| Round/Task/Gate data model | SPIKED | Spike prototyped engine with dataclasses | Phase 1 build |
| Three-field contract (Do/Read/Done) | SPIKED | Spike validated claude -p with 3-field prompts | Phase 1 build |
| Task state machine | THEORY | Specced: pending/in_progress/done/blocked/partial/error/skipped (CORE-STD-001 aligned) | Phase 1 build |
| Auth switching (Max plan vs API key) | WORKING | API key regenerated, Max plan active | After plan changes |
| Model routing (opus/sonnet/haiku) | THEORY | Specced for per-task model selection | Phase 1 build |
| Round state serialization | THEORY | Specced for JSON-based recovery | Phase 1 build |




---

## Dispatch Hooks (Session 100 — merged from addendum)

## Requirements

### Pre-Dispatch Hooks

| Req # | Requirement | Priority | Test |
|-------|-------------|----------|------|
| 100 | Round files MAY define `pre_dispatch` as a list of callables `(prompt: str, task: Task, config: RondoConfig) -> str`. Each callable receives the prompt and returns a (possibly modified) prompt. | MUST | Unit test |
| 101 | Pre-dispatch hooks run in order. Output of hook N is input to hook N+1. Final output is the dispatched prompt. | MUST | Chain test |
| 102 | If a pre-dispatch hook raises an exception, the task MUST be marked `error` with `ERR_HOOK_FAILED` and the hook name in `error_message`. The dispatch MUST NOT proceed. | MUST | Error test |
| 103 | Pre-dispatch hooks MUST be logged in the audit trail (STD-113) as a `HOOK_PRE` event with hook name and duration. | MUST | Audit test |
| 104 | Pre-dispatch hooks MAY be Python callables OR shell commands (string starting with `!`). Shell hooks receive prompt on stdin, return modified prompt on stdout. Exit code != 0 = error. | SHOULD | Shell hook test |
| 105 | Pre-dispatch hooks MUST NOT have access to API keys or provider credentials. They receive the prompt and task metadata only. | MUST | Security test |

### Post-Dispatch Hooks

| Req # | Requirement | Priority | Test |
|-------|-------------|----------|------|
| 110 | Round files MAY define `post_dispatch` as a list of callables `(result: TaskResult, usage: DispatchUsage) -> TaskResult`. Each callable receives the result and returns a (possibly modified) result. | MUST | Unit test |
| 111 | Post-dispatch hooks run in order AFTER finalize_dispatch (audit, sanitize, spool). Hooks see sanitized output — prevents accidental secret leakage through hook code. Audit OUTCOME records the provider's actual result, not hook-modified data. | MUST | Order test |
| 112 | If a post-dispatch hook raises, the ORIGINAL result (pre-hook) MUST be preserved and finalized. The hook failure is logged as WARNING. | MUST | Resilience test |
| 113 | Post-dispatch hooks MUST be logged in the audit trail as `HOOK_POST` events. | MUST | Audit test |
| 114 | Post-dispatch hooks receive sanitized output (sanitization already ran in finalize). Hooks MAY modify fields but MUST NOT re-inject sensitive data into `raw_output`. | MUST | Security test |

### Config-Level Hooks (Global)

| Req # | Requirement | Priority | Test |
|-------|-------------|----------|------|
| 120 | `~/.rondo/config.toml` MAY define `[hooks.pre_dispatch]` and `[hooks.post_dispatch]` as lists of shell commands that apply to ALL dispatches. | SHOULD | Config test |
| 121 | Round-file hooks run AFTER config-level hooks (COALESCE: config-global first, then round-specific). | MUST | Order test |
| 122 | `rondo hooks list` CLI command MUST show all active hooks (config + current round file). | SHOULD | CLI test |

---

## Data Model Changes

```python
@dataclass
class Task:
    # ... existing fields ...
    pre_dispatch: list[Callable | str] = field(default_factory=list)
    post_dispatch: list[Callable | str] = field(default_factory=list)
```

---

## Example Usage

```python
from rondo.engine import Round, Task

def redact_pii(prompt: str, task, config) -> str:
    """Remove email addresses from prompts before dispatch."""
    import re
    return re.sub(r'\b[\w.]+@[\w.]+\.\w+\b', '[REDACTED]', prompt)

def log_cost(result, usage):
    """Log cost after each dispatch."""
    if usage.cost_usd > 0.10:
        print(f"  HIGH COST: ${usage.cost_usd:.4f} for {result.task_name}")
    return result

def build_round():
    return Round(
        name="reviewed-dispatch",
        tasks=[
            Task(
                name="analyze",
                instruction="Review this code for security issues",
                pre_dispatch=[redact_pii],
                post_dispatch=[log_cost],
            ),
        ],
    )
```

---

## Architecture

```
  Round file defines hooks
         |
         v
  [pre_dispatch hooks] → prompt in → modified prompt out
         |
         v
  [dispatch to provider]
         |
         v
  [finalize_dispatch] → audit, sanitize, spool (existing pipeline)
         |
         v
  [post_dispatch hooks] → sanitized result in → modified result out
```

Hooks are lightweight — they don't change the dispatch architecture. They add
two extension points in the existing `_dispatch_with_safety_net` path.

---



---

## Usability — Self-Service Round Authoring (Session 93 — merged from addendum)

## Requirements

### DRY-RUN + PREFLIGHT (resolves REQ-103 Q3: OPEN → DECIDED)

| # | Requirement | Priority |
|---|-------------|----------|
| U-01 | `--dry-run` MUST skip preflight entirely — dry-run shows prompts only, no dispatch, no Claude binary needed | MUST |
| U-02 | `--dry-run` inside a Claude Code session (CLAUDECODE env set) MUST work — it only formats prompts, never spawns subprocess | MUST |
| U-03 | When `--dry-run` is active, output MUST show: task name, model, prompt text, context files, done_when criteria — enough to verify the round file is correct | MUST |
| U-04 | `--skip-preflight` flag MUST be available on `rondo run` and `rondo overnight` — logged as WARNING in audit, never silent | SHOULD |

**Decision (REQ-103 Q3):** `--skip-preflight` is allowed. It MUST log a warning.
`--dry-run` always skips preflight (no dispatch = no preflight needed).

### AI-HELP ENRICHMENT

| # | Requirement | Priority |
|---|-------------|----------|
| U-05 | `rondo --ai-help` MUST include the full Round dataclass schema: field names, types, defaults, descriptions | MUST |
| U-06 | `rondo --ai-help` MUST include the full Task dataclass schema: all fields including instruction, context_files, done_when, model, mode, auto_fn | MUST |
| U-07 | `rondo --ai-help` MUST include a minimal round file example (copy-paste ready) showing `from rondo.engine import Round, Task` and `def build_round() -> Round:` | MUST |
| U-08 | `rondo --ai-help` MUST include the Gate/GateResult schema for users writing gated rounds | SHOULD |
| U-09 | `rondo --ai-help` output MUST be valid JSON (parseable by AI agents via `--ai-help | jq`) | MUST |

### INIT SCAFFOLDING

| # | Requirement | Priority |
|---|-------------|----------|
| U-10 | `rondo init` MUST create a starter round file in the current directory | MUST |
| U-11 | `rondo init` MUST generate a valid Python file with `build_round() -> Round:` that runs with `rondo run` immediately (no edits needed for hello-world) | MUST |
| U-12 | `rondo init --name <name>` MUST set the round name and first task name from the flag | SHOULD |
| U-13 | Generated file MUST include comments explaining each field and common patterns | MUST |
| U-14 | `rondo init` MUST NOT overwrite an existing file — error with message | MUST |

### PROJECT/WORKDIR FLAG

| # | Requirement | Priority |
|---|-------------|----------|
| U-15 | `rondo run --project <path>` MUST set the working directory for all dispatched tasks to `<path>` | MUST |
| U-16 | `--project` path MUST be validated: directory exists, is readable | MUST |
| U-17 | When `--project` is set, `claude -p` subprocess MUST be spawned with `cwd=<path>` so tasks have access to that project's files and MCP servers | MUST |
| U-18 | `--project` MUST be available on `rondo run`, `rondo live`, and `rondo overnight` | MUST |
| U-19 | If `--project` is not set, default is CWD (current behavior, no change) | MUST |

### EXAMPLE ROUNDS (implements existing REQ-100-052/053/054)

| # | Requirement | Priority |
|---|-------------|----------|
| U-20 | `examples/rounds/round_hello.py` — 1 task, no gates, simplest possible round. Must run with `rondo run examples/rounds/round_hello.py --dry-run` | MUST |
| U-21 | `examples/round_file_check.py` — auto task (check file exists) + pre-gate (verify CWD). Demonstrates auto_fn and gate patterns | MUST |
| U-22 | `examples/round_multi_task.py` — 3 tasks with model hints, context_files, different done_when criteria. Parallel-ready | MUST |
| U-23 | `examples/round_overnight.py` — multi-phase overnight round file. Demonstrates build_phases() for `rondo overnight` | SHOULD |
| U-24 | All example files MUST be tested in the test suite (test_examples.py) — living docs, not dead code | MUST |
| U-25 | All example files MUST have header comments with usage: `rondo run examples/X.py --dry-run` | MUST |

### RESULT PARSING HELPERS

| # | Requirement | Priority |
|---|-------------|----------|
| U-26 | `TaskResult.extract_json()` MUST attempt to parse `raw_output` as JSON, returning dict or None | SHOULD |
| U-27 | `TaskResult.extract_code_blocks()` MUST extract fenced code blocks from `raw_output`, returning list of (language, content) tuples | SHOULD |
| U-28 | `TaskResult.extract_table()` MUST extract markdown tables from `raw_output`, returning list of dicts (header→value) | MAY |
| U-29 | Parsing helpers MUST be best-effort — never raise, return None/empty on failure | MUST |
| U-30 | Parsing helpers MUST NOT modify the original `raw_output` — they are read-only views | MUST |

### MCP DISPATCH STATUS (USH production feedback — Finding #165, #166)

| # | Requirement | Priority |
|---|-------------|----------|
| U-31 | `rondo_run_status` MUST return per-task progress: task name + status (done/running/pending) for each task in the round | MUST |
| U-32 | `rondo_run_status` MUST include completed task results inline (raw_output truncated to 2000 chars) so callers don't need to read separate files | MUST |

### INLINE TASK DISPATCH (USH production feedback — Finding #167)

| # | Requirement | Priority |
|---|-------------|----------|
| U-33 | `rondo_run` MUST accept an optional `prompt` parameter for one-off tasks without a round file. When `prompt` is set, Rondo creates an in-memory Round with one Task using the prompt as instruction | MUST |
| U-34 | Inline dispatch MUST accept `done_when` parameter (defaults to "Task completed. Return results.") | SHOULD |
| U-35 | Inline dispatch MUST return the same JSON structure as file-based dispatch | MUST |

### MCP DISPATCH OBSERVABILITY (USH production feedback)

| # | Requirement | Priority |
|---|-------------|----------|
| U-36 | Background dispatch SHOULD track running cost (sum of completed task costs) in status response | SHOULD |
| U-37 | `dispatched_at` field in audit OUTCOME records MUST be populated from the INTENT record timestamp (Finding #162) | MUST |
| U-38 | `round_name` MUST flow from Round.name through dispatch to audit records (Finding #163) | MUST |
| U-39 | `max_budget` documentation MUST note that budget cap only works with `auth: "api"`, not `auth: "max"` (Finding #164) | MUST |

### MCP STATUS ENRICHMENT (RONDO-44)

| # | Requirement | Priority |
|---|-------------|----------|
| U-40 | `rondo_run_file()` result MUST include `done_count`, `error_count`, `pending_count` integer fields — callers see progress at a glance without parsing task array | MUST |
| U-41 | Each task in the result `tasks` array MUST include `error_code` and `error_message` fields (empty string if no error) | MUST |
| U-42 | Background dispatch status (`rondo_run_status`) MUST include `done_count` and `error_count` when tasks complete | SHOULD |
| U-43 | Python API SHOULD support `on_task_complete` callback on `dispatch_task()` — called after each task finishes with the `TaskResult` | SHOULD |
| U-44 | Polling `rondo_run_status` MUST be lightweight: no file reads, no DB queries, no AI calls — in-memory dict lookup only | MUST |
| U-45 | `rondo_run_status(brief=True)` MUST return only `{status, done_count, error_count, pending_count}` — minimal tokens for polling loops | MUST |
| U-46 | `rondo://help` resource and `--ai-help` MUST document the polling pattern: brief=True for cheap polling, brief=False for full results when done | MUST |
| U-47 | Background dispatch SHOULD use MCP `report_progress` to push per-task completion to client without polling — capture Context.session before tool returns, use in background thread | SHOULD |
| U-48 | When progress notifications are available, final status SHOULD be pushed as a completion notification so client never needs to poll | SHOULD |
| U-49 | Progress notifications MUST be best-effort — if push fails, polling via `rondo_run_status` remains the fallback (MCP spec: notifications can be dropped) | MUST |
| U-50 | `rondo_run_status(heartbeat=True)` MUST return ultra-compact response: single-letter keys `{"s":"w","d":2,"e":0,"p":1}` (~10 tokens). Status codes: `w`=working, `d`=done, `e`=error. For tight polling loops. | SHOULD |
| U-51 | `rondo://help` resource MUST document the 3 polling tiers: heartbeat (~10 tokens), brief (~40 tokens), full (~300+ tokens) with guidance on when to use each | MUST |

### CURSOR REVIEW FIXES (Session 93 — Multi-AI Review)

| # | Requirement | Priority |
|---|-------------|----------|
| U-52 | `_finalize_dispatch` MUST pass `error_code` from TaskResult to `record_outcome` — audit JSONL must capture error types for failure analytics | MUST |
| U-53 | MCP tool functions (`rondo_metrics`, `rondo_health`, `rondo_audit_summary`, `rondo_spool_consume`) MUST honor `RONDO_TEST_DIR` env var for path resolution — test/production path parity | MUST |
| U-54 | Background dispatch with `prompt=` (inline) MUST pre-populate `task_names=["inline-task"]` in status — callers see pending rows before completion | MUST |
| U-55 | `rondo_dispatch_info` command list MUST be derived from `build_parser()` or a shared constant — no hardcoded list that drifts from CLI | MUST |

---

## Gap Check: Cross-Spec Impact

| This Addendum | Affects | How |
|--------------|---------|-----|
| U-01/U-02 (dry-run skip preflight) | REQ-103 Q3 | **Resolves** — Q3 answered: yes, skip allowed with warning |
| U-04 (--skip-preflight) | REQ-103 | **New flag** — add to preflight spec |
| U-05–U-09 (--ai-help) | IFS-100 | **New interface** — ai-help is a machine-readable API surface |
| U-15–U-19 (--project) | STD-109 | **New config field** — add to COALESCE chain |
| U-20–U-25 (examples) | REQ-100-052/053/054 | **Implements** existing reqs — no spec change needed |
| U-26–U-30 (result helpers) | STD-100 | **Extends** data standards — new methods on TaskResult |
| U-31/U-32 (per-task status) | IFS-104 | **Extends** MCP server — richer status response |
| U-33–U-35 (inline dispatch) | IFS-104 | **New interface** — prompt-based dispatch without files |
| U-37/U-38 (audit fixes) | STD-113 | **Bug fix** — dispatched_at + round_name propagation |
| U-39 (budget docs) | STD-109 | **Documentation** — max_budget limitation on Max plan |

## Cross-Spec Updates Required

| Spec | Section | Update |
|------|---------|--------|
| REQ-103 | §11 Open Questions | Q3 → DECIDED (U-01, U-04) |
| REQ-103 | Requirements table | Add req 027: `--skip-preflight` flag |
| IFS-100 | Interface definition | Add `--ai-help` as formal interface |
| IFS-104 | MCP tools | U-31/U-32 per-task status, U-33–U-35 inline dispatch |
| STD-109 | Configuration table | Add `project` field + `max_budget` limitation note |
| STD-113 | Audit trail | U-37 dispatched_at propagation, U-38 round_name flow |
| STD-100 | Data Model | Add extract methods to TaskResult |
| REQ-100 | Package layout | Add `examples/` directory with 4 files |

---

## Verification Matrix

| Req | Test Type | Test Description |
|-----|-----------|-----------------|
| U-01 | Unit | `--dry-run` with no claude binary works |
| U-02 | Unit | `--dry-run` with CLAUDECODE env set works |
| U-03 | Unit | Dry-run output contains task name, prompt, model |
| U-05 | Unit | `--ai-help` JSON contains Round schema |
| U-06 | Unit | `--ai-help` JSON contains Task schema with all fields |
| U-07 | Unit | `--ai-help` JSON contains example round file |
| U-10 | Unit | `rondo init` creates valid file |
| U-11 | E2E | Generated file runs with `rondo run --dry-run` |
| U-15 | Unit | `--project` sets subprocess CWD |
| U-20–U-23 | E2E | Each example runs with `--dry-run` |
| U-24 | Integration | test_examples.py imports and validates all examples |
| U-26 | Unit | extract_json() parses valid JSON from output |
| U-29 | Unit | extract_json() returns None on invalid output |
| U-31 | Unit | rondo_run_status returns per-task name + status |
| U-32 | Unit | rondo_run_status includes raw_output in completed tasks |
| U-33 | Unit | rondo_run(prompt="...") creates in-memory round and dispatches |
| U-35 | Unit | Inline dispatch returns same JSON as file-based |
| U-37 | Unit | Audit OUTCOME has dispatched_at from INTENT |
| U-38 | Unit | Audit OUTCOME has round_name from Round.name |
| U-40 | Unit | Result JSON has done_count, error_count, pending_count integers |
| U-41 | Unit | Task entries have error_code and error_message fields |
| U-44 | Unit | rondo_run_status returns from in-memory dict (no I/O) |

---

## Build Order

| Phase | Reqs | Why This Order |
|-------|------|---------------|
| 1 | U-01, U-02 | Unblocks testing everything else from inside CC |
| 2 | U-05–U-09 | Unblocks AI agents discovering the API |
| 3 | U-10–U-14 | Unblocks first-time users creating round files |
| 4 | U-20–U-25 | Living examples for learning and testing |
| 5 | U-15–U-19 | --project flag for cross-repo dispatching |
| 6 | U-26–U-30 | Result helpers for structured consumption |
| 7 | U-03, U-04 | Polish: better dry-run output, --skip-preflight |
| 8 | U-31, U-32 | Per-task status + results in status response (RONDO-42) |
| 9 | U-33–U-35 | Inline task dispatch without round file (RONDO-43) |
| 10 | U-37, U-38 | Audit bug fixes: dispatched_at + round_name |
| 11 | U-36, U-39 | Polish: running cost, budget doc |
| 12 | U-40–U-44 | Status enrichment: counts, error levels, Python callback (RONDO-44) |

---

### RETRY FAILED TASKS (RONDO-62)

| # | Requirement | Priority |
|---|-------------|----------|
| U-56 | `rondo_retry(dispatch_id)` MCP tool MUST re-dispatch only failed/error tasks from a previous dispatch | MUST |
| U-57 | Retry MUST use the same round file and config as the original dispatch | MUST |
| U-58 | Retry result MUST include which tasks were re-run and which were skipped (already done) | MUST |

### DIFF — WHAT'S NEW (RONDO-63)

| # | Requirement | Priority |
|---|-------------|----------|
| U-59 | `rondo_diff(current, previous)` MUST compare two dispatch results and report new items | MUST |
| U-60 | Diff output MUST show: new items, removed items, unchanged count | MUST |
| U-61 | `rondo_diff` MUST be available as MCP tool for AI consumption | MUST |

---

## USH Production Feedback (Session 93 — First Real Use)

**Source:** USH Claude session, 4-task parallel dispatch via MCP, 2026-03-30.

### What Worked (Validated)
- MCP dispatch from inside CC (no separate terminal)
- dry_run=true default (safe first)
- background=true with polling
- 4 parallel workers (5 min vs 20+ min sequential)
- Structured JSON results
- Auto audit trail
- Results persisted to files

### Feature Requests (New Requirements)

| # | Request | Finding | Sprint |
|---|---------|---------|--------|
| U-31 | Per-task progress in `rondo_run_status` (not just "running") | #165 | RONDO-42 |
| U-32 | Task results returned IN the status response (no file reading needed) | #166 | RONDO-42 |
| U-33 | Inline task dispatch: `rondo_run(prompt="...")` without round file | #167 | RONDO-43 |
| U-34 | Running cost shown during background dispatch | — | Future |
| U-35 | Completion notification (push result vs polling) | — | Future (needs MCP notification spec) |
| U-36 | `--project` inherits target project's MCP servers | — | Future (CC architecture limitation) |

### Bugs Found

| # | Bug | Finding | Severity |
|---|-----|---------|----------|
| B-1 | `dispatched_at` empty in audit OUTCOME | #162 | Medium |
| B-2 | `round_name` not flowing to audit | #163 | Low |
| B-3 | `max_budget` misleading on Max plan (no-op) | #164 | Medium |

---

## Change Log

| Version | Date | Changes |
|---------|------|---------|
| 0.1 | 2026-03-30 | Initial — 30 requirements across 6 features. Resolves REQ-103 Q3. Implements REQ-100-052/053/054. |
| 0.3 | 2026-03-30 | Status enrichment: +5 reqs (U-40 to U-44). Counts, error levels, Python callback. Phase 12. RONDO-44. |
| 0.2 | 2026-03-30 | USH production feedback: +9 requirements (U-31 to U-39) in proper tables. 3 categories: MCP status (U-31/32), inline dispatch (U-33-35), observability fixes (U-36-39). 6 verification matrix entries. 4 new build phases (8-11). 6 findings (#162-167). Cross-spec updates for IFS-104, STD-113, STD-109. |

## 35. Change History

| Version | Date | What Changed |
|---------|------|-------------|
| 0.1 | 2026-03-13 | Initial draft from spike learnings (Session 75) |
| 0.2 | 2026-03-13 | Split from monolithic spec. Rondo-REQ-100=core, Rondo-REQ-101=automation. Removed OB/ACE references. Own foundations. |
| 0.3 | 2026-03-14 | Added Data Boundary section: RoundResult, DispatchUsage, result file structure. Answered Q1 (no DB), Q2 (rate_limit_event), Q3 (configurable binary). |
| 0.4 | 2026-03-14 | Deep review fixes: formal Task/Gate/GateResult/Round dataclasses, aligned status vocabulary (done/blocked/partial/error/skipped) with CORE-IFS-001 reqs 53-54 (status vocabulary), added description field to Task, added model hint to Task, RoundResult.status uses same vocabulary, duration units clarified (ms from stream-json, sec for wall-clock) |
| 0.5 | 2026-03-14 | Added reqs 34-44: package structure, CLI entry point (run/overnight/report/dry-run subcommands), dynamic round loading, auto sequential/parallel detection, living example rounds (3 examples as test fixtures), library usage pattern, call chain diagram |
| 0.6 | 2026-03-14 | Deep review v2 fixes: added reqs 45-46 (run_round contract, RoundResult.status calculation), gate calling convention documented, DispatchUsage defaults for rate limit fields, dry-run changed from subcommand to --dry-run flag on run, test_cli.py + test_examples.py added to package layout |
| 0.7 | 2026-03-14 | Added reqs 47-49: `--permission-mode` dispatch flag — controls Claude Code tool access prompts in non-interactive subprocess dispatch |
| 0.8 | 2026-03-14 | Defense in depth: validate_task() + validate_round() pre-flight in engine.py, VALID_MODELS fail-fast in dispatch, CLI exit code contract (0/1/2/130), validate_config() at CLI boundary, KeyboardInterrupt + catch-all exception handling. Cross-ref CORE-IFS-001 reqs 53-54 (status vocabulary). |
| 0.9 | 2026-03-23 | Gemini R7 findings: +4 reqs (074-077, renumbered from 057-060) Task Safety — task_timeout_sec, round_timeout_sec, Popen timeout enforcement, timeout_exceeded error status. Total: 60 reqs. |
| 1.0 | 2026-03-25 | 4-AI cross-review fixes (OpenAI/Gemini/Mistral/Grok): Replaced `running` with `in_progress` throughout (CORE-STD-001 alignment). Filled §4 Architecture/Design (layer diagram, component interactions, dispatch detail, tool_mode vs permission_mode). Filled §5 Data Model (dataclass inventory). Filled §6 Data Boundary (canonical data path, config file locations, clarified Rondo-has-no-DB vs CORE-STD-022 indirect relationship). Filled §13 Integration Points. Added §12 Tactical Solutions (TAC-RON-001, TAC-RON-002). Renumbered Live Mode reqs 47-56 to 061-070 in proper table format. Clarified timeout coordination with Rondo-REQ-101 watchdog (req 057). Added CORE-STD-001 to dependencies. Annotated parallel.py/overnight.py/report.py as Rondo-REQ-101 scope in package layout. Clarified "zero external dependencies" applies to core engine, not consumer scripts. Total: 70 reqs. |
| 1.1 | 2026-03-25 | Grok cross-review fixes: (C1) Task state machine diagram now shows `pending` as explicit initial state with forward-only transition restrictions. Added D9 (7-state vocabulary DEC). (C2) Added reqs 071-073: --bare flag detection, flag precedence (stream-json mandatory, --bare additive), Caliber bypass warning. (M4) §6 Data Boundary clarified two distinct storage paths (results_dir vs spool) with owner/purpose/lifecycle table. (M7) Added D10 (dataclass timestamp domain semantics DEC). (M8) Live mode clarified: no subprocess dispatch, no ThreadPoolExecutor, no spool — in-process tool calls only. Total: 73 reqs. |
| 1.3 | 2026-04-09 | Merged dispatch hooks + usability addendums. |
| 1.3a | 2026-04-09 | Merged dispatch hooks addendum (reqs 100-122) + usability addendum (U-1 to U-36). Eliminated addendum files — one spec per feature. Session 100. |
| 1.2 | 2026-04-05 | FIX-674: ErrorPayload dataclass on TaskResult — structured error recovery guidance (code, message, recovery, transient, layer, provider). 12 error codes mapped to recovery messages. Report renders recovery in action items, notify includes recovery in failure messages. FIX-680: TOML type validation at load (wrong types warn + fallback to default). FIX-682: 4 bad-config E2E tests. |
