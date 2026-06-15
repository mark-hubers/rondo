# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Rondo engine — data model, state machine, gate execution, serialization.

Rondo-REQ-100 reqs 1-11, 23, 29, 31, 46.
All dataclasses live here. Other modules (dispatch, runner, parallel)
import types from engine — never the other way around.

Status vocabulary (shared with Rondo-STD-108):
    done, blocked, partial, error, skipped  (terminal)
    pending, in_progress                    (non-terminal)
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# -- Status constants (Rondo-REQ-100 req 8)
TERMINAL_STATES: set[str] = {"done", "blocked", "partial", "error", "skipped"}
VALID_STATES: set[str] = {"pending", "in_progress"} | TERMINAL_STATES

# -- H-15: Canonical error codes (STD-107 security hardening)
ERR_INVALID_INPUT = "ERR_INVALID_INPUT"
ERR_INPUT_TOO_LARGE = "ERR_INPUT_TOO_LARGE"
ERR_LIMIT_EXCEEDED = "ERR_LIMIT_EXCEEDED"
ERR_INTERNAL = "ERR_INTERNAL"
ERR_TIMEOUT = "ERR_TIMEOUT"
ERR_WATCHDOG_TIMEOUT = "ERR_WATCHDOG_TIMEOUT"
ERR_CONFIG = "ERR_CONFIG"
ERR_PROVIDER = "ERR_PROVIDER"
ERR_PROVIDER_DOWN = "ERR_PROVIDER_DOWN"
ERR_RATE_LIMIT = "ERR_RATE_LIMIT"
ERR_EMPTY_RESPONSE = "ERR_EMPTY_RESPONSE"
ERR_STREAM_DISCONNECT = "ERR_STREAM_DISCONNECT"  # -- REQ-109 req 215: mid-SSE drop, transient
ERR_COST_CAP = "ERR_COST_CAP"
ERR_INVALID_PROFILE = "ERR_INVALID_PROFILE"
ERR_SUBPROCESS = "ERR_SUBPROCESS"
ERR_MUTATIONS_DISABLED = "ERR_MUTATIONS_DISABLED"
ERR_NESTED_SESSION = "ERR_NESTED_SESSION"
ERR_AUTH = "ERR_AUTH"


# ──────────────────────────────────────────────────────────────────
#  Dataclasses — Rondo-REQ-100 reqs 1-5, Rondo-STD-108, Rondo-REQ-100 Data Boundary
# ──────────────────────────────────────────────────────────────────


@dataclass
class Task:  # pylint: disable=too-many-instance-attributes
    """A single unit of AI work (Rondo-REQ-100 req 2)."""

    # -- identity
    name: str  # -- unique within round
    description: str = ""  # -- brief human summary

    # -- three-field contract (interactive tasks — Rondo-REQ-100 req 3)
    instruction: str = ""  # -- Do: what Claude should do
    context_files: list[str] = field(default_factory=list)  # -- Read: files for context
    done_when: str = ""  # -- Done: completion criteria

    # -- structured input (REQ-114 (structured-input) req 001)
    context_data: dict[str, Any] = field(default_factory=dict)

    # -- auto task (alternative to three-field — Rondo-REQ-100 req 4)
    auto_fn: Callable[..., tuple[bool, str]] | None = None

    # -- dispatch hints
    model: str | None = None  # -- recommended model (COALESCE — Rondo-REQ-100 req 23)
    task_type: str = ""  # -- affinity category for scoring/routing (RONDO-315, finding #297)
    mode: str = "interactive"  # -- "interactive" or "auto"
    tool_mode: str = "default"  # -- "none" | "sandbox" | "default" (REQ-100 reqs 022-024)
    bare: bool | None = None  # -- task-level --bare override (REQ-100 req 073: false to opt out)
    safe_parallel: bool = False  # -- REQ-101 req 058: safe for parallel dispatch
    human_input: str = ""  # -- Rondo-REQ-100 req 063: prompt for human before dispatch

    # -- dispatch hooks (REQ-100-addendum-dispatch-hooks reqs 100-114)
    pre_dispatch: list[Any] = field(default_factory=list)  # -- callables or "!shell" strings
    post_dispatch: list[Any] = field(default_factory=list)  # -- callables or "!shell" strings

    # -- state (Rondo-REQ-100 req 8)
    status: str = "pending"  # -- pending → in_progress → terminal

    @property
    def is_auto(self) -> bool:
        """True if this task has a Python callable instead of three-field contract."""
        return self.auto_fn is not None


