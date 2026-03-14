"""Rondo — Define AI tasks in Python, send them to Claude, get structured results back.

Public API (REQ-001 req 35):
    Round, Task, Gate, GateResult, TaskResult, RoundResult, DispatchUsage
    RondoConfig, load_config, validate_config
    dispatch_task, run_round
"""
from rondo.config import (
    RondoConfig,
    load_config,
    validate_config,
)
from rondo.dispatch import dispatch_task
from rondo.engine import (
    DispatchUsage,
    Gate,
    GateResult,
    Round,
    RoundResult,
    Task,
    TaskResult,
)
from rondo.runner import run_round

__all__ = [
    "Round",
    "Task",
    "Gate",
    "GateResult",
    "TaskResult",
    "RoundResult",
    "DispatchUsage",
    "RondoConfig",
    "load_config",
    "validate_config",
    "dispatch_task",
    "run_round",
]
