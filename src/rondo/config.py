# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Rondo config — TOML loading, COALESCE resolution, validation.

Rondo-STD-109 rules 1-10.
Every setting resolved via COALESCE(cli_flag, config_file, default).
Config is frozen (immutable) after creation — thread-safe by design.
"""

from __future__ import annotations

import logging
import os
import threading
import tomllib
import types
import typing
import warnings
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# -- RONDO-202 (Finding #225): reload lock prevents mid-flight races.
_config_lock = threading.RLock()


# ──────────────────────────────────────────────────────────────────
#  Model context limits — RONDO-200 Finding #216, #227
# ──────────────────────────────────────────────────────────────────

# -- Per-model context window limits in tokens. Used by:
# --   1. mcp_dispatch.check_context_limit — pre-dispatch validation
# --   2. dispatch._max_output_bytes_for_model — dynamic output cap (#216)
# --
# -- Moved from mcp_dispatch.py to config.py in RONDO-206 because dispatch.py
# -- (L1) cannot import from mcp_dispatch.py (L2) without creating a cycle
# -- (mcp_dispatch imports finalize_dispatch from dispatch). config.py is
# -- below both layers and is the right home for configuration data.
MODEL_CONTEXT_LIMITS: dict[str, int] = {
    # -- Claude family (Anthropic)
    "haiku": 200_000,
    "sonnet": 200_000,
    "opus": 200_000,
    "sonnet[1m]": 1_000_000,
    "opus[1m]": 1_000_000,
    # -- Gemini
    "gemini-2.5-flash": 1_000_000,
    "gemini-2.5-pro": 2_000_000,
    "gemini-2.0-flash": 1_000_000,
    # -- OpenAI
    "gpt-4.1": 128_000,
    "gpt-4.1-mini": 128_000,
    # -- Grok
    "grok-3": 131_072,
    "grok-3-mini": 131_072,
    # -- Mistral
    "mistral-large-latest": 131_072,
}

# -- Default conservative limit for unknown models
DEFAULT_CONTEXT_LIMIT = 100_000


# ──────────────────────────────────────────────────────────────────
#  Shared directory constants — RONDO-213 cycle break
# ──────────────────────────────────────────────────────────────────
# -- Moved from mcp_tools.py to config.py in RONDO-213 because
# -- mcp_dispatch.py imported these at the top level from mcp_tools,
# -- creating the mcp_dispatch → mcp_tools → mcp_compose → mcp_dispatch
# -- triangle (finding #254, 7 of 13 pylint R0401 cycles). config.py is
# -- a leaf module (imports nothing from rondo.*), so it's the correct
# -- home — same pattern as MODEL_CONTEXT_LIMITS moved in RONDO-206.

DEFAULT_AUDIT_DIR = "~/.rondo/audit"
DEFAULT_SPOOL_DIR = "~/.rondo/spool"

# -- Max tenant name length (RONDO-216 C1: prevents DoS via long env var)
_MAX_TENANT_LEN = 64


def get_sanitized_tenant() -> str:
    """Shared tenant resolution — DRY replacement for 3 separate copies.

    RONDO-216 C1 (dual-sweep finding): audit.py, auth.py, spool.py each had
    their own tenant derivation with different sanitization levels. Now ONE
    shared function in config.py (leaf module) handles all three.

    Resolution: RONDO_TENANT → USER → 'default'.
    Sanitization: alphanumeric + underscore + hyphen only, max 64 chars.
    """
    import re  # pylint: disable=import-outside-toplevel

    raw = os.environ.get("RONDO_TENANT") or os.environ.get("USER") or "default"
    sanitized = re.sub(r"[^a-zA-Z0-9_-]", "", raw)[:_MAX_TENANT_LEN]
    return sanitized or "default"


def resolve_rondo_dir(default: str, subdir: str) -> str:
    """Resolve Rondo data dir: RONDO_TEST_DIR → default.

    Used by MCP tools and dispatch to find audit/spool/results dirs.
    Honors RONDO_TEST_DIR env var for test isolation (RONDO-200 #217).
    """
    test_dir = os.environ.get("RONDO_TEST_DIR")
    if test_dir:
        return os.path.join(test_dir, subdir)
    return default


# ──────────────────────────────────────────────────────────────────
#  COALESCE — Rondo-STD-109 rule 6
# ──────────────────────────────────────────────────────────────────


def resolve(cli_value: Any, config_value: Any, default_value: Any) -> Any:
    """COALESCE: first non-None wins."""
    if cli_value is not None:
        return cli_value
    if config_value is not None:
        return config_value
    return default_value


# ──────────────────────────────────────────────────────────────────
#  Config dataclass — Rondo-STD-109 rules 9-10
# ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RondoConfig:  # pylint: disable=too-many-instance-attributes
    """Immutable configuration — loaded once at startup (Rondo-STD-109 rule 9)."""

    # -- dispatch
    auth: str = "max"
    default_model: str = "sonnet"
    effort: str = "high"
    output_format: str = "stream-json"
    claude_binary: str = "claude"
    task_timeout_sec: int = 300  # -- REQ-100 req 074: per-task hard limit
    round_timeout_sec: int = 3600  # -- REQ-100 req 075: per-round hard limit

    # -- parallel
    workers: int = 4
    throttle_sec: float = 2.0

    # -- permissions
    permission_mode: str = "auto"

    # -- self-healing (Rondo-REQ-101 watchdog + usage gating)
    watchdog_timeout_sec: int = 60
    rate_limit_backoff_sec: int = 60
    on_overage: str = "continue"
    worktree_isolation: bool = False

    # -- paths
    results_dir: str = "reports/rondo-results"
    report_dir: str = "reports"
    audit_dir: str = "~/.rondo/audit"  # -- STD-113: always on, default path

    # -- cost & output control (REQ-100 reqs 078-080)
    max_budget_usd: float | None = None  # -- req 078: hard cost cap per task
    json_schema: str = ""  # -- req 079: enforce structured output at CC level
    dispatch_system_prompt: str = ""  # -- req 080: persistent dispatch context

    # -- spool (REQ-101 req 045: sync callers skip spool)
    spool_enabled: bool = False  # -- False = sync (no spool), True = async (overnight)

    # -- project (U-15 to U-19: cross-repo dispatching)
    project: str = ""  # -- empty = CWD, set = subprocess runs in this dir

    # -- flags
    bare: bool = True  # -- REQ-100 req 071: --bare for automated dispatch (default ON — skip hooks/CLAUDE.md)
    dry_run: bool = False
    verbose: bool = False

    def __post_init__(self) -> None:
        """RONDO_TEST_DIR: redirect audit+spool to tmp in tests (RONDO-28)."""
        test_dir = os.environ.get("RONDO_TEST_DIR")
        if test_dir and self.audit_dir == "~/.rondo/audit":
            object.__setattr__(self, "audit_dir", os.path.join(test_dir, "audit"))


# ──────────────────────────────────────────────────────────────────
#  Validation — Rondo-STD-109 rule 8
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

    valid_perms = ("default", "acceptEdits", "plan", "auto", "dontAsk", "bypassPermissions")
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

    # -- U-16: validate project path if set
    if config.project:
        from pathlib import Path  # pylint: disable=import-outside-toplevel

        project_path = Path(config.project).expanduser()
        if not project_path.exists():
            errors.append(f"--project path does not exist: {config.project}")
        elif not project_path.is_dir():
            errors.append(f"--project path is not a directory: {config.project}")


# ──────────────────────────────────────────────────────────────────
#  Config loading — Rondo-STD-109 rules 1-5, 7
# ──────────────────────────────────────────────────────────────────

# -- Fields in RondoConfig that are valid TOML keys
_CONFIG_FIELDS: set[str] = {f.name for f in fields(RondoConfig)}

# -- Fields that are CLI-only (not settable via TOML)
_CLI_ONLY: set[str] = {"dry_run"}


# -- FIX-688: robust TOML type checking (replaces FIX-680 string-matching)
_SIMPLE_TYPES: set[type] = {int, float, bool, str}


def _extract_allowed_types(type_hint: Any) -> set[type]:
    """Extract concrete types from a type hint, handling Optional/Union.

    Handles both real types and string annotations (from __future__ annotations).

    Examples:
        int / 'int' → {int}
        float | None / 'float | None' → {float}
        str | None → {str}
        Optional[int] → {int}
        complex/unknown → empty set (skip checking)
    """
    # -- String annotations (from __future__ import annotations) → resolve
    if isinstance(type_hint, str):
        # -- Simple type name
        simple_map = {"int": int, "float": float, "bool": bool, "str": str}
        if type_hint in simple_map:
            return {simple_map[type_hint]}
        # -- Union: "float | None", "int | None"
        if "|" in type_hint:
            parts = [p.strip() for p in type_hint.split("|")]
            return {simple_map[p] for p in parts if p in simple_map}
        return set()

    origin = typing.get_origin(type_hint)

    # -- Simple type (int, str, etc.)
    if type_hint in _SIMPLE_TYPES:
        return {type_hint}

    # -- Union type: int | None, Optional[int], etc.
    if origin is types.UnionType or origin is typing.Union:
        args = typing.get_args(type_hint)
        return {a for a in args if a in _SIMPLE_TYPES}

    return set()


def _check_toml_type(field_name: str, value: Any, type_hint: Any) -> bool:
    """Warn if TOML value type doesn't match field type.

    FIX-688: uses typing.get_args for robust Optional/Union handling.
    Returns True if type is bad (caller should skip this value and use default).
    """
    allowed = _extract_allowed_types(type_hint)
    if not allowed:
        return False  # -- complex type, skip checking

    if not isinstance(value, tuple(allowed)):
        type_names = " | ".join(t.__name__ for t in sorted(allowed, key=lambda t: t.__name__))
        warnings.warn(
            f"Config type error: '{field_name}' must be {type_names}, got {type(value).__name__} ({value!r})",
            stacklevel=4,
        )
        return True
    return False


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

    # -- Warn about unknown TOML keys (Rondo-STD-109 rule 7)
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
            # -- FIX-680: type check TOML values at load time (fail fast, clear message)
            if toml_val is not None and cli_val is None:
                if _check_toml_type(f.name, toml_val, f.type):
                    continue  # -- bad type: skip, use default
            kwargs[f.name] = resolved

    config = RondoConfig(**kwargs)

    # -- Finding #180: validate config and warn on errors
    errors = validate_config(config)
    for err in errors:
        warnings.warn(f"Config validation: {err}", stacklevel=2)

    return config


def _load_toml(
    config_path: Path | str | None,
    search_dir: Path | str | None,
) -> dict[str, Any]:
    """Find and parse TOML config file. Returns empty dict if not found.

    Discovery (Rondo-STD-109 rule 3):
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


# -- ──────────────────────────────────────────────────────────────
# --  Config validation — REQ-109 req 089
# -- ──────────────────────────────────────────────────────────────

_VALID_TRUST = {"trusted", "untrusted"}


def _validate_config(data: dict[str, Any]) -> dict[str, Any]:
    """Validate provider config types. Log warnings for invalid values, don't crash.

    REQ-109 req 089: enabled=bool, *_model=str, trust=enum.
    """
    providers = data.get("providers", {})
    for name, cfg in providers.items():
        if not isinstance(cfg, dict):
            logger.warning("Provider '%s' config is not a dict — skipping", name)
            continue
        # -- enabled must be bool
        if "enabled" in cfg and not isinstance(cfg["enabled"], bool):
            logger.warning("Provider '%s' enabled must be bool, got %s", name, type(cfg["enabled"]).__name__)
        # -- model fields must be non-empty strings
        for key in ("cheap_model", "default_model", "best_model"):
            val = cfg.get(key, "")
            if val and not isinstance(val, str):
                logger.warning("Provider '%s' %s must be string, got %s", name, key, type(val).__name__)
        # -- trust must be valid enum
        trust = cfg.get("trust", "")
        if trust and trust not in _VALID_TRUST:
            logger.warning("Provider '%s' trust='%s' invalid — must be 'trusted' or 'untrusted'", name, trust)
    return data


# -- ──────────────────────────────────────────────────────────────
# --  Raw TOML config reader — single cached reader for providers/cloud/auth
# -- ──────────────────────────────────────────────────────────────

_raw_config: dict[str, Any] | None = None


def get_rondo_config(config_path: str = "") -> dict[str, Any]:
    """Load and cache raw ~/.rondo/config.toml as dict.

    Single source for all TOML config reads (providers, cloud, auth, routing).

    Cache strategy (REQ-109 req 092):
        config: ONE-SHOT — loaded once at startup, never reloaded. Restart to pick up changes.
        health: 5-min TTL (see adapters/health.py req 018)
        keys:   5-min TTL + invalidate on 401 (see adapters/auth.py req 040)

    Merge behavior (REQ-109 req 040):
        config_path provided: returns that file (no cache, for tests).
        config_path empty: reads ~/.rondo/config.toml ONCE, caches result.
        Second call without config_path: returns cache (no-op, no re-read).
        This is MERGE on first load, not hot-reload.

    Args:
        config_path: Override path (for tests). Default: ~/.rondo/config.toml.

    Returns:
        Raw TOML dict. Empty dict if file missing, invalid, or world-writable.
    """
    global _raw_config  # noqa: PLW0603
    # -- RONDO-202 (Finding #225): hold lock during read to prevent mid-reload race
    with _config_lock:
        if _raw_config is not None and not config_path:
            return _raw_config

    path = Path(config_path) if config_path else Path.home() / ".rondo" / "config.toml"
    if path.is_file():
        # -- REQ-109 req 090: permission check (POSIX only)
        try:
            import os
            import stat

            file_stat = os.stat(path)
            if file_stat.st_mode & stat.S_IWOTH:
                logger.warning("Config %s is world-writable — skipping for security", path)
                result: dict[str, Any] = {}
                if not config_path:
                    _raw_config = result
                return result
        except (OSError, AttributeError):
            pass  # -- Non-POSIX or can't stat — proceed with load

        try:
            with open(path, "rb") as f:
                result = tomllib.load(f)
            # -- REQ-109 req 089: validate provider config types
            result = _validate_config(result)
        except (tomllib.TOMLDecodeError, OSError):
            result = {}
    else:
        result = {}

    if not config_path:
        # -- RONDO-202 Finding #225: write cache atomically under lock
        with _config_lock:
            _raw_config = result
    return result


def reset_rondo_config() -> None:
    """Clear cached config — used by tests."""
    global _raw_config  # noqa: PLW0603
    with _config_lock:
        _raw_config = None


def reload_rondo_config(config_path: str = "") -> dict[str, Any]:
    """RONDO-200 (Finding #218) + RONDO-202 (Finding #225): Hot-reload config.

    Clears the in-memory cache and re-reads ~/.rondo/config.toml.
    Use when an operator updates config and wants new providers/keys
    picked up without restarting the MCP server.

    Thread-safe: reload holds the lock for the entire reset+read sequence
    so mid-flight dispatches either see OLD or NEW config — never partial.
    """
    with _config_lock:
        reset_rondo_config()
        return get_rondo_config(config_path=config_path)


# -- sig: mgh-6201.cd.bd955f.1174.b6fb32
