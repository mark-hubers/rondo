# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Config-driven HTTP read-timeouts — REQ-109 req 212 (RONDO-318).

5-10 minutes is NORMAL for max-effort thinking on a long task; 120s is
right for a classic model — a fixed timeout is always wrong for someone.

COALESCE (manual always wins, the house idiom):
    per-dispatch override → config `[timeouts]` per (model-class, effort)
    → built-in defaults below.

Streamed dispatches don't use these at all: streaming replaces the total
read-timeout with a per-EVENT silence watchdog (req 214). This chain covers
classic models and non-streaming thinking fallbacks (req 211).

Import direction:
    timeouts.py → config only (lazy, for the live default path)
"""

from __future__ import annotations

from typing import Any

## -- req 212 built-in defaults. Keys: "classic" or f"thinking_{effort}".
DEFAULT_TIMEOUTS: dict[str, int] = {
    "classic": 120,
    "thinking_low": 600,
    "thinking_medium": 600,
    "thinking_high": 600,
    "thinking_xhigh": 900,
    "thinking_max": 900,
}
## -- a thinking model with an unrecognized effort still never gets 120s
_THINKING_FLOOR_KEY = "thinking_high"


def _coerce_positive_int(value: Any) -> int | None:
    """A timeout must be a positive number; anything else falls through."""
    try:
        as_int = int(value)
    except (TypeError, ValueError):
        return None
    return as_int if as_int > 0 else None


def resolve_read_timeout(
    *,
    thinking: bool,
    effort: str,
    per_dispatch: Any = None,
    timeouts_cfg: dict[str, Any] | None = None,
) -> int:
    """Resolve one dispatch's HTTP read-timeout — req 212 COALESCE.

    `timeouts_cfg=None` loads the live `[timeouts]` config table; pass a
    dict (even empty) for hermetic tests. Malformed or non-positive values
    at any level fall through to the next — never crash, never zero.
    """
    override = _coerce_positive_int(per_dispatch)
    if override is not None:
        return override

    if timeouts_cfg is None:
        timeouts_cfg = _load_timeouts_config()

    key = f"thinking_{effort.lower()}" if thinking else "classic"
    if thinking and key not in DEFAULT_TIMEOUTS:
        key = _THINKING_FLOOR_KEY

    configured = _coerce_positive_int(timeouts_cfg.get(key))
    if configured is not None:
        return configured
    return DEFAULT_TIMEOUTS[key]


def _load_timeouts_config() -> dict[str, Any]:
    """Live `[timeouts]` table from ~/.rondo/config.toml; {} when absent."""
    try:
        from rondo.config import get_rondo_config  # pylint: disable=import-outside-toplevel

        table = get_rondo_config().get("timeouts", {})
        return table if isinstance(table, dict) else {}
    except (OSError, TypeError, ValueError, KeyError):
        return {}
