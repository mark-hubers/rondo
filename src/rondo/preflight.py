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
from rondo.dispatch import _BARE_MIN_VERSION, detect_cc_version

logger = logging.getLogger(__name__)

# -- REQ-103 req 025-026: preflight result cache, version-keyed
_preflight_cache: dict[str, PreflightResult] = {}


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
    REQ-103 req 025-026: cache result keyed by CC version.
    """
    if config is None:
        config = RondoConfig()

    # -- REQ-103 req 026: check cache by CC version
    version = detect_cc_version(config.claude_binary)
    cache_key = ".".join(str(x) for x in version) if version else "unknown"
    if cache_key in _preflight_cache:
        logger.debug("Preflight cache hit: %s", cache_key)
        return _preflight_cache[cache_key]

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

    # -- REQ-109 req 017: provider health (key present + API reachable)
    _check_provider_health(result)

    # -- Calculate final status
    if result.errors:
        result.status = "RED"
    elif result.warnings:
        result.status = "YELLOW"
    else:
        result.status = "GREEN"

    # -- REQ-103 req 025: cache result for batch mode
    _preflight_cache[cache_key] = result
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
                "auth=api but ANTHROPIC_API_KEY not set. Set the key or switch to auth=max (subscription)."
            )
        else:
            result.checks.append("ANTHROPIC_API_KEY present (api auth)")
    elif config.auth == "max":
        result.checks.append("auth=max (subscription — no API key needed)")
    else:
        result.warnings.append(f"Unknown auth mode '{config.auth}' — expected 'max' or 'api'")


def _check_cc_version(result: PreflightResult, config: RondoConfig) -> None:
    """REQ-103 reqs 004, 017: detect CC version, warn if too old."""
    version = detect_cc_version(config.claude_binary)
    if version is None:
        result.warnings.append("Could not detect Claude Code version — some features (--bare) may not work")
    elif version < _BARE_MIN_VERSION:
        v_str = ".".join(str(x) for x in version)
        result.warnings.append(f"Claude Code {v_str} is old — need >= 2.1.81 for --bare flag")
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
            result.warnings.append(f"Low disk space: {free_mb:.0f}MB free (need {_MIN_DISK_MB}MB for worktrees)")
        else:
            result.checks.append(f"Disk space: {free_mb:.0f}MB free")
    except OSError:
        result.warnings.append("Could not check disk space")


def _check_git(result: PreflightResult) -> None:
    """REQ-103 req 009: git available (SHOULD)."""
    if shutil.which("git"):
        result.checks.append("git available")
    else:
        result.warnings.append("git not found on PATH — worktree operations will fail")


def _check_provider_health(result: PreflightResult) -> None:
    """REQ-109 req 017: check all configured providers — key present + API reachable."""
    try:
        from rondo.adapters.health import get_all_providers_health  # pylint: disable=import-outside-toplevel

        health_map = get_all_providers_health()
        if not health_map:
            return  # -- No providers configured — not an error
        for name, status in health_map.items():
            if status.healthy:
                result.checks.append(f"provider {name}: UP ({status.latency_ms:.0f}ms)")
            else:
                result.warnings.append(f"provider {name}: DOWN — {status.error or 'health check failed'}")
    except Exception as exc:  # noqa: BLE001
        result.warnings.append(f"Provider health check failed: {exc}")


# -- sig: mgh-6201.cd.bd955f.e4a1.82d3a1