@dataclass
class Gate:
    """Boolean check that guards round entry or exit (Rondo-REQ-100 req 5).

    Calling convention: runner calls check_fn() with NO arguments.
    Gates needing external context MUST capture it via closure.
    check_fn=None marks a MANUAL gate: live.py prints its description for
    a human to verify; run_gate() fails it closed (RONDO-338).
    """

    name: str
    check_fn: Callable[..., tuple[bool, str]] | None = None
    blocking: bool = True
    description: str = ""  # -- what a human should verify on a manual gate (RONDO-338)


@dataclass
class GateResult:
    """Outcome of running a gate check."""

    gate_name: str
    passed: bool
    detail: str
    blocking: bool = True  # -- carried from Gate for should_proceed()


@dataclass
class ErrorPayload:
    """Structured error context — carries recovery guidance through the chain.

    Rondo-REQ-100: every error includes code, context, and recovery path.
    Added FIX-674 (additive — legacy error_code/error_message preserved).
    """

    code: str  # -- ERR_SUBPROCESS, ERR_AUTH, etc.
    message: str  # -- human-readable explanation
    recovery: str = ""  # -- "Run rondo preflight" or "Check API key"
    transient: bool = False  # -- True = worth retrying
    layer: str = ""  # -- "dispatch", "runner", "overnight", "report"
    provider: str = ""  # -- which provider failed (if applicable)
    model: str = ""  # -- which model was targeted


@dataclass
class TaskResult:  # pylint: disable=too-many-instance-attributes
    """Outcome of dispatching a single task (Rondo-STD-108).

    Created by dispatch.py, consumed by runner.py and consumers.
    Defined here to avoid circular imports.
    """

    # -- identity
    task_name: str

    # -- outcome
    status: str = "pending"  # -- done, blocked, partial, error, skipped
    error_code: str | None = None
    error_message: str | None = None
    error_payload: ErrorPayload | None = None  # -- FIX-674: structured error with recovery

    # -- dispatch I/O
    prompt_sent: str = ""
    raw_output: str = ""
    parsed_result: dict[str, Any] | None = None
    stderr: str = ""
    exit_code: int | None = None

    # -- execution metadata
    duration_sec: float = 0.0
    model: str = ""
    auth_mode: str = ""
    timestamp: str = ""
    cost_usd: float | None = None

    # -- command audit (Rondo-REQ-100 req 015: know what was sent)
    command_sent: list[str] = field(default_factory=list)

    # -- file tracking (Rondo-STD-110 conflict detection)
    files_modified: list[str] = field(default_factory=list)

    # -- structured input audit (REQ-114 (structured-input) req 002)
    context_data: dict[str, Any] = field(default_factory=dict)

    # -- audit trail (STD-113: callers can reference this dispatch)
    dispatch_id: str = ""

    # -- ALWAYS-ON metrics (computed from audit data, included in every result)
    metrics: dict[str, Any] = field(default_factory=dict)

    # -- U-26 to U-30: result parsing helpers (read-only, never raise)

    def extract_json(self) -> dict[str, Any] | None:
        """U-26: Parse raw_output as JSON. Returns dict or None."""
        if not self.raw_output:
            return None
        try:
            return json.loads(self.raw_output)
        except (ValueError, TypeError):
            pass
        # -- Try balanced-brace extraction for nested JSON (Finding #178)
        try:
            start = self.raw_output.index("{")
            depth = 0
            for i, ch in enumerate(self.raw_output[start:], start):
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        candidate = self.raw_output[start : i + 1]
                        return json.loads(candidate)
        except (ValueError, TypeError):
            pass
        return None

    def extract_code_blocks(self) -> list[tuple[str, str]]:
        """U-27: Extract fenced code blocks. Returns list of (language, content)."""
        if not self.raw_output or not isinstance(self.raw_output, str):
            return []
        blocks: list[tuple[str, str]] = []
        for match in re.finditer(r"```(\w*)\n(.*?)```", self.raw_output, re.DOTALL):
            lang = match.group(1) or ""
            content = match.group(2).rstrip("\n")
            blocks.append((lang, content))
        return blocks

    def extract_table(self) -> list[dict[str, str]]:
        """U-28: Extract first markdown table. Returns list of {header: value} dicts."""
        if not self.raw_output or not isinstance(self.raw_output, str):
            return []
        lines = self.raw_output.strip().splitlines()
        # -- Find header row (contains |)
        header_idx = -1
        for i, line in enumerate(lines):
            if "|" in line and i + 1 < len(lines) and "---" in lines[i + 1]:
                header_idx = i
                break
        if header_idx < 0:
            return []
        headers = [h.strip() for h in lines[header_idx].split("|") if h.strip()]
        rows: list[dict[str, str]] = []
        for line in lines[header_idx + 2 :]:
            if "|" not in line:
                break
            cells = [c.strip() for c in line.split("|") if c.strip()]
            if cells:
                row = dict(zip(headers, cells))
                rows.append(row)
        return rows


