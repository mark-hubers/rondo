# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
r"""Shared helpers for ``examples/api`` scripts.

Run from the ``rondo`` package root (installed editable or ``PYTHONPATH=src``), e.g.::

    cd rondo && uv run python examples/api/01_simple_dispatch.py
    cd rondo && uv run python examples/api/code_review_to_findings.py

Why ``_session`` matters
------------------------
``rondo_run_file(..., model="", ...)`` normally resolves to an **inline** or **agent**
plan: JSON instructions for the *host* (Claude Code / MCP) to execute, not task
results with a ``tasks`` array.

Passing a **non-None** ``_session`` tells Rondo you are in a host-executable context.
The dispatcher then rewrites that route to a real ``claude -p`` subprocess so Python
callers receive normal round JSON (``status``, ``tasks``, …). The MCP server passes
the real client session; these examples use :data:`HOST_SESSION_PLACEHOLDER` — a
documented sentinel, not a live MCP session.

Provider models (``gemini:...``, ``anthropic:...``) always use the HTTP adapter and
do not need this sentinel for routing, but passing it is harmless.

See also: ``rondo_run_file`` docstring in ``rondo.mcp_dispatch``.
"""

from __future__ import annotations

import json
from typing import Any

__all__ = [
    "HOST_SESSION_PLACEHOLDER",
    "banner",
    "first_task_parsed_json",
    "invoke_rondo",
    "run_prompt_json",
]

# -- Single instance: any non-None object satisfies the routing contract.
HOST_SESSION_PLACEHOLDER = object()


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
) -> dict[str, Any]:
    """Call ``rondo_run_file`` and return the top-level JSON object.

    Raises:
        RuntimeError: Body is not JSON, Rondo returned an error envelope without tasks,
            or a host **plan** was returned instead of dispatch results (wrong routing).
    """
    from rondo.mcp_dispatch import rondo_run_file

    raw = rondo_run_file(
        file_path=file_path,
        prompt=prompt,
        model=model,
        dry_run=dry_run,
        timeout_sec=timeout_sec,
        _session=HOST_SESSION_PLACEHOLDER,
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

    if data.get("status") == "plan" and "engine" in data:
        raise RuntimeError(
            "Received a host plan instead of task results. "
            "Use invoke_rondo() (sets _session) or an explicit provider-prefixed model."
        )
    err = data.get("error") or data.get("reason")
    if data.get("status") == "error" and err and not data.get("tasks"):
        raise RuntimeError(str(err))

    return data


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
    )
    return env, first_task_parsed_json(env)
