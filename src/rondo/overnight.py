# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Rondo overnight — phase scheduler, watchdog response, usage gating.

Rondo-REQ-101 reqs 10-28.
This is the L3 layer: orchestrates run_round (L2) across phases.

Import direction:
    engine.py → (no rondo imports)
    config.py → (no rondo imports)
    dispatch.py → imports engine + config
    runner.py → imports engine + config + dispatch
    parallel.py → imports engine + config + dispatch
    overnight.py → imports engine + config + runner
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from rondo.config import RondoConfig
from rondo.engine import DispatchUsage, Round, RoundResult
from rondo.preflight import run_preflight
from rondo.runner import run_round
from rondo.spool import spool_result

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────
#  OvernightResult — aggregated output
# ──────────────────────────────────────────────────────────────────


@dataclass
class OvernightResult:  # pylint: disable=too-many-instance-attributes
    """Everything a consumer needs from an overnight run."""

    # -- identity
    mode: str = ""
    started_at: str = ""
    completed_at: str = ""
    duration_sec: float = 0.0

    # -- phase results (one per phase)
    phase_results: list[RoundResult] = field(default_factory=list)

    # -- event log
    event_log: list[dict] = field(default_factory=list)

    # -- aggregated
    total_cost_usd: float = 0.0
    status: str = "pending"  # -- done, partial, error, stopped


# ──────────────────────────────────────────────────────────────────
#  EventLog — rolling 100-entry JSON file (Rondo-REQ-101 req 18)
# ──────────────────────────────────────────────────────────────────


class EventLog:
    """Rolling event log — keeps last 100 entries (Rondo-REQ-101 req 18)."""

    MAX_ENTRIES = 100

    def __init__(self, log_path: str | None = None):
        self.log_path = log_path
        self.entries: list[dict] = []
        if log_path:
            self._load()

    def _load(self) -> None:
        """Load existing entries from disk."""
        if not self.log_path:
            return
        path = Path(self.log_path)
        if path.exists():
            try:
                self.entries = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, ValueError):
                self.entries = []

    def append(self, event: dict) -> None:
        """Add event, trim to max entries."""
        self.entries.append(event)
        if len(self.entries) > self.MAX_ENTRIES:
            self.entries = self.entries[-self.MAX_ENTRIES :]

    def save(self) -> None:
        """Persist to disk."""
        if not self.log_path:
            return
        path = Path(self.log_path)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        path.write_text(json.dumps(self.entries, indent=2, default=str), encoding="utf-8")


# ──────────────────────────────────────────────────────────────────
#  Usage gating — Rondo-REQ-101 reqs 24-28
# ──────────────────────────────────────────────────────────────────


def check_usage_gate(
    usage: DispatchUsage,
    on_overage: str = "continue",
) -> str:
    """Check rate limit status and return action.

    Rondo-REQ-101 req 24: check most recent rate_limit_event.
    Rondo-REQ-101 req 25: overage action (continue/pause/stop).
    Rondo-REQ-101 req 26: blocked status → blocked action.

    Returns:
        "continue" — proceed normally
        "stop" — end overnight run
        "pause" — wait for rate limit reset
        "blocked" — rate limit blocked (must wait)
    """
    # -- Rondo-REQ-101 req 26: blocked status always blocks
    if usage.rate_limit_status == "blocked":
        return "blocked"

    # -- Rondo-REQ-101 req 25: overage check
    if usage.is_using_overage:
        return on_overage

    return "continue"


# ──────────────────────────────────────────────────────────────────
#  run_overnight() — Rondo-REQ-101 reqs 10-28
# ──────────────────────────────────────────────────────────────────


def _overnight_preflight(config: RondoConfig) -> bool:
    """Run preflight before overnight batch — Rondo-REQ-103 req 014."""
    try:
        preflight = run_preflight(config=config)
        if not preflight.can_proceed:
            logger.error("Overnight preflight FAILED: %s", preflight.errors)
            return False
        if preflight.warnings:
            logger.warning("Overnight preflight warnings: %s", preflight.warnings)
        return True
    except (ImportError, OSError) as exc:
        logger.warning("Preflight check failed (continuing): %s", exc)
        return True