@dataclass
class DispatchUsage:  # pylint: disable=too-many-instance-attributes
    """Stream-json metadata captured from each claude -p call (Rondo-IFS-100)."""

    task_name: str = ""
    model: str = ""
    cost_usd: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_create_tokens: int = 0
    duration_ms: int = 0
    duration_api_ms: int = 0
    num_turns: int = 0
    context_window: int = 0
    rate_limit_status: str = "unknown"  # -- default per Rondo-IFS-100 req 9
    is_using_overage: bool = False  # -- default per Rondo-IFS-100 req 9
    rate_limit_resets_at: int = 0  # -- 0 = not available
    budget_exceeded: bool = False  # -- Rondo-REQ-100 req 078: CC stopped due to --max-budget-usd


@dataclass
class RoundResult:  # pylint: disable=too-many-instance-attributes
    """Everything a consumer needs to know about a round execution (Rondo-REQ-100)."""

    # -- identity
    round_name: str = ""
    started_at: str = ""
    completed_at: str = ""
    duration_sec: float = 0.0

    # -- task results
    task_results: list[TaskResult] = field(default_factory=list)

    # -- gate results
    pre_gate_results: list[GateResult] = field(default_factory=list)
    post_gate_results: list[GateResult] = field(default_factory=list)

    # -- parallel execution info
    conflicts: list[str] = field(default_factory=list)
    parallelism: int = 1

    # -- usage metadata
    usage: list[DispatchUsage] = field(default_factory=list)

    # -- overall (req 46 for calculation rules)
    status: str = "pending"  # -- done, partial, error, skipped
    summary: str = ""


@dataclass
class Round:
    """A collection of tasks with pre/post gates (Rondo-REQ-100 req 1)."""

    name: str
    tasks: list[Task] = field(default_factory=list)
    pre_gates: list[Gate] = field(default_factory=list)
    post_gates: list[Gate] = field(default_factory=list)


# ──────────────────────────────────────────────────────────────────
#  Gate execution (Rondo-REQ-100 reqs 5-7)
# ──────────────────────────────────────────────────────────────────


def run_gate(gate: Gate) -> GateResult:
    """Execute a single gate check. Returns GateResult with blocking flag.

    Manual gates (check_fn=None) fail closed — a human must verify and
    re-run, matching the pre-RONDO-338 behavior (None crashed into the
    except and failed) but with an actionable message.
    """
    if gate.check_fn is None:
        return GateResult(
            gate_name=gate.name,
            passed=False,
            detail="Manual gate — no check_fn; verify by hand and re-run",
            blocking=gate.blocking,
        )
    try:
        passed, detail = gate.check_fn()
    except (TypeError, ValueError, RuntimeError, OSError, KeyError, AttributeError) as exc:
        passed = False
        detail = f"Gate exception: {exc}"
    return GateResult(
        gate_name=gate.name,
        passed=passed,
        detail=detail,
        blocking=gate.blocking,
    )


def run_gates(gates: list[Gate]) -> list[GateResult]:
    """Execute all gates in order. Returns list of GateResults."""
    return [run_gate(g) for g in gates]


