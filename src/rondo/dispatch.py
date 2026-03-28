# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Rondo dispatch — send tasks to Claude via `claude -p`, parse results.

REQ-001 reqs 12-28, STD-001, ACE-IFS-001, STD-003.
This is the L1 layer: uses engine types (L0) and config settings (L0).

Import direction:
    engine.py → (no rondo imports)
    config.py → (no rondo imports)
    dispatch.py → imports engine + config
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import threading
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from rondo.config import RondoConfig
from rondo.engine import DispatchUsage, Task, TaskResult, validate_task

logger = logging.getLogger(__name__)

# -- Maximum size for raw_output in result files (STD-003 R2)
_MAX_OUTPUT_BYTES = 1024 * 1024  # -- 1MB


# ──────────────────────────────────────────────────────────────────
#  Prompt Building — REQ-001 reqs 12, 24
# ──────────────────────────────────────────────────────────────────


def build_prompt(task: Task) -> str:
    """Build the dispatch prompt from a task's three-field contract.

    Includes JSON output instructions (REQ-001 req 24).
    """
    parts = [f"# Rondo Task: {task.name}"]

    if task.description:
        parts.append(f"\n**Description:** {task.description}")

    if task.context_files:
        files = ", ".join(task.context_files)
        parts.append(f"\n**Read these files first:** {files}")

    parts.append(f"\n**Do:** {task.instruction}")
    parts.append(f"\n**Done when:** {task.done_when}")

    parts.append(
        "\n---\n"
        "**Output format:** Respond with a JSON block at the end:\n"
        "```json\n"
        '{"status": "done"|"blocked", "confidence": 0.0-1.0, '
        '"result": "what you did", "question": "if blocked, what you need"}\n'
        "```"
    )

    return "\n".join(parts)


# ──────────────────────────────────────────────────────────────────
#  Environment Preparation — REQ-001 reqs 13, 17, 18
# ──────────────────────────────────────────────────────────────────


def prepare_env(config: RondoConfig) -> dict[str, str]:
    """Build child process environment.

    Always strips CLAUDECODE (req 13).
    Strips ANTHROPIC_API_KEY when auth=max (req 17).
    Keeps ANTHROPIC_API_KEY when auth=api (req 18).
    """
    env = dict(os.environ)

    # -- Always strip CLAUDECODE (nested session guard)
    env.pop("CLAUDECODE", None)

    # -- Auth-based key handling
    if config.auth == "max":
        env.pop("ANTHROPIC_API_KEY", None)

    return env


# ──────────────────────────────────────────────────────────────────
#  Model Resolution — REQ-001 reqs 20-23
# ──────────────────────────────────────────────────────────────────


VALID_MODELS: set[str] = {"opus", "sonnet", "haiku", "opus[1m]", "sonnet[1m]"}


def resolve_model(
    cli_model: str | None,
    task: Task,
    config: RondoConfig,
) -> str:
    """COALESCE: CLI → task.model → config.default_model.

    REQ-001 req 21: CLI override → task hint → config default.
    Validates against VALID_MODELS — fails fast with clear message.
    """
    model = cli_model or task.model or config.default_model
    if model not in VALID_MODELS:
        raise ValueError(f"Invalid model '{model}' for task '{task.name}'. Valid: {sorted(VALID_MODELS)}")
    return model


# ──────────────────────────────────────────────────────────────────
#  Task JSON Parsing — REQ-001 reqs 25, 26
# ──────────────────────────────────────────────────────────────────


def parse_task_json(text: str) -> dict[str, Any] | None:
    """Extract the last valid JSON block from Claude's text output.

    Looks for JSON blocks in code fences or bare JSON objects.
    Returns None if no valid JSON found (REQ-001 req 26 → "partial").
    """
    # -- Try code-fenced JSON blocks first (last one wins)
    fenced = re.findall(r"```(?:json)?\s*\n(.*?)\n\s*```", text, re.DOTALL)
    for block in reversed(fenced):
        try:
            parsed = json.loads(block.strip())
            if isinstance(parsed, dict) and "status" in parsed:
                return parsed
        except (json.JSONDecodeError, ValueError):
            continue

    # -- Try bare JSON objects (last one wins)
    bare = re.findall(r"\{[^{}]*\}", text)
    for block in reversed(bare):
        try:
            parsed = json.loads(block)
            if isinstance(parsed, dict) and "status" in parsed:
                return parsed
        except (json.JSONDecodeError, ValueError):
            continue

    return None