def run_overnight(  # pylint: disable=too-many-branches
    phases: list[Round],
    config: RondoConfig,
    *,
    mode: str | None = None,
    modes: dict[str, list[str]] | None = None,
    event_log_path: str | None = None,
) -> OvernightResult:
    """Execute overnight automation: phases → usage gating → event logging.

    Rondo-REQ-101 req 10: accept list of round definitions.
    Rondo-REQ-101 req 11: phases execute sequentially.
    Rondo-REQ-101 req 12: phase failure doesn't block next.
    Rondo-REQ-101 req 13-15: mode selects which phases run.
    Rondo-REQ-101 req 17: start/end events logged.
    """
    started_at = datetime.now(UTC).isoformat()
    start_time = time.monotonic()

    event_log = EventLog(log_path=event_log_path)
    result = OvernightResult(
        mode=mode or "all",
        started_at=started_at,
    )

    # -- Log start event (Rondo-REQ-101 req 17)
    event_log.append(
        {
            "type": "start_overnight",
            "timestamp": started_at,
            "mode": result.mode,
        }
    )

    # -- REQ-103 req 014: preflight ONCE at batch start (not per-task)
    if not _overnight_preflight(config):
        result.completed_at = datetime.now(UTC).isoformat()
        result.duration_sec = time.monotonic() - start_time
        return result

    # -- STD-108 reqs 015-017 (RONDO-303): sweep the retry queue at run start.
    # -- Permanent/expired entries dead-letter; depth alert goes to the event
    # -- log (and the morning report carries it). Best-effort, never blocks.
    try:
        import os  # pylint: disable=import-outside-toplevel

        from rondo.retry_queue import sweep_retry_queue  # pylint: disable=import-outside-toplevel

        test_dir = os.environ.get("RONDO_TEST_DIR")
        retry_dir = os.path.join(test_dir, "retry") if test_dir else "~/.rondo/retry"
        sweep = sweep_retry_queue(retry_dir)
        if sweep.dead_lettered_permanent or sweep.dead_lettered_expired or sweep.alert:
            event_log.append(
                {
                    "type": "retry_sweep",
                    "timestamp": datetime.now(UTC).isoformat(),
                    "dead_lettered_permanent": sweep.dead_lettered_permanent,
                    "dead_lettered_expired": sweep.dead_lettered_expired,
                    "remaining": sweep.remaining,
                    "alert": sweep.alert or "",
                }
            )
    except (OSError, ImportError, TypeError) as exc:
        logger.debug("Retry sweep skipped (non-fatal): %s", exc)

    # -- Filter phases by mode (Rondo-REQ-101 reqs 13-15)
    active_phases = _filter_phases(phases, mode, modes)

    # -- Execute phases sequentially (Rondo-REQ-101 reqs 11-12)
    last_usage: DispatchUsage | None = None
    stopped = False

    for phase in active_phases:
        # -- Pre-phase usage gate (Rondo-REQ-101 reqs 24-28)
        if last_usage is not None:
            gate_action = check_usage_gate(last_usage, on_overage=config.on_overage)

            # -- Log usage gate decision (Rondo-REQ-101 req 28)
            event_log.append(
                {
                    "type": "usage_gate",
                    "timestamp": datetime.now(UTC).isoformat(),
                    "phase": phase.name,
                    "action": gate_action,
                    "rate_limit_status": last_usage.rate_limit_status,
                    "is_using_overage": last_usage.is_using_overage,
                }
            )

            if gate_action == "stop":
                stopped = True
                break
            if gate_action == "blocked":
                # -- Rondo-REQ-101 req 26: wait for reset
                if last_usage.rate_limit_resets_at > 0:
                    wait_sec = max(0, last_usage.rate_limit_resets_at - time.time())
                    if wait_sec > 0:
                        time.sleep(min(wait_sec, 3600))  # -- cap at 1 hour

        # -- Log phase start
        event_log.append(
            {
                "type": "phase_start",
                "timestamp": datetime.now(UTC).isoformat(),
                "phase": phase.name,
            }
        )

        # -- Execute phase (Rondo-REQ-101 req 12: failure isolation)
        try:
            phase_result = run_round(phase, config=config)
        except (OSError, ValueError, RuntimeError, TypeError) as exc:
            logger.warning("Phase %s failed: %s", phase.name, exc)
            phase_result = RoundResult(
                round_name=phase.name,
                status="error",
                summary=f"Phase exception: {exc}",
                started_at=datetime.now(UTC).isoformat(),
                completed_at=datetime.now(UTC).isoformat(),
            )

        result.phase_results.append(phase_result)

        # -- Log phase end
        event_log.append(
            {
                "type": "phase_end",
                "timestamp": datetime.now(UTC).isoformat(),
                "phase": phase.name,
                "status": phase_result.status,
            }
        )

        # -- Check for watchdog errors and log them (Rondo-REQ-101 req 23)
        _log_watchdog_events(phase_result, event_log)

        # -- Check for rate limit errors → backoff (Rondo-REQ-101 req 22)
        if _has_rate_limit_error(phase_result):
            event_log.append(
                {
                    "type": "watchdog_pause",
                    "timestamp": datetime.now(UTC).isoformat(),
                    "phase": phase.name,
                    "reason": "rate_limit_backoff",
                    "backoff_sec": config.rate_limit_backoff_sec,
                }
            )
            time.sleep(config.rate_limit_backoff_sec)

        # -- IFS-100 req 012 (RONDO-299): auth loss is NOT transient — every
        # -- later dispatch on this session fails identically. Halt the run;
        # -- the morning report shows what completed and why we stopped.
        if _has_auth_error(phase_result):
            event_log.append(
                {
                    "type": "auth_halt",
                    "timestamp": datetime.now(UTC).isoformat(),
                    "phase": phase.name,
                    "reason": "session auth lost — remaining phases skipped (IFS-100 req 012)",
                }
            )
            logger.error("-ERROR- auth loss in phase %s — halting overnight run", phase.name)
            stopped = True
            break

        # -- Capture last usage for pre-phase gate
        if phase_result.usage:
            last_usage = phase_result.usage[-1]

    # -- Calculate overnight status
    if stopped:
        result.status = "stopped"
    elif not result.phase_results:
        result.status = "done"
    else:
        result.status = _calculate_overnight_status(result.phase_results)

    # -- Aggregate costs
    result.total_cost_usd = sum(u.cost_usd for pr in result.phase_results for u in pr.usage)

    # -- Timing
    result.completed_at = datetime.now(UTC).isoformat()
    result.duration_sec = time.monotonic() - start_time

    # -- Log end event (Rondo-REQ-101 req 17)
    event_log.append(
        {
            "type": "end_overnight",
            "timestamp": result.completed_at,
            "status": result.status,
            "duration_sec": result.duration_sec,
        }
    )

    # -- Persist event log
    event_log.save()

    # -- Attach event log to result
    result.event_log = event_log.entries

    # -- REQ-101 spool: write overnight result for consumer pickup (ALWAYS-ON)
    _write_overnight_spool(result)

    return result


