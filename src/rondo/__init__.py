# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Rondo — Define AI tasks in Python, send them to Claude, get structured results back.

Public API (Rondo-REQ-100 req 35):
    Round, Task, Gate, GateResult, TaskResult, RoundResult, DispatchUsage
    RondoConfig, load_config, validate_config
    dispatch_task, run_round, run_parallel, detect_conflicts

Advanced modules (stable but specialized):
    sanitize — STD-114 output sanitization (secret detection + scrubbing)
    audit — STD-113 dispatch audit trail (two-phase JSONL recording)
    flaky — REQ-107 task flakiness detection (flip rate scoring)
"""

from rondo.config import (
    RondoConfig,
    load_config,
    validate_config,
)
from rondo.dispatch import dispatch_task
from rondo.engine import (
    DispatchUsage,
    ErrorPayload,
    Gate,
    GateResult,
    Round,
    RoundResult,
    Task,
    TaskResult,
    validate_round,
    validate_task,
)
from rondo.live import run_live
from rondo.overnight import EventLog, OvernightResult, check_usage_gate, run_overnight
from rondo.parallel import detect_conflicts, run_parallel
from rondo.report import generate_report, save_report
from rondo.runner import run_round

__all__ = [
    "Round",
    "Task",
    "Gate",
    "GateResult",
    "TaskResult",
    "RoundResult",
    "DispatchUsage",
    "ErrorPayload",
    "RondoConfig",
    "load_config",
    "validate_config",
    "dispatch_task",
    "run_round",
    "run_parallel",
    "detect_conflicts",
    "run_overnight",
    "OvernightResult",
    "EventLog",
    "check_usage_gate",
    "generate_report",
    "save_report",
    "validate_round",
    "validate_task",
    "run_live",
]


# -- sig: mgh-6201.cd.bd955f.8e2c.008cb8
