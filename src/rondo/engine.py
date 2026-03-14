"""Rondo engine — data model, state machine, gate execution, serialization.

REQ-001 reqs 1-11, 23, 29, 31, 46.
All dataclasses live here. Other modules (dispatch, runner, parallel)
import types from engine — never the other way around.

Status vocabulary (shared with STD-001):
    done, blocked, partial, error, skipped  (terminal)
    pending, running                        (non-terminal)
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

# -- Status constants (REQ-001 req 8)
TERMINAL_STATES: set[str] = {"done", "blocked", "partial", "error", "skipped"}
VALID_STATES: set[str] = {"pending", "running"} | TERMINAL_STATES


# ──────────────────────────────────────────────────────────────────
#  Dataclasses — REQ-001 reqs 1-5, STD-001, REQ-001 Data Boundary
# ──────────────────────────────────────────────────────────────────


@dataclass
class Task:
    """A single unit of AI work (REQ-001 req 2)."""

    # -- identity
    name: str  # -- unique within round
    description: str = ""  # -- brief human summary

    # -- three-field contract (interactive tasks — REQ-001 req 3)
    instruction: str = ""  # -- Do: what Claude should do
    context_files: list[str] = field(default_factory=list)  # -- Read: files for context
    done_when: str = ""  # -- Done: completion criteria

    # -- auto task (alternative to three-field — REQ-001 req 4)
    auto_fn: Callable[..., tuple[bool, str]] | None = None

    # -- dispatch hints
    model: str | None = None  # -- recommended model (COALESCE — REQ-001 req 23)
    mode: str = "interactive"  # -- "interactive" or "auto"

    # -- state (REQ-001 req 8)
    status: str = "pending"  # -- pending → running → terminal

    @property
    def is_auto(self) -> bool:
        """True if this task has a Python callable instead of three-field contract."""
        return self.auto_fn is not None


@dataclass
class Gate:
    """Boolean check that guards round entry or exit (REQ-001 req 5).

    Calling convention: runner calls check_fn() with NO arguments.
    Gates needing external context MUST capture it via closure.
    """

    name: str
    check_fn: Callable[..., tuple[bool, str]]
    blocking: bool = True


@dataclass
class GateResult:
    """Outcome of running a gate check."""

    gate_name: str
    passed: bool
    detail: str
    blocking: bool = True  # -- carried from Gate for should_proceed()


@dataclass
class TaskResult:
    """Outcome of dispatching a single task (STD-001).

    Created by dispatch.py, consumed by runner.py and consumers.
    Defined here to avoid circular imports.
    """

    # -- identity
    task_name: str

    # -- outcome
    status: str = "pending"  # -- done, blocked, partial, error, skipped
    error_code: str | None = None
    error_message: str | None = None

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

    # -- file tracking (STD-003 conflict detection)
    files_modified: list[str] = field(default_factory=list)


@dataclass
class DispatchUsage:
    """Stream-json metadata captured from each claude -p call (IFS-001)."""

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
    rate_limit_status: str = "unknown"  # -- default per IFS-001 req 9
    is_using_overage: bool = False  # -- default per IFS-001 req 9
    rate_limit_resets_at: int = 0  # -- 0 = not available


@dataclass
class RoundResult:
    """Everything a consumer needs to know about a round execution (REQ-001)."""

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
    """A collection of tasks with pre/post gates (REQ-001 req 1)."""

    name: str
    tasks: list[Task] = field(default_factory=list)
    pre_gates: list[Gate] = field(default_factory=list)
    post_gates: list[Gate] = field(default_factory=list)


# ──────────────────────────────────────────────────────────────────
#  Gate execution (REQ-001 reqs 5-7)
# ──────────────────────────────────────────────────────────────────


def run_gate(gate: Gate) -> GateResult:
    """Execute a single gate check. Returns GateResult with blocking flag."""
    try:
        passed, detail = gate.check_fn()
    except Exception as exc:
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
    """Check if execution should proceed after gate checks (REQ-001 req 6).

    Returns False if ANY blocking gate failed. Non-blocking failures
    are warnings only — they don't prevent execution.
    """
    for result in gate_results:
        if not result.passed and result.blocking:
            return False
    return True


# ──────────────────────────────────────────────────────────────────
#  State management (REQ-001 reqs 8-9)
# ──────────────────────────────────────────────────────────────────


def is_terminal(status: str) -> bool:
    """Check if a task status is terminal (REQ-001 req 8)."""
    return status in TERMINAL_STATES


def is_round_complete(tasks: list[Task]) -> bool:
    """Check if all tasks are in terminal state (REQ-001 req 9)."""
    return all(is_terminal(t.status) for t in tasks)


# ──────────────────────────────────────────────────────────────────
#  Round status calculation (REQ-001 req 46)
# ──────────────────────────────────────────────────────────────────


def calculate_round_status(task_results: list[TaskResult]) -> str:
    """Calculate RoundResult.status from task statuses (REQ-001 req 46).

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
#  Serialization (REQ-001 reqs 10-11)
# ──────────────────────────────────────────────────────────────────


def round_state_to_dict(
    tasks: list[Task],
    gate_results: list[GateResult],
) -> dict[str, Any]:
    """Serialize round state to a dict (JSON-safe). REQ-001 req 10."""
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
    """Apply saved state to tasks for resume. REQ-001 req 11.

    Mutates tasks in place — sets status from saved state.
    Tasks not in the saved state keep their current status (pending).
    """
    status_map = state.get("task_statuses", {})
    for task in tasks:
        if task.name in status_map:
            task.status = status_map[task.name]
