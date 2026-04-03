# Rondo

**Define AI tasks in Python. Send them to any AI — Claude, Gemini, Grok, Mistral. Get structured results back.**

Rondo is a multi-provider AI dispatch engine. Write round definitions in plain
Python — tasks, gates, config — and Rondo handles routing to 7 providers,
parallel dispatch, error recovery, cost tracking, and overnight scheduling.
Use it from CLI, MCP (Claude Code), or Python import.

```python
from rondo import Round, Task, run_round

result = run_round(Round(
    name="hello",
    tasks=[
        Task(
            name="greet",
            instruction="Say hello and confirm you received this prompt.",
            done_when="Response contains a greeting",
        ),
    ],
))

print(f"{result.status}: {result.summary}")
```

---

## 5 Minutes to Your First Review

```bash
## 1. Install
cd rondo && uv tool install --editable .

## 2. Dry-run an example (no AI calls, free)
rondo run examples/round_hello.py --dry-run

## 3. Run it for real (Claude, ~$0.01)
rondo run examples/round_hello.py

## 4. Try a cloud provider (Gemini, ~$0.001)
rondo run examples/round_hello.py --model gemini:flash

## 5. Multi-provider review (Gemini + Grok, ~$0.005)
## (From Claude Code — via MCP)
## rondo_multi_review(prompt="Review this code for bugs", providers='["gemini:flash", "grok:grok-3"]')
```

That's it. `--dry-run` shows prompts without calling AI. Remove it to dispatch for real.

---

## What Rondo Does

| You write | Rondo handles |
|-----------|---------------|
| Tasks with instructions | Dispatch to Claude, Gemini, Grok, Mistral, or Ollama |
| Gates (pre/post checks) | Blocking vs advisory gate logic |
| Config (model, workers) | COALESCE resolution (CLI > config > defaults) |
| Round definitions | Sequential or parallel execution |
| Overnight phase lists | Multi-phase scheduling with usage gating |

**Key features:**

