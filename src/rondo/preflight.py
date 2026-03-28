# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Rondo preflight — verify dispatch environment before wasting API tokens.

REQ-103: Pre-dispatch environment checks.
Checks: claude binary, auth, nested session, config.
Returns GREEN/YELLOW/RED health status.

Import direction:
    engine.py → (no rondo imports)
    config.py → (no rondo imports)
    preflight.py → imports config
"""

from __future__ import annotations

import logging
import os
import shutil
from dataclasses import dataclass, field

from rondo.config import RondoConfig
from rondo.dispatch import detect_cc_version

logger = logging.getLogger(__name__)


@dataclass
class PreflightResult:
    """REQ-103 req 012: preflight health status.

    GREEN = all checks pass, proceed.
    YELLOW = warnings but can proceed.
    RED = errors, abort.
    """

    status: str = "GREEN"
    checks: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def can_proceed(self) -> bool:
        """True if status is GREEN or YELLOW."""
        return self.status in ("GREEN", "YELLOW")


def run_preflight(
    *,
    config: RondoConfig | None = None,
) -> PreflightResult:
    """Run all preflight checks. Returns PreflightResult.

    REQ-103 reqs 001-013: environment validation before dispatch.
    """
    if config is None:
        config = RondoConfig()

    result = PreflightResult()

    # -- REQ-103 req 003: claude binary on PATH
    _check_claude_binary(result, config)

    # -- REQ-103 req 010: CLAUDECODE env var (nested session guard)
    _check_nested_session(result)

    # -- REQ-103 req 005: API key / auth
    _check_auth(result, config)

    # -- REQ-103 reqs 004, 017: CC version
    _check_cc_version(result, config)

    # -- REQ-103 req 008: disk space
    _check_disk_space(result)

    # -- REQ-103 req 009: git available
    _check_git(result)

    # -- Calculate final status
    if result.errors:
        result.status = "RED"
    elif result.warnings:
        result.status = "YELLOW"
    else:
        result.status = "GREEN"

    return result


def _check_claude_binary(result: PreflightResult, config: RondoConfig) -> None:
    """REQ-103 req 003: claude binary on PATH and executable."""
    binary = shutil.which(config.claude_binary)
    if binary:
        result.checks.append(f"claude binary: {binary}")
    else:
        result.errors.append(
            f"claude binary '{config.claude_binary}' not found on PATH. "
            "Install Claude Code: npm install -g @anthropic-ai/claude-code"
        )


def _check_nested_session(result: PreflightResult) -> None:
    """REQ-103 req 010: CLAUDECODE env var not set."""
    if os.environ.get("CLAUDECODE"):
        result.errors.append(
            "CLAUDECODE env var is set — running inside a Claude Code session. "
            "Nested dispatch will fail with ERR_NESTED_SESSION. "
            "Fix: dispatch strips CLAUDECODE (REQ-100 req 013)."
        )
    else:
        result.checks.append("CLAUDECODE not set (no nesting risk)")


def _check_auth(result: PreflightResult, config: RondoConfig) -> None:
    """REQ-103 req 005: API key or Max plan auth available."""
    if config.auth == "api":
        key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not key:
            result.errors.append(
                "auth=api but ANTHROPIC_API_KEY not set. "
                "Set the key or switch to auth=max (subscription)."
            )
        else:
            result.checks.append("ANTHROPIC_API_KEY present (api auth)")
    elif config.auth == "max":
        result.checks.append("auth=max (subscription — no API key needed)")
    else:
        result.warnings.append(
            f"Unknown auth mode '{config.auth}' — expected 'max' or 'api'"
        )


_BARE_MIN_VERSION = (2, 1, 81)


def _check_cc_version(result: PreflightResult, config: RondoConfig) -> None:
    """REQ-103 reqs 004, 017: detect CC version, warn if too old."""
    version = detect_cc_version(config.claude_binary)
    if version is None:
        result.warnings.append(
            "Could not detect Claude Code version — "
            "some features (--bare) may not work"
        )
    elif version < _BARE_MIN_VERSION:
        v_str = ".".join(str(x) for x in version)
        result.warnings.append(
            f"Claude Code {v_str} is old — "
            f"need >= 2.1.81 for --bare flag"
        )
    else:
        v_str = ".".join(str(x) for x in version)
        result.checks.append(f"Claude Code version: {v_str}")


_MIN_DISK_MB = 500


def _check_disk_space(result: PreflightResult) -> None:
    """REQ-103 req 008: disk space > 500MB free (SHOULD)."""
    try:
        total, used, free = shutil.disk_usage(".")
        free_mb = free / (1024 * 1024)
        if free_mb < _MIN_DISK_MB:
            result.warnings.append(
                f"Low disk space: {free_mb:.0f}MB free (need {_MIN_DISK_MB}MB for worktrees)"
            )
        else:
            result.checks.append(f"Disk space: {free_mb:.0f}MB free")
    except OSError:
        result.warnings.append("Could not check disk space")


def _check_git(result: PreflightResult) -> None:
    """REQ-103 req 009: git available (SHOULD)."""
    if shutil.which("git"):
        result.checks.append("git available")
    else:
        result.warnings.append(
            "git not found on PATH — worktree operations will fail"
        )


# -- sig: mgh-6201.cd.bd955f.e4a1.82d3a1
