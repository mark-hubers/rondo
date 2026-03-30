# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Rondo dispatch — send tasks to Claude via `claude -p`.

Rondo-REQ-100 reqs 12-28, Rondo-STD-108, Rondo-IFS-100, Rondo-STD-110.
This is the L1 layer: uses engine types (L0) and config settings (L0).

Session 91 Sprint 19: Split into 3 modules (Cursor Finding #144):
    dispatch_prompt.py — prompt building + constants
    dispatch_parse.py — JSON extraction + error classification
    dispatch.py (this) — core subprocess dispatch + env + model

All functions re-exported here for backward compatibility.
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

from rondo.audit import AuditConfig, AuditTrail
from rondo.config import RondoConfig
from rondo.dispatch_parse import (
    _collect_assistant_text,
    classify_error,
    extract_modified_files,
    extract_structured_output,
    parse_stream_json_events,
    parse_task_json,
)
from rondo.dispatch_prompt import (
    RONDO_DISPATCH_PROMPT,
    RONDO_RESULT_SCHEMA,
    build_prompt,
)
from rondo.engine import DispatchUsage, Task, TaskResult, validate_task
from rondo.sanitize import sanitize_task_result
from rondo.spool import spool_result

logger = logging.getLogger(__name__)

# -- Maximum size for raw_output in result files (Rondo-STD-110 R2)
_MAX_OUTPUT_BYTES = 1024 * 1024  # -- 1MB

# -- Rondo-REQ-100 req 071: CC version detection (cached per process)
_cc_version_cache: tuple[int, int, int] | None = None
_BARE_MIN_VERSION = (2, 1, 81)


def _attach_metrics(result: TaskResult, config: RondoConfig) -> None:
    """Attach metrics to result — ALWAYS-ON, every path."""
    try:
        from rondo.metrics import compute_metrics

        report = compute_metrics(audit_dir=config.audit_dir)
        result.metrics = report.to_dict()
    except (ImportError, OSError, TypeError):
        pass


def _get_audit_trail(config: RondoConfig) -> AuditTrail | None:
    """Create AuditTrail if audit_dir is configured — STD-113."""
    if not config.audit_dir:
        return None
    try:
        return AuditTrail(config=AuditConfig(audit_dir=config.audit_dir))
    except (OSError, TypeError) as exc:
        logger.debug("Audit trail init failed (non-fatal): %s", exc)
        return None


def detect_cc_version(binary: str = "claude") -> tuple[int, int, int] | None:
    """Detect Claude Code version via `claude --version`.

    Returns (major, minor, patch) or None if unavailable.
    Caches result — called once per process lifetime.
    """
    global _cc_version_cache  # noqa: PLW0603
    if _cc_version_cache is not None:
        return _cc_version_cache
    try:
        result = subprocess.run(
            [binary, "--version"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        if result.returncode == 0:
            version_str = result.stdout.strip().split()[0]
            parts = version_str.split(".")
            _cc_version_cache = (int(parts[0]), int(parts[1]), int(parts[2]))
            return _cc_version_cache
    except (FileNotFoundError, IndexError, ValueError, subprocess.TimeoutExpired):
        pass
    return None


# ──────────────────────────────────────────────────────────────────
#  Environment Preparation — Rondo-REQ-100 reqs 13, 17, 18
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
#  Model Resolution — Rondo-REQ-100 reqs 20-23
# ──────────────────────────────────────────────────────────────────


VALID_MODELS: set[str] = {"opus", "sonnet", "haiku", "opus[1m]", "sonnet[1m]"}


def resolve_model(
    cli_model: str | None,
    task: Task,
    config: RondoConfig,
) -> str:
    """COALESCE: CLI → task.model → config.default_model.

    Rondo-REQ-100 req 21: CLI override → task hint → config default.
    Validates against VALID_MODELS — fails fast with clear message.
    """
    model = cli_model or task.model or config.default_model
    if model not in VALID_MODELS:
        raise ValueError(f"Invalid model '{model}' for task '{task.name}'. Valid: {sorted(VALID_MODELS)}")
    return model


# ──────────────────────────────────────────────────────────────────
#  Result Saving — Rondo-REQ-100 req 15, Rondo-STD-110 S5, R2
# ──────────────────────────────────────────────────────────────────


def save_result(
    result: TaskResult,
    usage: DispatchUsage,
    results_dir: str,
) -> str:
    """Save task result to JSON file with restrictive permissions.

    Rondo-STD-110 S5: file permissions 0o600.
    Rondo-STD-110 R2: raw_output truncated to 1MB.
    Rondo-STD-108 rule 8: no credentials in output (enforced by env prep).
    """
    out_dir = Path(results_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # -- Build result dict
    data = asdict(result)

    # -- Truncate raw_output if needed (Rondo-STD-110 R2)
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
#  Dispatch — Rondo-REQ-100 reqs 12-28, Rondo-STD-108, Rondo-STD-110
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

    # -- Pre-dispatch validation (Rondo-STD-108 defensive check)
    task_errors = validate_task(task)
    if task_errors:
        msg = "; ".join(task_errors)
        logger.warning("Task '%s' failed validation: %s", task.name, msg)
        result = TaskResult(
            task_name=task.name,
            status="error",
            error_code="ERR_INTERNAL",
            error_message=f"Validation failed: {msg}",
            raw_output="",
            model="",
            auth_mode=config.auth,
            timestamp=timestamp,
        )
        _attach_metrics(result, config)
        return result, DispatchUsage(task_name=task.name)

    model = resolve_model(cli_model, task, config)

    # -- Case 1: Dry run (Rondo-REQ-100 req 16)
    if config.dry_run:
        prompt = build_prompt(task) if not task.is_auto else f"[AUTO] {task.name}"
        result = TaskResult(
            task_name=task.name,
            status="skipped",
            prompt_sent=prompt,
            raw_output="",
            model=model,
            auth_mode=config.auth,
            timestamp=timestamp,
        )
        _attach_metrics(result, config)
        return result, DispatchUsage(task_name=task.name, model=model)

    # -- Case 2: Auto task (Rondo-REQ-100 req 4)
    if task.is_auto:
        r, u = _dispatch_auto(task, config, model, timestamp)
        _attach_metrics(r, config)
        return r, u

    # -- Case 3: Interactive task (Rondo-REQ-100 reqs 12-28)
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

    Rondo-STD-110 S1: command as list, never shell=True.
    Rondo-STD-110 R1: SIGTERM-first kill sequence.
    Rondo-STD-108: all exceptions caught and converted to error results.
    """
    prompt = build_prompt(task)
    env = prepare_env(config)
    start = time.monotonic()
    cmd = _build_subprocess_cmd(config, prompt, model)

    # -- STD-113: record INTENT before dispatch (crash-safe)
    audit_trail = _get_audit_trail(config)
    audit_record = None
    if audit_trail:
        audit_record = audit_trail.record_intent(
            task_name=task.name,
            round_name="",
            model=model,
            prompt=prompt,
        )

    try:
        stdout, stderr, returncode, timed_out = _run_subprocess(cmd, env, config.task_timeout_sec)
        duration = time.monotonic() - start

        # -- Handle timeout
        if timed_out:
            result, usage = _make_error_result(
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
            return _finalize_dispatch(result, usage, config, audit_trail, audit_record)

        # -- Handle non-zero exit (Rondo-REQ-100 req 27)
        if returncode != 0:
            result, usage = _make_error_result(
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
            return _finalize_dispatch(result, usage, config, audit_trail, audit_record)

        # -- Handle empty stdout (Rondo-STD-108: ERR_EMPTY_OUTPUT)
        if not stdout or not stdout.strip():
            result, usage = _make_error_result(
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
            return _finalize_dispatch(result, usage, config, audit_trail, audit_record)

        # -- Parse and build success result
        return _parse_and_build_result(
            task,
            config,
            model,
            timestamp,
            prompt,
            stdout,
            stderr,
            returncode,
            duration,
            audit_trail=audit_trail,
            audit_record=audit_record,
        )

    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        # -- Rondo-STD-108 rule 9: subprocess + I/O failures caught
        logger.warning("Interactive dispatch failed for task %s: %s", task.name, exc)
        result, usage = _make_error_result(
            task.name,
            error_code="ERR_INTERNAL",
            error_message=str(exc),
            prompt=prompt,
            duration=time.monotonic() - start,
            model=model,
            auth=config.auth,
            timestamp=timestamp,
        )
        return _finalize_dispatch(result, usage, config, audit_trail, audit_record)


def _finalize_dispatch(
    result: TaskResult,
    usage: DispatchUsage,
    config: RondoConfig,
    audit_trail: AuditTrail | None,
    audit_record: object | None,
) -> tuple[TaskResult, DispatchUsage]:
    """Shared ALWAYS-ON pipeline for ALL dispatch paths (success + error).

    Cursor review (Session 92): error paths were skipping audit OUTCOME,
    sanitize, spool, and history. This function runs on every path.
    """
    # -- STD-113: set dispatch_id on result
    if audit_record:
        result.dispatch_id = getattr(audit_record, "dispatch_id", "")

    # -- STD-113: record audit OUTCOME
    if audit_trail and audit_record:
        try:
            audit_trail.record_outcome(
                dispatch_id=audit_record.dispatch_id,
                task_name=result.task_name,
                model=result.model,
                status=result.status,
                exit_code=result.exit_code or 0,
                cost_usd=usage.cost_usd,
                duration_sec=result.duration_sec,
                raw_output=result.raw_output,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                files_modified=result.files_modified,
            )
        except (OSError, TypeError) as exc:
            logger.debug("Audit outcome failed (non-fatal): %s", exc)

    # -- STD-114: sanitize result
    try:
        result, _sr = sanitize_task_result(result, config=None)
    except (TypeError, AttributeError) as exc:
        logger.debug("Sanitize failed (non-fatal): %s", exc)

    # -- REQ-101 req 045: spool only for async/overnight callers
    if config.spool_enabled:
        try:
            test_dir = os.environ.get("RONDO_TEST_DIR")
            _spool_dir = os.path.join(test_dir, "spool") if test_dir else os.path.expanduser("~/.rondo/spool")
            spool_result(
                task_name=result.task_name,
                result=asdict(result),
                spool_dir=_spool_dir,
            )
        except (OSError, TypeError) as exc:
            logger.debug("Spool write failed (non-fatal): %s", exc)

    # -- ALWAYS-ON: embed metrics in every result (no second call)
    _attach_metrics(result, config)

    # -- REQ-104: log to history
    _log_to_history(result, usage, config)

    return result, usage


def _build_subprocess_cmd(
    config: RondoConfig,
    prompt: str,
    model: str,
    *,
    task: Task | None = None,
) -> list[str]:
    """Build the claude -p command as a list (Rondo-STD-110 S1: never shell=True).

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

    # -- Rondo-REQ-100 req 071-073: --bare for automated dispatch
    # -- Task can opt out with bare=False (req 073: Caliber enforcement needed)
    # -- Only add --bare when CC version >= 2.1.81 (req 071)
    use_bare = config.bare
    if task and task.bare is not None:
        use_bare = task.bare
    if use_bare:
        cc_ver = _cc_version_cache or detect_cc_version(config.claude_binary)
        if cc_ver and cc_ver >= _BARE_MIN_VERSION:
            cmd.append("--bare")
        else:
            logger.info("--bare skipped: CC version %s < %s", cc_ver, _BARE_MIN_VERSION)

    # -- REQ-100 reqs 022-024: tool_mode controls tool access
    if task:
        if task.tool_mode == "none":
            cmd.extend(["--tools", ""])
        elif task.tool_mode == "sandbox":
            cmd.append("--dangerously-skip-permissions")
        # -- "default" adds no flags

    # -- REQ-100 reqs 078-081: cost, output, session control
    _add_output_flags(cmd, config)

    return cmd


def _add_output_flags(cmd: list[str], config: RondoConfig) -> None:
    """Add cost/output/session flags — extracted for complexity (Rondo-REQ-100 reqs 078-081)."""
    if config.max_budget_usd is not None:
        cmd.extend(["--max-budget-usd", str(config.max_budget_usd)])
    # -- "auto" → use Rondo's canonical schema/prompt constants
    schema = RONDO_RESULT_SCHEMA if config.json_schema == "auto" else config.json_schema
    if schema:
        cmd.extend(["--json-schema", schema])
    prompt_val = RONDO_DISPATCH_PROMPT if config.dispatch_system_prompt == "auto" else config.dispatch_system_prompt
    if prompt_val:
        cmd.extend(["--system-prompt", prompt_val])
    # -- req 081: don't clutter CC session store
    cmd.append("--no-session-persistence")


def _run_subprocess(
    cmd: list[str],
    env: dict[str, str],
    timeout_sec: int,
) -> tuple[str, str, int, bool]:
    """Launch subprocess with SIGTERM-first kill timer.

    Returns (stdout, stderr, returncode, timed_out).
    Rondo-STD-110 R1: Popen for SIGTERM-first kill sequence.
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
    *,
    audit_trail: AuditTrail | None = None,
    audit_record: object | None = None,
) -> tuple[TaskResult, DispatchUsage]:
    """Parse stream-json output and build success/partial TaskResult.

    Extracted from _dispatch_interactive() for complexity reduction.
    STD-113: records audit outcome. STD-114: sanitizes stored result.
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

    # -- Rondo-REQ-100 req 079: prefer StructuredOutput over text JSON parsing
    assistant_text = _collect_assistant_text(events)
    parsed = extract_structured_output(events)
    if parsed is None:
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

    # -- ALWAYS-ON: shared finalizer for all paths (Cursor Session 92 review)
    return _finalize_dispatch(result, usage, config, audit_trail, audit_record)


def _log_to_history(
    result: TaskResult,
    usage: DispatchUsage,
    config: RondoConfig,
) -> None:
    """Log dispatch result to JSONL history — Rondo-REQ-104 req 001."""
    try:
        from rondo.history import DispatchRecord, log_dispatch

        record = DispatchRecord(
            round_name="",  # -- set by caller if available
            task_name=result.task_name,
            model=result.model,
            status=result.status,
            cost_usd=usage.cost_usd,
            duration_sec=result.duration_sec,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            confidence=0.0,  # -- set from parsed JSON if available
            error_code=result.error_code,
            budget_exceeded=usage.budget_exceeded,
        )
        history_dir = str(Path(config.results_dir).parent / "history")
        log_dispatch(record, history_dir)
    except (ImportError, OSError, TypeError) as exc:
        logger.debug("History logging failed (non-fatal): %s", exc)


# -- sig: mgh-6201.cd.bd955f.e969.bc3711