def _write_overnight_spool(result: OvernightResult) -> None:
    """Write overnight result to spool for consumer pickup (REQ-101)."""
    try:
        test_dir = os.environ.get("RONDO_TEST_DIR")
        spool_kw = {"spool_dir": os.path.join(test_dir, "spool")} if test_dir else {}
        spool_result(
            task_name=f"overnight-{result.status}",
            result=asdict(result),
            **spool_kw,
        )
    except (ImportError, OSError, TypeError) as exc:
        logger.debug("Overnight spool write failed (non-fatal): %s", exc)


# ──────────────────────────────────────────────────────────────────
#  Internal helpers
# ──────────────────────────────────────────────────────────────────


def _filter_phases(
    phases: list[Round],
    mode: str | None,
    modes: dict[str, list[str]] | None,
) -> list[Round]:
    """Filter phases based on mode selection.

    Rondo-REQ-101 req 13: mode selects which phases run.
    Rondo-REQ-101 req 15: no mode → all phases.
    """
    if mode is None or modes is None:
        return phases

    if mode not in modes:
        raise ValueError(f"Unknown mode '{mode}'. Available: {', '.join(modes.keys())}")

    selected_names = set(modes[mode])
    return [p for p in phases if p.name in selected_names]


def _calculate_overnight_status(phase_results: list[RoundResult]) -> str:
    """Calculate overall overnight status from phase results.

    Rules:
        "done"    — all phases completed successfully
        "skipped" — all phases skipped (dry-run, gate block, or no tasks)
        "partial" — at least one done, at least one not
        "error"   — no phases succeeded
    """
    statuses = {pr.status for pr in phase_results}

    if statuses == {"done"}:
        return "done"
    if statuses == {"skipped"}:
        return "skipped"
    if "done" in statuses:
        return "partial"
    return "error"


def _has_rate_limit_error(phase_result: RoundResult) -> bool:
    """Check if any task in phase had a rate limit error."""
    return any(tr.error_code == "ERR_RATE_LIMIT" for tr in phase_result.task_results)


def _has_auth_error(phase_result: RoundResult) -> bool:
    """Check if any task in phase had an auth failure — IFS-100 req 012 (RONDO-299).

    Auth loss is NOT transient: every subsequent dispatch on the session
    fails identically, burning the night for nothing. The run halts.
    """
    return any(tr.error_code == "ERR_AUTH" for tr in phase_result.task_results)


def _log_watchdog_events(phase_result: RoundResult, event_log: EventLog) -> None:
    """Log any watchdog timeout errors from phase results (Rondo-REQ-101 req 23)."""
    for tr in phase_result.task_results:
        if tr.error_code == "ERR_WATCHDOG_TIMEOUT":
            event_log.append(
                {
                    "type": "watchdog_kill",
                    "timestamp": datetime.now(UTC).isoformat(),
                    "task": tr.task_name,
                    "reason": "output_timeout",
                    "phase": phase_result.round_name,
                }
            )


# -- sig: mgh-6201.cd.bd955f.f73d.2bc45c
