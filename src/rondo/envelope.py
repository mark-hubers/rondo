# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Shared dispatch envelope normalization for MCP/API/CLI surfaces.

REQ-112 reqs 500-506: canonical result/error envelope, stable error_code taxonomy,
and deterministic top-level status derivation including `partial`.
"""

from __future__ import annotations

from typing import Any

ENVELOPE_SCHEMA_VERSION = "2"


def build_error_envelope(
    *,
    error_code: str,
    error_message: str,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build canonical error envelope with stable code/message fields."""
    payload: dict[str, Any] = {
        "schema_version": ENVELOPE_SCHEMA_VERSION,
        "status": "error",
        "error_code": error_code,
        "error_message": error_message,
        # -- Backward-compat aliases for older callers.
        "error": error_message,
        "code": error_code,
        "tasks": [],
        "done_count": 0,
        "error_count": 0,
        "partial_count": 0,
        "pending_count": 0,
        "total_cost_usd": 0.0,
        "duration_sec": 0.0,
        "dry_run": False,
    }
    if context:
        payload.update(context)
    return payload


def compute_task_counts(tasks: list[Any]) -> dict[str, int]:
    """Compute top-level task counters from task status values."""
    statuses: list[str] = []
    for task in tasks:
        if isinstance(task, dict):
            statuses.append(str(task.get("status", "")))
        else:
            statuses.append("")
    return {
        "done_count": statuses.count("done") + statuses.count("skipped"),
        "error_count": statuses.count("error") + statuses.count("blocked"),
        "partial_count": statuses.count("partial"),
        "pending_count": statuses.count("pending"),
    }


def derive_top_level_status(tasks: list[Any]) -> str:
    """Derive deterministic top-level dispatch status from task statuses."""
    counts = compute_task_counts(tasks)
    has_pending = counts["pending_count"] > 0
    has_done = counts["done_count"] > 0
    has_partial = counts["partial_count"] > 0
    has_error = counts["error_count"] > 0

    if has_pending and not (has_done or has_partial or has_error):
        return "running"
    if not (has_partial or has_error):
        return "done"
    if has_partial and not has_error:
        return "partial"
    if has_done or has_partial:
        return "partial"
    return "error"


def normalize_envelope(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize a dispatch payload to the canonical schema fields."""
    data = dict(payload)
    tasks_raw = data.get("tasks")
    tasks = tasks_raw if isinstance(tasks_raw, list) else []
    data["tasks"] = tasks
    data["schema_version"] = str(data.get("schema_version") or ENVELOPE_SCHEMA_VERSION)

    counts = compute_task_counts(tasks)
    for key, value in counts.items():
        data[key] = int(data.get(key, value))

    status = str(data.get("status", "")).strip()
    if status in ("", "unknown"):
        data["status"] = derive_top_level_status(tasks)
    elif status == "error" and tasks:
        # -- S1 fix: task-level partial/error mix should not collapse to top-level error.
        data["status"] = derive_top_level_status(tasks)

    if data.get("status") == "error":
        error_message = str(data.get("error_message") or data.get("error") or "Dispatch failed")
        error_code = str(data.get("error_code") or data.get("code") or "ERR_DISPATCH_EXCEPTION")
        data["error_message"] = error_message
        data["error_code"] = error_code
        # -- Backward-compat aliases.
        data["error"] = error_message
        data["code"] = error_code

    data["total_cost_usd"] = float(data.get("total_cost_usd", 0.0) or 0.0)
    data["duration_sec"] = float(data.get("duration_sec", 0.0) or 0.0)
    data["dry_run"] = bool(data.get("dry_run", False))
    return data


# -- sig: mgh-6201.cd.bd955f.f0d0.e27401