def should_proceed(gate_results: list[GateResult]) -> bool:
    """Check if execution should proceed after gate checks (Rondo-REQ-100 req 6).

    Returns False if ANY blocking gate failed. Non-blocking failures
    are warnings only — they don't prevent execution.
    """
    for result in gate_results:
        if not result.passed and result.blocking:
            return False
    return True


def finalize_if_pre_gate_blocked(round_def: Round, result: RoundResult, start_time: float) -> bool:
    """Run pre-gates; finalize `result` as skipped when blocked — RONDO-382.

    Returns True when a blocking pre-gate failed (caller returns `result`),
    False to proceed. Extracted from runner/parallel (checklist item 13 R0801
    pair) — both execution paths MUST share the exact pre-gate contract
    (Rondo-REQ-100 req 6), so it lives here next to run_gates/should_proceed.
    """
    import time  # pylint: disable=import-outside-toplevel
    from datetime import UTC, datetime  # pylint: disable=import-outside-toplevel

    if not round_def.pre_gates:
        return False
    result.pre_gate_results = run_gates(round_def.pre_gates)
    if should_proceed(result.pre_gate_results):
        return False
    result.status = "skipped"
    failed = [g for g in result.pre_gate_results if not g.passed and g.blocking]
    result.summary = "Blocked by pre-gate: " + ", ".join(g.gate_name for g in failed)
    result.completed_at = datetime.now(UTC).isoformat()
    result.duration_sec = time.monotonic() - start_time
    return True


# ──────────────────────────────────────────────────────────────────
#  State management (Rondo-REQ-100 reqs 8-9)
# ──────────────────────────────────────────────────────────────────


def is_terminal(status: str) -> bool:
    """Check if a task status is terminal (Rondo-REQ-100 req 8)."""
    return status in TERMINAL_STATES


def is_round_complete(tasks: list[Task]) -> bool:
    """Check if all tasks are in terminal state (Rondo-REQ-100 req 9)."""
    return all(is_terminal(t.status) for t in tasks)


# ──────────────────────────────────────────────────────────────────
#  Round status calculation (Rondo-REQ-100 req 46)
# ──────────────────────────────────────────────────────────────────


def calculate_round_status(task_results: list[TaskResult]) -> str:
    """Calculate RoundResult.status from task statuses (Rondo-REQ-100 req 46).

    Rules:
        "done"    — all tasks have status done
        "partial" — at least one done and at least one non-done
        "error"   — all tasks are error or blocked (none succeeded)
        "skipped" — no tasks dispatched (gate blocked) or all skipped
    """
    if not task_results:
        return "skipped"

    statuses = {r.status for r in task_results}

    # -- All done
    if statuses == {"done"}:
        return "done"

    # -- All skipped
    if statuses == {"skipped"}:
        return "skipped"

    # -- Any done + any non-done = partial
    has_done = "done" in statuses
    if has_done:
        return "partial"

    # -- No done tasks — all are error/blocked/partial = error
    return "error"


# ──────────────────────────────────────────────────────────────────
#  Validation — Rondo-STD-108 defensive checks
# ──────────────────────────────────────────────────────────────────