# ──────────────────────────────────────────────────────────────────
#  Error Classification — STD-001 error categories
# ──────────────────────────────────────────────────────────────────


def classify_error(stderr: str) -> str:
    """Classify error from stderr content (STD-001 stderr patterns)."""
    if not stderr:
        return "ERR_SUBPROCESS"

    lower = stderr.lower()

    if "credit balance is too low" in lower or "invalid api key" in lower:
        return "ERR_AUTH"

    if "cannot be launched inside another" in lower:
        return "ERR_NESTED_SESSION"

    if "rate limit" in lower or "rate_limit" in lower:
        return "ERR_RATE_LIMIT"

    return "ERR_SUBPROCESS"


# ──────────────────────────────────────────────────────────────────
#  Stream-JSON Parsing — ACE-IFS-001 reqs 1-10
# ──────────────────────────────────────────────────────────────────


def parse_stream_json_events(
    lines: list[str],
    task_name: str = "",
) -> tuple[list[dict[str, Any]], DispatchUsage]:
    """Parse stream-json output line by line (ACE-IFS-001 req 1).

    Returns:
        Tuple of (all_events, dispatch_usage).
        DispatchUsage has defaults for missing fields (ACE-IFS-001 req 9).
    """
    events: list[dict[str, Any]] = []
    usage = DispatchUsage(task_name=task_name)

    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue

        events.append(event)
        event_type = event.get("type", "")

        # -- rate_limit_event → DispatchUsage rate limit fields (ACE-IFS-001 req 2)
        if event_type == "rate_limit_event":
            info = event.get("rate_limit_info", {})
            usage = DispatchUsage(
                task_name=usage.task_name,
                model=usage.model,
                cost_usd=usage.cost_usd,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cache_read_tokens=usage.cache_read_tokens,
                cache_create_tokens=usage.cache_create_tokens,
                duration_ms=usage.duration_ms,
                duration_api_ms=usage.duration_api_ms,
                num_turns=usage.num_turns,
                context_window=usage.context_window,
                rate_limit_status=info.get("status", "unknown"),
                is_using_overage=info.get("isUsingOverage", False),
                rate_limit_resets_at=info.get("resetsAt", 0),
            )

        # -- result event → DispatchUsage cost/token/duration (ACE-IFS-001 req 3)
        elif event_type == "result":
            u = event.get("usage", {})
            model_usage = event.get("modelUsage", {})
            # -- Get context window from first model entry
            ctx_window = 0
            for model_info in model_usage.values():
                ctx_window = model_info.get("contextWindow", 0)
                break

            usage = DispatchUsage(
                task_name=usage.task_name,
                model=usage.model,
                cost_usd=event.get("total_cost_usd", 0.0),
                input_tokens=u.get("input_tokens", 0),
                output_tokens=u.get("output_tokens", 0),
                cache_read_tokens=u.get("cache_read_input_tokens", 0),
                cache_create_tokens=u.get("cache_creation_input_tokens", 0),
                duration_ms=event.get("duration_ms", 0),
                duration_api_ms=event.get("duration_api_ms", 0),
                num_turns=event.get("num_turns", 0),
                context_window=ctx_window,
                rate_limit_status=usage.rate_limit_status,
                is_using_overage=usage.is_using_overage,
                rate_limit_resets_at=usage.rate_limit_resets_at,
            )

    return events, usage


def _collect_assistant_text(events: list[dict[str, Any]]) -> str:
    """Extract concatenated assistant text from stream-json events."""
    parts: list[str] = []
    for event in events:
        if event.get("type") != "assistant":
            continue
        message = event.get("message", {})
        content = message.get("content", [])
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
    return "\n".join(parts)


# ──────────────────────────────────────────────────────────────────
#  File Extraction — STD-001 files_modified
# ──────────────────────────────────────────────────────────────────