- **Two task types** — Interactive (Claude does it) and Auto (Python callable does it)
- **Gates** — Pre-gates block execution, post-gates validate results. Blocking or advisory.
- **Parallel dispatch** — ThreadPoolExecutor with configurable workers and throttling
- **Error resilience** — 10 error codes, SIGTERM-first kill, task isolation (one failure doesn't crash others)
- **Usage tracking** — Cost, tokens, rate limits, overage detection per task
- **Overnight automation** — Multi-phase scheduler with usage gating (continue/pause/stop on overage)
- **Morning reports** — Markdown report with health indicators, action items, usage summary
- **Zero-config** — Works out of the box. Optional `rondo.toml` for overrides.

---

## How It Works: The Unix Pipeline

Rondo follows the Unix philosophy: **do one thing well, compose with pipes.**

```
grep does one thing:    match patterns
sort does one thing:    order lines
rondo does one thing:   run Claude tasks and give you JSON back
```

The power isn't in any single tool — it's in how you chain them.

### The Pipeline in 5 Steps

```
   Step 1          Step 2          Step 3          Step 4          Step 5
   DEFINE       →  RUN          →  CHECK        →  RUN NEXT     →  REPORT
   (you write      (rondo           (read the       (feed results    (rondo
    Python)         runs it)         JSON)            into next)       summarizes)
       │               │               │                │               │
       ▼               ▼               ▼                ▼               ▼
   my_round.py    task-*.json     pass/fail?      task-*.json     morning.md
```

Each step reads from disk. Each step writes to disk. Each step knows
nothing about the others. Like Unix pipes — but with JSON files instead
of text streams.

### Step by Step

**Step 1: Define** — Write a Python file with your tasks.

```python
# -- scan.py: find what needs reviewing
from rondo import Round, Task

def build_round() -> Round:
    return Round(
        name="scan",
        tasks=[
            Task(
                name="find-issues",
                instruction="List all TODO and FIXME comments in src/",
                context_files=["src/"],
                done_when="Table of file, line number, comment text",
            ),
        ],
    )
```

**Step 2: Run** — Rondo sends it to Claude, saves JSON to disk.

```bash
rondo run scan.py
# → reports/rondo-results/task-find-issues.json
```

**Step 3: Check** — Read the JSON. Decide what's next.

```json
{
  "task_name": "find-issues",
  "status": "done",
  "parsed_result": {
    "status": "done",
    "confidence": 0.95,
    "result": "Found 12 TODOs across 4 files"
  }
}
```

**Step 4: Chain** — Feed results into the next round.

```python
# -- fix.py: fix what the scan found
import json
from pathlib import Path
from rondo import Round, Task

def build_round() -> Round:
    # -- read previous step's output
    scan = json.loads(Path("reports/rondo-results/task-find-issues.json").read_text())
    findings = scan["parsed_result"]["result"]

    return Round(
        name="fix",
        tasks=[
            Task(
                name="resolve-todos",
                instruction=f"Previous scan found these issues:\n{findings}\n\n"
                            "For each TODO: resolve it or convert to a tracked issue.",
                context_files=["src/"],
                done_when="Each TODO resolved or converted to issue",
            ),
        ],
    )
```

```bash
rondo run fix.py
# → reports/rondo-results/task-resolve-todos.json
```

**Step 5: Report** — Rondo summarizes everything.

```bash
rondo overnight phases.py    # runs all steps + generates morning report
# → reports/rondo-morning-20260315.md
```

### Why This Matters

```
Without Rondo:
  1. Open Claude chat
  2. Type prompt
  3. Wait
  4. Copy result
  5. Type next prompt referencing what you copied
  6. Repeat 50 times
  7. Claude compacts — you start over

With Rondo:
  1. Write Python (once)
  2. rondo run
  3. JSON on disk (forever)
  4. Chain into next step
  5. Go to sleep
```

The results are JSON files on disk. They don't vanish on compaction.
They don't scroll off screen. They're **data** — grep them, pipe them,
feed them into the next round. Like Unix intended.

### The Unix Comparison

| Unix | Rondo | What it does |
|------|-------|-------------|
| `echo "hello"` | `Task(instruction="Say hello")` | Single command |
| `bash script.sh` | `rondo run round.py` | Run a batch |
| `stdout > file` | `→ task-*.json` | Output to disk |
| `cat file \| next` | Next round reads JSON | Chain steps |
| `cron` | `rondo overnight` | Run while you sleep |
| `$?` exit code | `status: done/error` | Did it work? |
| `make` | Round with gates | Check before/after |
| `tee` | Every result auto-saved | Nothing lost |

---

## Install

Rondo requires Python 3.12+ and Claude Code (the `claude` CLI).

```bash
# -- From the rondo directory
pip install -e .

# -- Verify
rondo --help
```

---

## Quickstart

### 1. Write a round definition

Create a file `my_round.py`:

```python
from rondo import Round, Task

def build_round() -> Round:
    return Round(
        name="hello",
        tasks=[
            Task(
                name="Say hello",
                instruction="Say 'Hello from Rondo!' and confirm you received this prompt.",
                done_when="Response contains 'Hello from Rondo'",
            ),
        ],
    )
```

### 2. Run it

```bash
rondo run my_round.py
```

### 3. See results

```
done: 1/1 tasks done
```

Task results are saved as JSON in `reports/rondo-results/`.

---

## Core Concepts

### Round

A **Round** is a collection of tasks with optional pre/post gates. It's the
unit of execution — you define a round, then run it.

```python
Round(
    name="my-round",
    pre_gates=[...],    # -- checked before tasks run
    tasks=[...],        # -- the work
    post_gates=[...],   # -- checked after tasks complete
)
```

### Task

A **Task** is a single unit of AI work. There are two kinds:

**Interactive task** — sends a prompt to Claude via the three-field contract:

```python
Task(
    name="Review code",
    instruction="Review this file for bugs.",      # -- Do: what Claude should do
    context_files=["src/main.py"],                 # -- Read: files for context
    done_when="Bug report with severity ratings",  # -- Done: completion criteria
    model="sonnet",                                # -- optional model hint
)
```

**Auto task** — runs a Python callable directly (no Claude needed):

```python
Task(
    name="Count files",
    auto_fn=lambda: (True, f"{len(list(Path('.').rglob('*.py')))} Python files"),
)
```

Auto functions return `(bool, str)` — pass/fail and a detail message.

### Gate

A **Gate** is a boolean check that guards round entry or exit:

```python
Gate(
    name="Tests pass",
    check_fn=lambda: (True, "All tests green"),
    blocking=True,   # -- True = blocks execution; False = advisory warning
)
```

**Pre-gates** run before tasks. If a blocking pre-gate fails, all tasks are skipped.
**Post-gates** run after tasks. They validate results but don't undo work.

Gate functions return `(bool, str)` — pass/fail and a detail message. Gates that
need external context (subprocess, files, etc.) capture it via closure.

### Config (COALESCE)

Every setting resolves via **COALESCE: CLI flag > config file > default**.

```
rondo run my_round.py --model opus --workers 8
                       ↑ CLI wins     ↑ CLI wins over rondo.toml and defaults
```

If you don't set anything, defaults work fine (zero-config mode).

---

## Task Three-Field Contract

Every interactive task uses the **Do / Read / Done** contract:

| Field | Purpose | Required |
|-------|---------|----------|
| `instruction` | What Claude should do | Yes |
| `context_files` | Files Claude should read first | No |
| `done_when` | How to know the task is complete | Yes |

Claude receives a structured prompt built from these fields, and responds
with a JSON block containing `status`, `confidence`, `result`, and optionally
`question` (if blocked).

---

## CLI Reference

### `rondo run <file>`

Execute a round definition file. The file must define a `build_round()` function
that returns a `Round`.

```bash
rondo run my_round.py
rondo run my_round.py --workers 8        # parallel dispatch
rondo run my_round.py --model opus       # override model for all tasks
rondo run my_round.py --dry-run          # show prompts without invoking Claude
rondo run my_round.py --verbose          # detailed per-task output
rondo run my_round.py --config path.toml # explicit config file
```

### `rondo overnight <file>`

Run multi-phase overnight automation. The file must define a `build_phases()`
function that returns a `list[Round]`.

```bash
rondo overnight phases.py
rondo overnight phases.py --mode minimal    # run subset of phases
rondo overnight phases.py --on-overage stop # stop if hitting usage overage
```

### `rondo report <results_dir>`

Generate a report from saved results (future feature).

### Common Flags

| Flag | What it does | Default |
|------|-------------|---------|
| `--workers N` | Parallel worker count | 4 |
| `--model MODEL` | Model override (sonnet/opus/haiku) | sonnet |
| `--auth MODE` | Auth mode (max/api) | max |
| `--timeout SECS` | Task timeout in seconds | 300 |
| `--effort LEVEL` | Effort level (low/medium/high/max) | high |
| `--on-overage ACT` | Overage action (continue/pause/stop) | continue |
| `--permission-mode MODE` | Claude permission mode | auto |
| `--config PATH` | Path to rondo.toml | auto-detect |
| `--dry-run` | Show prompts, don't invoke Claude | false |
| `--verbose` | Detailed output | false |

---

## Configuration

Create a `rondo.toml` in your project root (optional — all settings have defaults):

```toml
# -- Dispatch
auth = "max"                    # "max" (subscription) or "api" (pay-per-token)
default_model = "sonnet"        # opus, sonnet, haiku, opus[1m], sonnet[1m]
effort = "high"                 # low, medium, high, max
output_format = "stream-json"   # text, json, stream-json
claude_binary = "claude"        # path to claude binary
task_timeout_sec = 300          # kill task after N seconds
permission_mode = "auto"        # default, acceptEdits, plan, auto, bypassPermissions

# -- Parallel execution
workers = 4                     # max concurrent dispatches
throttle_sec = 2.0              # delay between task launches

# -- Self-healing
watchdog_timeout_sec = 60       # no-output timeout before kill
rate_limit_backoff_sec = 60     # backoff after rate limit hit
on_overage = "continue"         # continue, pause, stop

# -- Output
results_dir = "reports/rondo-results"
report_dir = "reports"
```

**Resolution order:** CLI flag > `rondo.toml` > built-in default. If a flag isn't
set on the command line and isn't in the config file, the default applies.

---

## Permission Modes

When Rondo dispatches tasks via `claude -p`, Claude Code may prompt for tool
permissions (file edits, bash commands, etc.). In non-interactive overnight runs,
these prompts hang forever. The `--permission-mode` flag controls this behavior.

| Mode | Behavior | When to use |
|------|----------|-------------|
| `auto` | Claude decides based on context | Default — good for interactive use |
| `default` | Prompt for every tool permission | Maximum safety, manual approval |
| `acceptEdits` | Auto-allow file edits, prompt for others | Code review / generation tasks |
| `plan` | Plan-only mode, no tool execution | Dry-run-like analysis tasks |
| `bypassPermissions` | Allow all tools without prompting | Overnight automation (trusted rounds) |

**COALESCE resolution:** `--permission-mode` flag > `permission_mode` in `rondo.toml` > default `"auto"`.

```bash
# -- Overnight: bypass prompts (tasks are pre-reviewed)
rondo overnight phases.py --permission-mode bypassPermissions

# -- Code review: allow edits but prompt for bash
rondo run review.py --permission-mode acceptEdits
```

**In config:**
```toml
permission_mode = "bypassPermissions"  # recommended for overnight automation
```

---

## Python API

For programmatic use (scripts, CI, other tools):

```python
from rondo import Round, Task, Gate, run_round, RondoConfig

# -- Build a round
my_round = Round(
    name="example",
    pre_gates=[Gate("check", check_fn=lambda: (True, "ok"))],
    tasks=[
        Task(name="work", instruction="Do the thing", done_when="Thing is done"),
    ],
)

# -- Run with custom config
config = RondoConfig(workers=2, default_model="haiku", dry_run=True)
result = run_round(my_round, config=config)

# -- Inspect results
print(result.status)       # "done", "partial", "error", "skipped"
print(result.summary)      # "1/1 tasks done"
for tr in result.task_results:
    print(f"  {tr.task_name}: {tr.status}")
    if tr.parsed_result:
        print(f"    confidence: {tr.parsed_result.get('confidence')}")
        print(f"    result: {tr.parsed_result.get('result')}")
```

### Key Classes

| Class | What it is |
|-------|-----------|
| `Round` | Collection of tasks + pre/post gates |
| `Task` | Single unit of work (interactive or auto) |
| `Gate` | Boolean check (blocking or advisory) |
| `RondoConfig` | Immutable config (frozen dataclass) |
| `TaskResult` | Outcome of one dispatched task |
| `RoundResult` | Outcome of a full round execution |
| `DispatchUsage` | Token/cost/rate-limit metadata per task |
| `OvernightResult` | Aggregated results from overnight run |
| `EventLog` | Rolling 100-entry event log for overnight |

### Key Functions

| Function | What it does |
|----------|-------------|
| `run_round(round, config)` | Execute a round (auto-detects sequential vs parallel) |
| `run_parallel(round, config)` | Force parallel execution |
| `dispatch_task(task, config)` | Dispatch a single task to Claude |
| `run_overnight(phases, config)` | Run multi-phase overnight automation |
| `load_config(...)` | Load config with COALESCE resolution |
| `validate_config(config)` | Validate config, return list of errors |
| `detect_conflicts(results)` | Find files modified by multiple parallel tasks |
| `generate_report(result)` | Generate morning report markdown |
| `save_report(result, config)` | Save report to dated file |

---

## Examples

Rondo ships with 8 working examples in `examples/`. These are real round definitions
you can run — they also serve as the integration test suite.

### Spec Examples (minimal, teach one concept each)

| File | What it teaches |
|------|----------------|
| `round_hello.py` | Simplest possible round — 1 task, no gates |
| `round_file_check.py` | Auto task + gate + interactive task + model hint |
| `round_multi_task.py` | 3 tasks, pre/post gates, parameterized `build_round(target_dir)` |

### Pipeline Demo (Unix-style chaining)

| File | Pattern |
|------|---------|
| `demo_pipeline.py` | **4-step pipeline**: scan → review → fix → verify. Each step reads the previous step's JSON. Run one at a time or all via overnight. |

```bash
# -- Run the full pipeline (all 4 steps):
rondo overnight examples/demo_pipeline.py

# -- Or run step by step (like Unix pipes):
rondo run examples/demo_pipeline.py              # Step 1: scan
# → read task-find-issues.json, feed into Step 2
rondo run examples/demo_pipeline.py              # Step 2: review (reads Step 1 JSON)
# → and so on...

# -- Dry run to see what Claude would receive:
rondo run examples/demo_pipeline.py --dry-run
```

### Practical Examples (real-world patterns)

| File | Pattern |
|------|---------|
| `round_code_review.py` | Subprocess gate (git diff) + Claude reviews staged changes |
| `round_test_generator.py` | Auto-discovery of untested modules + Claude writes test stubs |
| `round_doc_sweep.py` | Parallel doc improvement across multiple files |
| `round_refactor_audit.py` | Blocking + non-blocking gates, post-gate validation |
| `phases_overnight.py` | Multi-phase overnight: auto checks → haiku lint → sonnet deep review |

### Running Examples

```bash
# -- Simple round
rondo run examples/round_hello.py

# -- With parallel workers
rondo run examples/round_doc_sweep.py --workers 4

# -- Dry run (see prompts without invoking Claude)
rondo run examples/round_code_review.py --dry-run

# -- Parameterized
python -c "
from examples.round_multi_task import build_round
r = build_round(target_dir='src/')
print(f'{r.name}: {len(r.tasks)} tasks')
"

# -- Overnight phases
rondo overnight examples/phases_overnight.py --mode standard
```

---

## Error Handling

Rondo follows the **STD-001 error resilience** spec: every failure is caught,
classified, and reported — never crashes the framework.

### Error Codes

| Code | Meaning |
|------|---------|
| `ERR_TIMEOUT` | Task exceeded `task_timeout_sec` |
| `ERR_SUBPROCESS` | Claude process failed (non-zero exit) |
| `ERR_AUTH` | Authentication failure (bad API key, low balance) |
| `ERR_NESTED_SESSION` | Tried to launch Claude inside another Claude session |
| `ERR_RATE_LIMIT` | Rate limited by the API |
| `ERR_EMPTY_OUTPUT` | Claude returned empty stdout |
| `ERR_MALFORMED_JSON` | Claude's output didn't contain valid task JSON |
| `ERR_WATCHDOG_TIMEOUT` | No output for `watchdog_timeout_sec` |
| `ERR_INTERNAL` | Unexpected framework error (safety net) |

### Task Isolation

One task failing never crashes other tasks. In parallel mode, each task runs
in its own thread with no shared mutable state.

### Kill Sequence

Hung tasks get SIGTERM first (graceful), then SIGKILL after 5 seconds if
the process doesn't exit. This is safer than raw `kill -9`.

---

## Round Status Values

| Status | Meaning |
|--------|---------|
| `done` | All tasks completed successfully |
| `partial` | Some tasks done, some failed |
| `error` | All tasks failed (none succeeded) |
| `skipped` | Pre-gate blocked execution, or no tasks in round |
| `blocked` | Task couldn't proceed (needs human input) |
| `pending` | Not yet started |
| `running` | Currently executing |

---

## Architecture

```
CLI (cli.py)
  │
  ▼
Runner (runner.py)  ←── primary entry point: run_round()
  │                      auto-detects sequential vs parallel
  ├──▶ Sequential         workers == 1
  └──▶ Parallel (parallel.py)   workers > 1 → ThreadPoolExecutor
         │
         ▼
    Dispatch (dispatch.py)  ←── sends tasks to Claude via subprocess
         │
         ▼
    Engine (engine.py)  ←── data model: Round, Task, Gate, Result
    Config (config.py)  ←── TOML loading, COALESCE, validation
```

**Import layering (strict, no circular deps):**

| Layer | Module | Imports from |
|-------|--------|-------------|
| L0 | engine.py | nothing (pure data model) |
| L0 | config.py | nothing (pure config) |
| L1 | dispatch.py | engine + config |
| L2 | runner.py | engine + config + dispatch |
| L2 | parallel.py | engine + config + dispatch |
| L3 | overnight.py | engine + config + runner |
| Top | cli.py | everything |
| Top | report.py | engine + config + overnight |

---

## Project Structure

```
rondo/
├── src/rondo/           # source (10 modules, ~2,300 LOC)
│   ├── __init__.py      # public API surface
│   ├── __main__.py      # python -m rondo
│   ├── engine.py        # data model + state machine
│   ├── config.py        # TOML loading + COALESCE
│   ├── dispatch.py      # claude -p subprocess dispatch
│   ├── runner.py        # sequential orchestration
│   ├── parallel.py      # ThreadPoolExecutor dispatch
│   ├── overnight.py     # multi-phase scheduler
│   ├── report.py        # morning report generator
│   └── cli.py           # command-line interface
├── tests/               # 480 tests (~4,700 LOC)
├── examples/            # 8 working examples (~400 LOC)
├── specs/               # 7 requirement/standard specs
├── rondo.toml           # example config (all defaults)
└── pyproject.toml       # PEP 621 packaging
```

---

## Quality

| Metric | Value |
|--------|-------|
| Pylint score | 10.00/10 |
| Mypy | strict, 0 errors |
| Ruff lint | clean |
| Ruff format | clean |
| Bandit security | 0 medium/high (3 low — subprocess by design) |
| Tests | 480 |
| Test:code ratio | 2.0:1 |
| Type coverage | 100% (every function annotated) |
| Docstring coverage | 100% (every public function/class) |

---

## License

MIT