def validate_task(
    task: Task,
    *,
    project_root: str | None = None,
    max_context_bytes: int = 500_000,
) -> list[str]:
    """Validate a task before dispatch. Returns list of errors (empty = valid).

    Checks:
        - Name is not empty
        - Interactive tasks have instruction + done_when
        - Auto tasks have auto_fn
        - Task doesn't set both auto_fn AND three-field contract
        - context_files: no traversal, no absolute, no symlinks outside root, size cap
    """
    errors: list[str] = []

    if not task.name.strip():
        errors.append("Task has empty name")

    has_auto = task.auto_fn is not None
    has_interactive = bool(task.instruction.strip() or task.done_when.strip())

    if has_auto and has_interactive:
        errors.append(f"Task '{task.name}' has both auto_fn AND three-field contract — pick one")

    if not has_auto and not has_interactive:
        errors.append(f"Task '{task.name}' has neither auto_fn nor instruction/done_when")

    if not has_auto:
        if not task.instruction.strip():
            errors.append(f"Task '{task.name}' Do field (instruction) is empty")
        if not task.done_when.strip():
            errors.append(f"Task '{task.name}' Done field (done_when) is empty")

    # -- REQ-100 req 024: tool_mode validation
    valid_tool_modes = {"none", "sandbox", "default"}
    if task.tool_mode not in valid_tool_modes:
        errors.append(
            f"Task '{task.name}' tool_mode '{task.tool_mode}' invalid — must be one of {sorted(valid_tool_modes)}"
        )

    # -- REQ-114 (structured-input) req 009: context_data must be JSON-serializable
    context_data_size = 0
    if task.context_data:
        try:
            serialized = json.dumps(task.context_data)
            context_data_size = len(serialized.encode("utf-8"))
        except (TypeError, ValueError) as e:
            errors.append(f"Task '{task.name}' context_data not JSON-serializable: {e}")

    # -- REQ-114 (structured-input) req 005: context_data included in size cap
    if context_data_size > max_context_bytes:
        errors.append(
            f"Task '{task.name}' context_data {context_data_size} bytes exceeds max_context_bytes ({max_context_bytes})"
        )

    # -- REQ-100 req 003: context_files validation (extracted for complexity)
    errors.extend(_validate_context_files(task, project_root, max_context_bytes, context_data_size))

    return errors


def _validate_context_files(
    task: Task,
    project_root: str | None,
    max_context_bytes: int,
    context_data_size: int = 0,
) -> list[str]:
    """Validate context_files paths — REQ-100 req 003.

    Checks: no traversal, no absolute (without root), no symlinks outside root, size cap.
    REQ-114 (structured-input) req 005: combined context_files + context_data size checked.
    """
    errors: list[str] = []
    total_size = 0

    for path_str in task.context_files:
        if ".." in path_str:
            errors.append(f"Task '{task.name}' context_file '{path_str}' contains '..' traversal")
        if path_str.startswith("/") and not project_root:
            errors.append(f"Task '{task.name}' context_file '{path_str}' is absolute path")

        # -- Symlink check: resolve and verify within project root
        if project_root:
            resolved = Path(path_str).resolve()
            root = Path(project_root).resolve()
            if Path(path_str).is_symlink() and not str(resolved).startswith(str(root)):
                errors.append(f"Task '{task.name}' context_file '{path_str}' is symlink outside project root")

        # -- Size accumulator
        p = Path(path_str)
        if p.exists() and p.is_file():
            total_size += p.stat().st_size

    combined_size = total_size + context_data_size
    if combined_size > max_context_bytes:
        errors.append(
            f"Task '{task.name}' context total {combined_size} bytes "
            f"(files={total_size} + data={context_data_size}) exceeds max_context_bytes ({max_context_bytes})"
        )

    return errors


def validate_round(round_def: Round) -> list[str]:
    """Validate a round before execution. Returns list of errors (empty = valid).

    Checks:
        - Round name is not empty
        - No duplicate task names
        - All tasks pass validate_task()
    """
    errors: list[str] = []

    if not round_def.name.strip():
        errors.append("Round name is empty")

    task_names: set[str] = set()
    for task in round_def.tasks:
        if task.name in task_names:
            errors.append(f"Duplicate task name: '{task.name}'")
        task_names.add(task.name)
        errors.extend(validate_task(task))

    return errors


# ──────────────────────────────────────────────────────────────────
#  Serialization (Rondo-REQ-100 reqs 10-11)
# ──────────────────────────────────────────────────────────────────


def round_state_to_dict(
    tasks: list[Task],
    gate_results: list[GateResult],
) -> dict[str, Any]:
    """Serialize round state to a dict (JSON-safe). Rondo-REQ-100 req 10."""
    return {
        "task_statuses": {t.name: t.status for t in tasks},
        "gate_results": [
            {
                "gate_name": gr.gate_name,
                "passed": gr.passed,
                "detail": gr.detail,
            }
            for gr in gate_results
        ],
    }


def round_state_from_dict(tasks: list[Task], state: dict[str, Any]) -> None:
    """Apply saved state to tasks for resume. Rondo-REQ-100 req 11.

    Mutates tasks in place — sets status from saved state.
    Tasks not in the saved state keep their current status (pending).
    """
    status_map = state.get("task_statuses", {})
    for task in tasks:
        if task.name in status_map:
            task.status = status_map[task.name]


