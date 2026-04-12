# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
r"""Shared helpers for ``examples/api`` scripts.

Run from the ``rondo`` package root (installed editable or ``PYTHONPATH=src``), e.g.::

    cd rondo && uv run python examples/api/01_simple_dispatch.py
    cd rondo && uv run python examples/api/code_review_to_findings.py

Why ``execution`` matters
-------------------------
Python examples explicitly pass ``execution="subprocess"`` so they always return
task results (``status``, ``tasks``, …) instead of host plan JSON.

Provider models (``gemini:...``, ``anthropic:...``) still use the HTTP adapter.

See also: ``rondo_run_file`` docstring in ``rondo.mcp_dispatch``.
"""

from __future__ import annotations

import json
from typing import Any

__all__ = [
    "banner",
    "first_task_status",
    "first_task_parsed_json",
    "is_partial_with_output",
    "invoke_rondo",
    "run_prompt_json",
]


def banner(title: str, char: str = "=", width: int = 64) -> str:
    """Return a single heading line for stdout."""
    line = char * width
    return f"{line}\n{title}\n{line}"


def invoke_rondo(
    *,
    prompt: str,
    model: str = "",
    dry_run: bool = False,
    timeout_sec: int = 180,
    rules: str = "",
    allowed_tools: str = "",
    max_turns: int = 0,
    done_when: str = "Task completed. Return results.",
    project: str = "",
    max_budget: float = 0.0,
    file_path: str = "",
    execution: str = "subprocess",
) -> dict[str, Any]:
    """Call ``rondo_run_file`` and return the top-level JSON object.

    Raises:
        RuntimeError: Body is not JSON, Rondo returned an error envelope without tasks,
            or a host **plan** was returned instead of dispatch results (wrong routing).
    """
    from rondo.envelope import normalize_envelope
    from rondo.mcp_dispatch import rondo_run_file

    raw = rondo_run_file(
        file_path=file_path,
        prompt=prompt,
        model=model,
        dry_run=dry_run,
        timeout_sec=timeout_sec,
        execution=execution,
        rules=rules,
        allowed_tools=allowed_tools or "",
        max_turns=max_turns,
        done_when=done_when,
        project=project,
        max_budget=max_budget,
    )
    try:
        data: dict[str, Any] = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Rondo returned non-JSON (first 400 chars): {raw[:400]!r}") from exc

    data = normalize_envelope(data)

    if data.get("status") == "plan" and "engine" in data:
        raise RuntimeError(
            "Received a host plan instead of task results. "
            "Use execution='subprocess' for scripts or pass a provider-prefixed model."
        )
    err = data.get("error_message") or data.get("error") or data.get("reason")
    if data.get("status") == "error" and err and not data.get("tasks"):
        raise RuntimeError(str(err))

    return data


def first_task_status(envelope: dict[str, Any]) -> str:
    """Return first task status, or empty string when no tasks exist."""
    tasks = envelope.get("tasks") or []
    if not tasks:
        return ""
    return str(tasks[0].get("status", ""))


def is_partial_with_output(envelope: dict[str, Any]) -> bool:
    """Return True when first task is partial and has non-empty output."""
    tasks = envelope.get("tasks") or []
    if not tasks:
        return False
    first = tasks[0]
    return str(first.get("status", "")) == "partial" and bool((first.get("raw_output") or "").strip())


def first_task_parsed_json(envelope: dict[str, Any]) -> dict[str, Any]:
    """Parse the first task's ``raw_output`` as JSON.

    On failure to parse model output as JSON, returns a dict with
    ``_non_json`` True and ``snippet`` text — callers must not treat that as a successful model contract.
    """
    tasks = envelope.get("tasks") or []
    if not tasks:
        raise RuntimeError(f"No tasks in envelope; keys={list(envelope.keys())!r}")

    t0: dict[str, Any] = tasks[0]
    if t0.get("status") == "error":
        code = t0.get("error_code", "")
        msg = t0.get("error_message", "")
        raise RuntimeError(f"Task error {code}: {msg}")

    raw_out = (t0.get("raw_output") or "").strip()
    if not raw_out:
        return {}

    try:
        return json.loads(raw_out)
    except json.JSONDecodeError:
        return {"_non_json": True, "snippet": raw_out[:2000]}


def run_prompt_json(
    *,
    prompt: str,
    model: str = "",
    dry_run: bool = False,
    timeout_sec: int = 180,
    rules: str = "",
    allowed_tools: str = "",
    max_turns: int = 0,
    done_when: str = "Task completed. Return results.",
    project: str = "",
    max_budget: float = 0.0,
    file_path: str = "",
    execution: str = "subprocess",
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Invoke Rondo and return ``(full_envelope, first_task_json)``."""
    env = invoke_rondo(
        prompt=prompt,
        model=model,
        dry_run=dry_run,
        timeout_sec=timeout_sec,
        rules=rules,
        allowed_tools=allowed_tools,
        max_turns=max_turns,
        done_when=done_when,
        project=project,
        max_budget=max_budget,
        file_path=file_path,
        execution=execution,
    )
    return env, first_task_parsed_json(env)
