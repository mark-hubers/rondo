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
    """Send to all configured channels."""
    for channel in config.channels:
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


def _send_macos(msg: str, title: str) -> None:
    """macOS notification center via osascript — Rondo-REQ-105 req 005."""
    try:
        script = f'display notification "{msg}" with title "{title}"'
        subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, check=False, timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        logger.debug("macOS notification failed: %s", exc)


# -- sig: mgh-6201.cd.bd955f.e4a1.c4d5e6
