# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Rondo notifications — terminal, file, macOS notification center.

Rondo-REQ-105: dispatch notification channels.
Fires on round completion, dispatch failure, budget threshold.

Import direction:
    notify.py → no rondo imports (standalone utility)
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class NotifyConfig:
    """Notification configuration — Rondo-REQ-105 req 006."""

    channels: list[str] = field(default_factory=lambda: ["terminal"])
    log_file: str = "reports/notifications.log"
    quiet: bool = False  # -- REQ-105 req 007: suppress terminal, keep file+macos


def notify_round_complete(
    *,
    round_name: str,
    status: str,
    duration_sec: float,
    cost_usd: float,
    config: NotifyConfig | None = None,
) -> None:
    """Notify on round completion — Rondo-REQ-105 req 001."""
    config = config or NotifyConfig()
    msg = f"Round '{round_name}': {status} ({duration_sec:.1f}s, ${cost_usd:.4f})"
    _send(msg, title=f"Rondo: {status}", config=config)


def notify_failure(
    *,
    task_name: str,
    error_code: str,
    error_message: str,
    config: NotifyConfig | None = None,
) -> None:
    """Notify on dispatch failure — Rondo-REQ-105 req 002."""
    config = config or NotifyConfig()
    msg = f"Task '{task_name}' failed: {error_code} — {error_message}"
    _send(msg, title="Rondo: dispatch failed", config=config)


def _send(msg: str, *, title: str, config: NotifyConfig) -> None:
    """Send to all configured channels. Quiet mode skips terminal."""
    for channel in config.channels:
        if channel == "terminal" and config.quiet:
            continue  # -- REQ-105 req 007
        if channel == "terminal":
            _send_terminal(msg)
        elif channel == "file":
            _send_file(msg, config.log_file)
        elif channel == "macos":
            _send_macos(msg, title)


def _send_terminal(msg: str) -> None:
    """Print to stdout — Rondo-REQ-105 req 005."""
    timestamp = datetime.now(UTC).strftime("%H:%M:%S")
    print(f"  [{timestamp}] {msg}")


def _send_file(msg: str, log_file: str) -> None:
    """Append to notification log — Rondo-REQ-105 req 005."""
    try:
        path = Path(log_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(UTC).isoformat()
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {msg}\n")
    except OSError as exc:
        logger.debug("File notification failed: %s", exc)


def _escape_applescript(s: str) -> str:
    """Escape a string for safe embedding in AppleScript double-quoted string.

    Finding #182: AI output is untrusted. Double-quotes in msg could
    terminate the AppleScript string and inject arbitrary commands.
    """
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def _send_macos(msg: str, title: str) -> None:
    """Send a macOS notification via osascript — Rondo-REQ-105 req 005."""
    try:
        safe_msg = _escape_applescript(msg)[:200]
        safe_title = _escape_applescript(title)[:50]
        script = f'display notification "{safe_msg}" with title "{safe_title}"'
        subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            check=False,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        logger.debug("macOS notification failed: %s", exc)


def notify_rate_limit(
    *,
    reset_time: str,
    config: NotifyConfig | None = None,
) -> None:
    """Notify on rate limit — Rondo-REQ-105 req 004. Uses dedup."""
    config = config or NotifyConfig()
    msg = f"Rate limited. Resets at: {reset_time}. Pausing dispatches."
    notify_with_dedup("rate_limited", msg, config=config)


def notify_budget_threshold(
    *,
    spent_usd: float,
    budget_usd: float,
    config: NotifyConfig | None = None,
) -> None:
    """Notify on budget threshold crossing — Rondo-REQ-105 req 003.

    Fires at 50%, 75%, 90%. Under 50% = silent.
    """
    config = config or NotifyConfig()
    if budget_usd <= 0:
        return
    pct = (spent_usd / budget_usd) * 100
    if pct >= 90:
        msg = f"Budget CRITICAL: ${spent_usd:.2f} of ${budget_usd:.2f} (90%+)"
    elif pct >= 75:
        msg = f"Budget WARNING: ${spent_usd:.2f} of ${budget_usd:.2f} (75%+)"
    elif pct >= 50:
        msg = f"Budget NOTICE: ${spent_usd:.2f} of ${budget_usd:.2f} (50%+)"
    else:
        return
    _send(msg, title="Rondo: budget alert", config=config)


# -- Deduplication state (Rondo-REQ-105 req 009)
_dedup_seen: set[str] = set()


def reset_dedup() -> None:
    """Reset dedup state — for testing."""
    _dedup_seen.clear()


def notify_with_dedup(
    key: str,
    msg: str,
    *,
    config: NotifyConfig | None = None,
) -> None:
    """Send notification with dedup — Rondo-REQ-105 req 009.

    Same key only fires once. Reset with reset_dedup().
    """
    config = config or NotifyConfig()
    if key in _dedup_seen:
        return
    _dedup_seen.add(key)
    _send(msg, title="Rondo", config=config)


# -- sig: mgh-6201.cd.bd955f.e4a1.c4d5e6