# -- ──────────────────────────────────────────────────────────────
# --  Round file loading — RONDO-213 cycle break
# -- ──────────────────────────────────────────────────────────────
# -- Moved from cli.py to engine.py in RONDO-213 because 3 modules
# -- (cli_commands/dispatch, mcp_dispatch, mcp_tools) imported
# -- load_round_file from cli.py, creating cycles back to the CLI layer.
# -- engine.py is a leaf module (imports nothing from rondo.*) so it's
# -- the correct home — same pattern as config.py for shared constants.


def load_round_file(filepath: str, *, allow_python: bool = False) -> Round:
    """Load a round definition from .py, .yaml, .yml, or .json file.

    REQ-100 req 39 (Python), REQ-111 reqs 410-414 (YAML/JSON).
    Detects format by extension. YAML/JSON delegates to round_loader.

    RONDO-330 (SOP-105 P1-3): THIS is the .py executor, so THIS is where
    the trust gate lives — importing a .py round runs it. Requires
    allow_python=True (CLI: --allow-python-rounds) or config
    `[security] allow_python_rounds = true`.
    """
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"Round file not found: {filepath}")

    # -- REQ-111: YAML/JSON support via round_loader
    if path.suffix.lower() in (".yaml", ".yml", ".json"):
        from rondo.round_loader import load_round  # pylint: disable=import-outside-toplevel

        return load_round(filepath)

    # -- RONDO-330 trust gate (lazy import — round_loader imports engine)
    from rondo.round_loader import (  # pylint: disable=import-outside-toplevel
        PythonRoundBlockedError,
        _config_allows_python_rounds,
    )

    if not (allow_python or _config_allows_python_rounds()):
        raise PythonRoundBlockedError(
            f"Refusing to load Python round '{path.name}': importing a .py round "
            f"file means running code you may not have read — a downloaded round "
            f"IS a program. Options:\n"
            f"  1. Re-run with --allow-python-rounds (one-time, explicit)\n"
            f"  2. Add to ~/.rondo/config.toml:  [security]\\n  allow_python_rounds = true\n"
            f"  3. Prefer the safe declarative formats: .yaml / .json rounds\n"
            f"     (same tasks/gates, no code execution — see docs/GOLDEN-FIVE.md)"
        )

    # -- Python round files (existing path)
    import importlib.util  # pylint: disable=import-outside-toplevel

    spec = importlib.util.spec_from_file_location("round_def", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module spec from: {filepath}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    if not hasattr(module, "build_round"):
        raise AttributeError(f"Round file '{filepath}' must define a build_round() function")

    result = module.build_round()

    if not isinstance(result, Round):
        raise TypeError(f"build_round() must return a Round, got {type(result).__name__}")

    return result


def load_phases_file(filepath: str, *, allow_python: bool = False) -> list[Round]:
    """Dynamically import a phases file and call build_phases().

    Same pattern as load_round_file() but expects build_phases() → list[Round].
    RONDO-330: same trust gate — a phases file EXECUTES on import.
    """
    import importlib.util  # pylint: disable=import-outside-toplevel

    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"Phases file not found: {filepath}")

    from rondo.round_loader import (  # pylint: disable=import-outside-toplevel
        PythonRoundBlockedError,
        _config_allows_python_rounds,
    )

    if not (allow_python or _config_allows_python_rounds()):
        raise PythonRoundBlockedError(
            f"Refusing to load Python phases file '{path.name}': importing it runs "
            f"code you may not have read. Re-run with --allow-python-rounds, or set "
            f"[security] allow_python_rounds = true in ~/.rondo/config.toml."
        )

    spec = importlib.util.spec_from_file_location("phases_def", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module spec from: {filepath}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    if not hasattr(module, "build_phases"):
        raise AttributeError(f"Phases file '{filepath}' must define a build_phases() function")

    result = module.build_phases()

    if not isinstance(result, list):
        raise TypeError(f"build_phases() must return a list, got {type(result).__name__}")

    return result


# -- sig: mgh-6201.cd.bd955f.773b.5b324e
