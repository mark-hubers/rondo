# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Shared dispatch envelope normalization for MCP/API/CLI surfaces.

REQ-112 reqs 500-506: canonical result/error envelope, stable error_code taxonomy,
and deterministic top-level status derivation including `partial`.
"""

from __future__ import annotations

from typing import Any

ENVELOPE_SCHEMA_VERSION = "2"

ERROR_HELP_BY_CODE: dict[str, str] = {
    "ERR_INPUT_TOO_LARGE": "Reduce prompt/context size or switch to a model with a larger context window.",
    "ERR_FILE_NOT_FOUND": "Verify file_path exists and is readable from the current working directory.",
    "ERR_INVALID_INPUT": "Check required parameters (prompt or file_path) and rerun with valid inputs.",
    "ERR_PROJECT_NOT_FOUND": "Set project to an existing directory path before dispatch.",
    "ERR_TIMEOUT": "Increase timeout_sec, simplify the prompt, or retry with backoff.",
    "ERR_UNKNOWN_DISPATCH_ID": "Use a valid dispatch_id from rondo_run_file(background=True) response.",
    "ERR_INVALID_EXECUTION": "Use execution=inline|subprocess|agent (or empty string for auto).",
    "ERR_INVALID_EXECUTION_MODEL": "Use a Claude model for execution=agent, or switch execution mode.",
    "ERR_DISPATCH_EXCEPTION": "Inspect task error_message/raw_output and retry once with a simpler prompt.",
}


def _resolve_error_message(error_code: str, error_message: str) -> str:
    """Return a stable user-facing error message for the envelope."""
    msg = (error_message or "").strip()
    if msg:
        return msg
    return f"Dispatch failed ({error_code})"


def _resolve_error_help(error_code: str) -> str:
    """Return user-facing next action guidance for known error codes."""
    return ERROR_HELP_BY_CODE.get(error_code, "Check error_message and task output, then retry with adjusted inputs.")


def _compute_counts(data: dict[str, Any], tasks: list[Any]) -> None:
    """Populate count fields with defaults derived from task statuses."""
    counts = compute_task_counts(tasks)
    for key, value in counts.items():
        data[key] = int(data.get(key, value))


def _normalize_status(data: dict[str, Any], tasks: list[Any]) -> None:
    """Normalize top-level status with deterministic derivation rules."""
    status = str(data.get("status", "")).strip()
    if status in ("", "unknown"):
        data["status"] = derive_top_level_status(tasks)
        return
    if status == "error" and tasks:
        # -- S1 fix: task-level partial/error mix should not collapse to top-level error.
        data["status"] = derive_top_level_status(tasks)


def _promote_task_error_fields(data: dict[str, Any], tasks: list[Any]) -> None:
    """Promote first task-level error metadata to top-level when missing."""
    if data.get("error_code") or data.get("error_message") or not tasks:
        return
    first_error = next(
        (
            t
            for t in tasks
            if isinstance(t, dict)
            and str(t.get("status", "")).strip().lower() in ("error", "blocked")
            and (t.get("error_code") or t.get("error_message"))
        ),
        None,
    )
    if isinstance(first_error, dict):
        data["error_code"] = first_error.get("error_code", "")
        data["error_message"] = first_error.get("error_message", "")


def _normalize_error_fields(data: dict[str, Any], tasks: list[Any]) -> None:
    """Ensure canonical top-level error fields are present and aligned."""
    if data.get("status") != "error":
        return
    _promote_task_error_fields(data, tasks)
    error_code = str(data.get("error_code") or data.get("code") or "ERR_DISPATCH_EXCEPTION")
    error_message = _resolve_error_message(error_code, str(data.get("error_message") or data.get("error") or ""))
    data["error_message"] = error_message
    data["error_code"] = error_code
    data["error_help"] = _resolve_error_help(error_code)
    # -- Backward-compat aliases.
    data["error"] = error_message
    data["code"] = error_code


def _normalize_numeric_fields(data: dict[str, Any]) -> None:
    """Normalize numeric and boolean envelope fields."""
    data["total_cost_usd"] = float(data.get("total_cost_usd", 0.0) or 0.0)
    data["duration_sec"] = float(data.get("duration_sec", 0.0) or 0.0)
    data["dry_run"] = bool(data.get("dry_run", False))


def build_error_envelope(
    *,
    error_code: str,
    error_message: str,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build canonical error envelope with stable code/message fields."""
    resolved_message = _resolve_error_message(error_code, error_message)
    payload: dict[str, Any] = {
        "schema_version": ENVELOPE_SCHEMA_VERSION,
        "status": "error",
        "error_code": error_code,
        "error_message": resolved_message,
        "error_help": _resolve_error_help(error_code),
        # -- Backward-compat aliases for older callers.
        "error": resolved_message,
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
    _compute_counts(data, tasks)
    _normalize_status(data, tasks)
    _normalize_error_fields(data, tasks)
    _normalize_numeric_fields(data)
    return data


# -- sig: mgh-6201.cd.bd955f.f0d0.e27401
