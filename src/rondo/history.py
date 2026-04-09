# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Rondo dispatch history — per-task telemetry logging + querying.

Rondo-REQ-104: queryable dispatch history for cost tracking and optimization.
Stores as JSONL (one JSON object per line) — simple, appendable, greppable.

Import direction:
    history.py → no rondo imports (standalone utility)
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass
class DispatchRecord:  # pylint: disable=too-many-instance-attributes
    """One dispatch event — Rondo-REQ-104 req 002."""

    round_name: str = ""
    task_name: str = ""
    model: str = ""
    status: str = ""
    cost_usd: float = 0.0
    duration_sec: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    confidence: float = 0.0
    error_code: str = ""
    budget_exceeded: bool = False
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


def log_dispatch(record: DispatchRecord, history_dir: str) -> None:
    """Append dispatch record to JSONL history file.

    Rondo-REQ-104 req 001: per-round telemetry.
    One file per day: history-YYYY-MM-DD.jsonl
    """
    out_dir = Path(history_dir)
    out_dir.mkdir(parents=True, exist_ok=True, mode=0o700)

    date_str = datetime.now(UTC).strftime("%Y-%m-%d")
    filepath = out_dir / f"history-{date_str}.jsonl"

    line = json.dumps(asdict(record), default=str)
    with open(filepath, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def load_history(history_dir: str) -> list[dict[str, Any]]:
    """Load all dispatch records from JSONL files.

    Rondo-REQ-104 req 004: queryable history.
    Returns list of dicts (not dataclasses — for flexible querying).
    """
    out_dir = Path(history_dir)
    if not out_dir.exists():
        return []

    records: list[dict[str, Any]] = []
    for filepath in sorted(out_dir.glob("history-*.jsonl")):
        for line in filepath.read_text(encoding="utf-8").strip().split("\n"):
            if line.strip():
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return records


def query_history(
    records: list[dict[str, Any]],
    *,
    model: str = "",
    status: str = "",
    round_name: str = "",
    task_name: str = "",
) -> list[dict[str, Any]]:
    """Filter history records — Rondo-REQ-104 req 004."""
    result = records
    if model:
        result = [r for r in result if r.get("model") == model]
    if status:
        result = [r for r in result if r.get("status") == status]
    if round_name:
        result = [r for r in result if r.get("round_name") == round_name]
    if task_name:
        result = [r for r in result if r.get("task_name") == task_name]
    return result


def aggregate_by_model(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Per-model cost/count/duration aggregates — Rondo-REQ-104 req 003."""
    agg: dict[str, dict[str, Any]] = {}
    for r in records:
        model = r.get("model", "unknown")
        if model not in agg:
            agg[model] = {"count": 0, "total_cost": 0.0, "total_duration": 0.0, "success": 0, "error": 0}
        agg[model]["count"] += 1
        agg[model]["total_cost"] += r.get("cost_usd", 0)
        agg[model]["total_duration"] += r.get("duration_sec", 0)
        if r.get("status") == "done":
            agg[model]["success"] += 1
        elif r.get("status") == "error":
            agg[model]["error"] += 1
    return agg


# -- sig: mgh-6201.cd.bd955f.e4a1.d3e4f5
