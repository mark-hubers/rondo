# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Rondo dispatch hooks — pre/post processing pipeline.

REQ-100-addendum-dispatch-hooks reqs 100-122.
Hooks are user-defined callables or shell commands that run before/after
each task dispatch. Pre-hooks transform prompts. Post-hooks transform results.

Import direction:
    hooks.py → imports engine (Task, TaskResult, DispatchUsage only)
"""

from __future__ import annotations

import logging
import subprocess
import time
from typing import Any

from rondo.config import RondoConfig
from rondo.engine import DispatchUsage, Task, TaskResult

logger = logging.getLogger(__name__)


def run_pre_dispatch_hooks(
    prompt: str,
    task: Task,
    config: RondoConfig,
) -> tuple[str, list[dict]]:
    """Run pre-dispatch hooks in order. Return (modified_prompt, trace).

    REQ-100-addendum reqs 100-105.
    Each hook receives the prompt and returns a modified prompt.
    Shell hooks (starting with '!') receive prompt on stdin, return on stdout.

    Returns:
        (final_prompt, hook_trace) where hook_trace is a list of
        {"hook": name, "duration_ms": N, "status": "ok"|"error"} dicts.
    """
    if not task.pre_dispatch:
        return prompt, []

    trace: list[dict] = []
    current_prompt = prompt

    for i, hook in enumerate(task.pre_dispatch):
        hook_name = _get_hook_name(hook, i, "pre")
        start = time.monotonic()

        try:
            if isinstance(hook, str) and hook.startswith("!"):
                current_prompt = _run_shell_hook(hook[1:].strip(), current_prompt)
            elif callable(hook):
                result = hook(current_prompt, task, config)
                if not isinstance(result, str):
                    raise TypeError(f"Pre-dispatch hook must return str, got {type(result).__name__}")
                current_prompt = result
            else:
                raise TypeError(f"Hook must be callable or '!shell_cmd', got {type(hook).__name__}")

            elapsed_ms = (time.monotonic() - start) * 1000
            trace.append({"hook": hook_name, "duration_ms": round(elapsed_ms, 1), "status": "ok"})

        except (OSError, TypeError, ValueError, subprocess.SubprocessError) as exc:
            elapsed_ms = (time.monotonic() - start) * 1000
            trace.append(
                {
                    "hook": hook_name,
                    "duration_ms": round(elapsed_ms, 1),
                    "status": "error",
                    "error": f"{type(exc).__name__}: {str(exc)[:200]}",
                }
            )
            raise HookError(hook_name, str(exc)) from exc

    return current_prompt, trace


def run_post_dispatch_hooks(
    result: TaskResult,
    usage: DispatchUsage,
    task: Task,
) -> tuple[TaskResult, list[dict]]:
    """Run post-dispatch hooks in order. Return (modified_result, trace).

    REQ-100-addendum reqs 110-114.
    Each hook receives the result and returns a modified result.
    If a hook raises, the ORIGINAL result is preserved (req 112).

    Returns:
        (final_result, hook_trace) where hook_trace is a list of dicts.
    """
    if not task.post_dispatch:
        return result, []

    trace: list[dict] = []
    current_result = result

    for i, hook in enumerate(task.post_dispatch):
        hook_name = _get_hook_name(hook, i, "post")
        start = time.monotonic()

        try:
            if not callable(hook):
                raise TypeError(f"Post-dispatch hook must be callable, got {type(hook).__name__}")

            hook_result = hook(current_result, usage)
            if not isinstance(hook_result, TaskResult):
                raise TypeError(f"Post-dispatch hook must return TaskResult, got {type(hook_result).__name__}")
            current_result = hook_result

            elapsed_ms = (time.monotonic() - start) * 1000
            trace.append({"hook": hook_name, "duration_ms": round(elapsed_ms, 1), "status": "ok"})

        except (OSError, TypeError, ValueError, AttributeError) as exc:
            elapsed_ms = (time.monotonic() - start) * 1000
            trace.append(
                {
                    "hook": hook_name,
                    "duration_ms": round(elapsed_ms, 1),
                    "status": "error",
                    "error": f"{type(exc).__name__}: {str(exc)[:200]}",
                }
            )
            # -- Req 112: preserve ORIGINAL result on hook failure
            logger.warning("Post-dispatch hook '%s' failed: %s. Original result preserved.", hook_name, exc)
            current_result = result

    return current_result, trace


class HookError(Exception):
    """Raised when a pre-dispatch hook fails (req 102: blocks dispatch)."""

    def __init__(self, hook_name: str, message: str) -> None:
        self.hook_name = hook_name
        super().__init__(f"Pre-dispatch hook '{hook_name}' failed: {message}")


def _run_shell_hook(command: str, stdin_data: str) -> str:
    """Run a shell hook command. Prompt on stdin, modified prompt on stdout.

    REQ-100-addendum req 104.
    Security: round files are user-authored Python — same trust level as
    the code calling Rondo. Shell hooks are explicitly user-defined.
    """
    result = subprocess.run(  # noqa: S603, S607 — user-defined hook command
        ["/bin/sh", "-c", command],
        input=stdin_data,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise subprocess.SubprocessError(f"Shell hook exited {result.returncode}: {result.stderr[:200]}")
    return result.stdout


def _get_hook_name(hook: Any, index: int, phase: str) -> str:
    """Derive a human-readable name for a hook."""
    if callable(hook) and hasattr(hook, "__name__"):
        return hook.__name__
    if isinstance(hook, str):
        return f"{phase}_shell_{index}"
    return f"{phase}_hook_{index}"


# -- sig: mgh-6201.cd.bd955f.h00k.d1sp4t
