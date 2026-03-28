# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Rondo config — TOML loading, COALESCE resolution, validation.

STD-002 rules 1-10.
Every setting resolved via COALESCE(cli_flag, config_file, default).
Config is frozen (immutable) after creation — thread-safe by design.
"""

from __future__ import annotations

import tomllib
import warnings
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any

# ──────────────────────────────────────────────────────────────────
#  COALESCE — STD-002 rule 6
# ──────────────────────────────────────────────────────────────────


def resolve(cli_value: Any, config_value: Any, default_value: Any) -> Any:
    """COALESCE: first non-None wins."""
    if cli_value is not None:
        return cli_value
    if config_value is not None:
        return config_value
    return default_value


# ──────────────────────────────────────────────────────────────────
#  Config dataclass — STD-002 rules 9-10
# ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RondoConfig:  # pylint: disable=too-many-instance-attributes
    """Immutable configuration — loaded once at startup (STD-002 rule 9)."""

    # -- dispatch
    auth: str = "max"
    default_model: str = "sonnet"
    effort: str = "high"
    output_format: str = "stream-json"
    claude_binary: str = "claude"
    task_timeout_sec: int = 300

    # -- parallel
    workers: int = 4
    throttle_sec: float = 2.0

    # -- permissions
    permission_mode: str = "auto"

    # -- self-healing (REQ-002 watchdog + usage gating)
    watchdog_timeout_sec: int = 60
    rate_limit_backoff_sec: int = 60
    on_overage: str = "continue"
    worktree_isolation: bool = False

    # -- paths
    results_dir: str = "reports/rondo-results"
    report_dir: str = "reports"

    # -- flags
    bare: bool = False  # -- REQ-100 req 071: add --bare for automated dispatch
    dry_run: bool = False
    verbose: bool = False


# ──────────────────────────────────────────────────────────────────
#  Validation — STD-002 rule 8
# ──────────────────────────────────────────────────────────────────


def validate_config(config: RondoConfig) -> list[str]:
    """Return list of validation errors (empty = valid).

    All errors collected — not just the first. Caller decides
    whether to exit or warn.
    """
    errors: list[str] = []
    _validate_enums(config, errors)
    _validate_ranges(config, errors)
    _validate_relationships(config, errors)
    _validate_non_empty(config, errors)
    return errors


def _validate_enums(config: RondoConfig, errors: list[str]) -> None:
    """Validate enum-style fields against allowed values."""
    if config.auth not in ("max", "api"):
        errors.append(f"auth must be 'max' or 'api', got '{config.auth}'")

    if config.output_format not in ("text", "json", "stream-json"):
        errors.append(f"output_format must be text/json/stream-json, got '{config.output_format}'")

    if config.effort not in ("low", "medium", "high", "max"):
        errors.append(f"effort must be low/medium/high/max, got '{config.effort}'")

    if config.on_overage not in ("continue", "pause", "stop"):
        errors.append(f"on_overage must be continue/pause/stop, got '{config.on_overage}'")

    valid_models = ("opus", "sonnet", "haiku", "opus[1m]", "sonnet[1m]")
    if config.default_model not in valid_models:
        errors.append(f"default_model must be one of {valid_models}, got '{config.default_model}'")

    valid_perms = ("default", "acceptEdits", "plan", "auto", "bypassPermissions")
    if config.permission_mode not in valid_perms:
        errors.append(f"permission_mode must be one of {valid_perms}, got '{config.permission_mode}'")


def _validate_ranges(config: RondoConfig, errors: list[str]) -> None:
    """Validate numeric fields against min/max bounds."""
    if config.workers < 1 or config.workers > 32:
        errors.append(f"workers must be 1-32, got {config.workers}")

    if config.throttle_sec < 0 or config.throttle_sec > 60:
        errors.append(f"throttle_sec must be 0-60, got {config.throttle_sec}")

    if config.task_timeout_sec < 10 or config.task_timeout_sec > 3600:
        errors.append(f"task_timeout_sec must be 10-3600, got {config.task_timeout_sec}")

    if config.watchdog_timeout_sec < 10 or config.watchdog_timeout_sec > 600:
        errors.append(f"watchdog_timeout_sec must be 10-600, got {config.watchdog_timeout_sec}")

    if config.rate_limit_backoff_sec < 10 or config.rate_limit_backoff_sec > 600:
        errors.append(f"rate_limit_backoff_sec must be 10-600, got {config.rate_limit_backoff_sec}")


def _validate_relationships(config: RondoConfig, errors: list[str]) -> None:
    """Validate cross-field relationships between config values."""
    if config.watchdog_timeout_sec >= config.task_timeout_sec:
        errors.append(
            f"watchdog_timeout_sec ({config.watchdog_timeout_sec}) must be less than "
            f"task_timeout_sec ({config.task_timeout_sec}) — watchdog detects silence "
            f"within a task, so it must fire before the task times out"
        )


def _validate_non_empty(config: RondoConfig, errors: list[str]) -> None:
    """Validate string fields that must not be empty."""
    if not config.claude_binary:
        errors.append("claude_binary must not be empty")

    if not config.results_dir:
        errors.append("results_dir must not be empty")

    if not config.report_dir:
        errors.append("report_dir must not be empty")


# ──────────────────────────────────────────────────────────────────
#  Config loading — STD-002 rules 1-5, 7
# ──────────────────────────────────────────────────────────────────

# -- Fields in RondoConfig that are valid TOML keys
_CONFIG_FIELDS: set[str] = {f.name for f in fields(RondoConfig)}

# -- Fields that are CLI-only (not settable via TOML)
_CLI_ONLY: set[str] = {"dry_run"}


def load_config(
    *,
    config_path: Path | str | None = None,
    search_dir: Path | str | None = None,
    cli_overrides: dict[str, Any] | None = None,
) -> RondoConfig:
    """Load config via COALESCE(cli_flag, config_file, default).

    Args:
        config_path: Explicit path to TOML file (--config flag).
        search_dir: Directory to search for rondo.toml (default: CWD).
        cli_overrides: Dict of CLI flag values (non-None = provided).

    Returns:
        Frozen RondoConfig with all values resolved.
    """
    cli_overrides = cli_overrides or {}
    toml_data = _load_toml(config_path, search_dir)

    # -- Warn about unknown TOML keys (STD-002 rule 7)
    toml_keys = set(toml_data.keys()) - _CONFIG_FIELDS
    for key in sorted(toml_keys):
        warnings.warn(
            f"Unknown config key '{key}' in TOML file — ignored",
            stacklevel=2,
        )

    # -- COALESCE each field: CLI → TOML → default
    kwargs: dict[str, Any] = {}
    for f in fields(RondoConfig):
        cli_val = cli_overrides.get(f.name)
        toml_val = toml_data.get(f.name)
        resolved = resolve(cli_val, toml_val, None)
        if resolved is not None:
            kwargs[f.name] = resolved

    return RondoConfig(**kwargs)


def _load_toml(
    config_path: Path | str | None,
    search_dir: Path | str | None,
) -> dict[str, Any]:
    """Find and parse TOML config file. Returns empty dict if not found.

    Discovery (STD-002 rule 3):
        1. If config_path provided → use that path exactly
        2. Else: look for rondo.toml in search_dir (default CWD)
        3. If not found → empty dict (zero-config mode)

    No walk-up search — only looks in the exact directory.
    """
    if config_path is not None:
        path = Path(config_path)
        if path.is_file():
            try:
                with open(path, "rb") as f:
                    return tomllib.load(f)
            except tomllib.TOMLDecodeError as exc:
                warnings.warn(f"TOML parse error in {path}: {exc}", stacklevel=3)
                return {}
        return {}

    # -- Discovery: search_dir or CWD
    base = Path(search_dir) if search_dir is not None else Path.cwd()
    candidate = base / "rondo.toml"
    if candidate.is_file():
        try:
            with open(candidate, "rb") as f:
                return tomllib.load(f)
        except tomllib.TOMLDecodeError as exc:
            warnings.warn(f"TOML parse error in {candidate}: {exc}", stacklevel=3)
            return {}

    return {}


# -- sig: mgh-6201.cd.bd955f.1174.b6fb32