def extract_modified_files(raw_output: str) -> list[str]:
    """Extract file paths from Claude's output (heuristic).

    STD-001: populated by parsing raw_output for file paths.
    Used by detect_conflicts() in parallel dispatch (advisory).
    """
    # -- Match file paths with known extensions in Claude output.
    # -- Captures optional leading ./ or /, path segments (dir/dir/),
    # -- and filename with extension. Used for conflict detection in parallel mode.
    pattern = (
        r"(?:^|\s)"
        r"((?:\./|/)?(?:[\w.-]+/)*[\w.-]+\."
        r"(?:py|md|toml|json|sql|sh|ts|js|yaml|yml))"
        r"\b"
    )
    matches = re.findall(pattern, raw_output)
    # -- Deduplicate, preserve order
    seen: set[str] = set()
    result: list[str] = []
    for m in matches:
        if m not in seen:
            seen.add(m)
            result.append(m)
    return result


# ──────────────────────────────────────────────────────────────────
#  Result Saving — REQ-001 req 15, STD-003 S5, R2
# ──────────────────────────────────────────────────────────────────


def save_result(
    result: TaskResult,
    usage: DispatchUsage,
    results_dir: str,
) -> str:
    """Save task result to JSON file with restrictive permissions.

    STD-003 S5: file permissions 0o600.
    STD-003 R2: raw_output truncated to 1MB.
    STD-001 rule 8: no credentials in output (enforced by env prep).
    """
    out_dir = Path(results_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # -- Build result dict
    data = asdict(result)

    # -- Truncate raw_output if needed (STD-003 R2)
    if len(data.get("raw_output", "")) > _MAX_OUTPUT_BYTES:
        data["raw_output"] = data["raw_output"][:_MAX_OUTPUT_BYTES] + "\n... [TRUNCATED — exceeded 1MB limit]"

    # -- Add usage data
    data["usage"] = asdict(usage)

    # -- Remove callable fields (not serializable)
    # -- TaskResult doesn't have callables, but safety check
    for key in list(data.keys()):
        if callable(data[key]):
            data[key] = str(data[key])

    # -- Write with restrictive permissions
    safe_name = re.sub(r"[^\w\-.]", "_", result.task_name)
    filepath = out_dir / f"task-{safe_name}.json"
    filepath.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    filepath.chmod(0o600)

    return str(filepath)


# ──────────────────────────────────────────────────────────────────
#  Dispatch — REQ-001 reqs 12-28, STD-001, STD-003
# ──────────────────────────────────────────────────────────────────


def dispatch_task(
    task: Task,
    config: RondoConfig,
    *,
    cli_model: str | None = None,
) -> tuple[TaskResult, DispatchUsage]:
    """Dispatch a single task. Returns (TaskResult, DispatchUsage).

    Handles three cases:
        1. dry_run — return prompt without invoking
        2. auto task — call task.auto_fn() directly
        3. interactive task — invoke claude -p subprocess
    """
    timestamp = datetime.now(UTC).isoformat()

    # -- Pre-dispatch validation (STD-001 defensive check)
    task_errors = validate_task(task)
    if task_errors:
        msg = "; ".join(task_errors)
        logger.warning("Task '%s' failed validation: %s", task.name, msg)
        return (
            TaskResult(
                task_name=task.name,
                status="error",
                error_code="ERR_INTERNAL",
                error_message=f"Validation failed: {msg}",
                raw_output="",
                model="",
                auth_mode=config.auth,
                timestamp=timestamp,
            ),
            DispatchUsage(task_name=task.name),
        )

    model = resolve_model(cli_model, task, config)

    # -- Case 1: Dry run (REQ-001 req 16)
    if config.dry_run:
        prompt = build_prompt(task) if not task.is_auto else f"[AUTO] {task.name}"
        return (
            TaskResult(
                task_name=task.name,
                status="skipped",
                prompt_sent=prompt,
                raw_output="",
                model=model,
                auth_mode=config.auth,
                timestamp=timestamp,
            ),
            DispatchUsage(task_name=task.name, model=model),
        )

    # -- Case 2: Auto task (REQ-001 req 4)
    if task.is_auto:
        return _dispatch_auto(task, config, model, timestamp)

    # -- Case 3: Interactive task (REQ-001 reqs 12-28)
    return _dispatch_interactive(task, config, model, timestamp)


def _dispatch_auto(
    task: Task,
    config: RondoConfig,
    model: str,
    timestamp: str,
) -> tuple[TaskResult, DispatchUsage]:
    """Execute an auto task by calling its callable directly."""
    start = time.monotonic()
    try:
        if task.auto_fn is None:
            raise ValueError(f"Task '{task.name}' has no auto_fn")
        passed, detail = task.auto_fn()
        status = "done" if passed else "error"
        return (
            TaskResult(
                task_name=task.name,
                status=status,
                raw_output=detail,
                duration_sec=time.monotonic() - start,
                model=model,
                auth_mode=config.auth,
                timestamp=timestamp,
            ),
            DispatchUsage(task_name=task.name, model=model),
        )
    except (TypeError, ValueError, RuntimeError, OSError, KeyError, AttributeError) as exc:
        logger.warning("Auto task %s failed: %s", task.name, exc)
        return (
            TaskResult(
                task_name=task.name,
                status="error",
                error_code="ERR_INTERNAL",
                error_message=str(exc),
                raw_output="",
                duration_sec=time.monotonic() - start,
                model=model,
                auth_mode=config.auth,
                timestamp=timestamp,
            ),
            DispatchUsage(task_name=task.name, model=model),
        )


def _make_error_result(
    task_name: str,
    *,
    error_code: str,
    error_message: str,
    prompt: str,
    raw_output: str = "",
    stderr: str = "",
    exit_code: int | None = None,
    duration: float = 0.0,
    model: str = "",
    auth: str = "",
    timestamp: str = "",
) -> tuple[TaskResult, DispatchUsage]:
    """Build a standardized error TaskResult + empty DispatchUsage.

    Extracted to reduce cyclomatic complexity in _dispatch_interactive().
    Every error path returns the same shaped result.
    """
    return (
        TaskResult(
            task_name=task_name,
            status="error",
            error_code=error_code,
            error_message=error_message,
            prompt_sent=prompt,
            raw_output=raw_output,
            stderr=stderr,
            exit_code=exit_code,
            duration_sec=duration,
            model=model,
            auth_mode=auth,
            timestamp=timestamp,
        ),
        DispatchUsage(task_name=task_name, model=model),
    )


def _dispatch_interactive(
    task: Task,
    config: RondoConfig,
    model: str,
    timestamp: str,
) -> tuple[TaskResult, DispatchUsage]:
    """Execute an interactive task via claude -p subprocess.

    STD-003 S1: command as list, never shell=True.
    STD-003 R1: SIGTERM-first kill sequence.
    STD-001: all exceptions caught and converted to error results.
    """
    prompt = build_prompt(task)
    env = prepare_env(config)
    start = time.monotonic()
    cmd = _build_subprocess_cmd(config, prompt, model)

    try:
        stdout, stderr, returncode, timed_out = _run_subprocess(cmd, env, config.task_timeout_sec)
        duration = time.monotonic() - start

        # -- Handle timeout
        if timed_out:
            return _make_error_result(
                task.name,
                error_code="ERR_TIMEOUT",
                error_message=f"Task timed out after {config.task_timeout_sec}s",
                prompt=prompt,
                raw_output=stdout,
                stderr=stderr,
                duration=duration,
                model=model,
                auth=config.auth,
                timestamp=timestamp,
            )

        # -- Handle non-zero exit (REQ-001 req 27)
        if returncode != 0:
            return _make_error_result(
                task.name,
                error_code=classify_error(stderr),
                error_message=stderr[:500] if stderr else "Non-zero exit code",
                prompt=prompt,
                raw_output=stdout,
                stderr=stderr,
                exit_code=returncode,
                duration=duration,
                model=model,
                auth=config.auth,
                timestamp=timestamp,
            )

        # -- Handle empty stdout (STD-001: ERR_EMPTY_OUTPUT)
        if not stdout or not stdout.strip():
            return _make_error_result(
                task.name,
                error_code="ERR_EMPTY_OUTPUT",
                error_message="Empty stdout — possible auth failure",
                prompt=prompt,
                stderr=stderr,
                exit_code=returncode,
                duration=duration,
                model=model,
                auth=config.auth,
                timestamp=timestamp,
            )

        # -- Parse and build success result
        return _parse_and_build_result(task, config, model, timestamp, prompt, stdout, stderr, returncode, duration)

    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        # -- STD-001 rule 9: subprocess + I/O failures caught
        logger.warning("Interactive dispatch failed for task %s: %s", task.name, exc)
        return _make_error_result(
            task.name,
            error_code="ERR_INTERNAL",
            error_message=str(exc),
            prompt=prompt,
            duration=time.monotonic() - start,
            model=model,
            auth=config.auth,
            timestamp=timestamp,
        )


def _build_subprocess_cmd(
    config: RondoConfig,
    prompt: str,
    model: str,
    *,
    task: Task | None = None,
) -> list[str]:
    """Build the claude -p command as a list (STD-003 S1: never shell=True).

    REQ-100 reqs 022-024: tool_mode controls --tools/--dangerously-skip-permissions.
    REQ-100 reqs 047-049: --permission-mode from config.
    REQ-100 reqs 071-073: --bare for automated dispatch.
    """
    cmd = [
        config.claude_binary,
        "-p",
        prompt,
        "--model",
        model,
        "--output-format",
        config.output_format,
    ]
    if config.effort:
        cmd.extend(["--effort", config.effort])
    if config.permission_mode:
        cmd.extend(["--permission-mode", config.permission_mode])

    # -- REQ-100 req 071-073: --bare for automated dispatch
    # -- Task can opt out with bare=False (req 073: Caliber enforcement needed)
    use_bare = config.bare
    if task and task.bare is not None:
        use_bare = task.bare
    if use_bare:
        cmd.append("--bare")

    # -- REQ-100 reqs 022-024: tool_mode controls tool access
    if task:
        if task.tool_mode == "none":
            cmd.extend(["--tools", ""])
        elif task.tool_mode == "sandbox":
            cmd.append("--dangerously-skip-permissions")
        # -- "default" adds no flags

    return cmd


def _run_subprocess(
    cmd: list[str],
    env: dict[str, str],
    timeout_sec: int,
) -> tuple[str, str, int, bool]:
    """Launch subprocess with SIGTERM-first kill timer.

    Returns (stdout, stderr, returncode, timed_out).
    STD-003 R1: Popen for SIGTERM-first kill sequence.
    """
    proc = subprocess.Popen(  # pylint: disable=consider-using-with
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )

    timed_out = threading.Event()

    def _kill_on_timeout() -> None:
        timed_out.set()
        proc.terminate()  # -- SIGTERM
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()  # -- SIGKILL after 5s

    timer = threading.Timer(timeout_sec, _kill_on_timeout)
    timer.start()
    try:
        stdout, stderr = proc.communicate()
    finally:
        timer.cancel()

    return stdout or "", stderr or "", proc.returncode, timed_out.is_set()


def _parse_and_build_result(
    task: Task,
    config: RondoConfig,
    model: str,
    timestamp: str,
    prompt: str,
    stdout: str,
    stderr: str,
    returncode: int,
    duration: float,
) -> tuple[TaskResult, DispatchUsage]:
    """Parse stream-json output and build success/partial TaskResult.

    Extracted from _dispatch_interactive() for complexity reduction.
    """
    events, usage = parse_stream_json_events(stdout.split("\n"), task_name=task.name)
    usage = DispatchUsage(
        task_name=task.name,
        model=model,
        cost_usd=usage.cost_usd,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cache_read_tokens=usage.cache_read_tokens,
        cache_create_tokens=usage.cache_create_tokens,
        duration_ms=usage.duration_ms,
        duration_api_ms=usage.duration_api_ms,
        num_turns=usage.num_turns,
        context_window=usage.context_window,
        rate_limit_status=usage.rate_limit_status,
        is_using_overage=usage.is_using_overage,
        rate_limit_resets_at=usage.rate_limit_resets_at,
    )

    assistant_text = _collect_assistant_text(events)
    parsed = parse_task_json(assistant_text)

    if parsed is not None:
        task_status = parsed.get("status", "done")
        if task_status not in ("done", "blocked"):
            task_status = "done"
    else:
        task_status = "partial"

    result = TaskResult(
        task_name=task.name,
        status=task_status,
        error_code="ERR_MALFORMED_JSON" if parsed is None else None,
        prompt_sent=prompt,
        raw_output=assistant_text,
        parsed_result=parsed,
        stderr=stderr,
        exit_code=returncode,
        duration_sec=duration,
        model=model,
        auth_mode=config.auth,
        timestamp=timestamp,
        cost_usd=usage.cost_usd,
        files_modified=extract_modified_files(assistant_text),
    )

    return result, usage


# -- sig: mgh-6201.cd.bd955f.e969.bc3711
