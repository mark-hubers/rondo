# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Retry queue lifecycle — STD-108 reqs 015-018 (RONDO-303).

Driver (failure taxonomy 2026-06-05): 50 stale files in ~/.rondo/retry/,
60% ERR_SUBPROCESS_FOOTGUN — PERMANENT blocks that can never succeed on
retry. The queue was a write-only bin: no classification, no aging, no
alerting. "A queue nobody reads is a black hole with extra steps."

Lifecycle:
    classify  — transient (retryable) vs permanent (dead-letter, req 015)
    sweep     — permanent + aged-out entries move to dead-letter/ (req 016)
    alert     — depth over threshold surfaces in morning report (req 017)
    list      — age, class, one-line reason per entry (req 018)

Import direction:
    retry_queue.py → stdlib only (reads queue files directly)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEAD_LETTER_DIRNAME = "dead-letter"

# -- STD-108 req 015: error codes that can NEVER succeed on retry.
# -- Semantic blocks (guards, validation) and auth failures — retrying
# -- burns time and money for a guaranteed identical outcome.
PERMANENT_ERROR_CODES: frozenset[str] = frozenset(
    {
        "ERR_SUBPROCESS_FOOTGUN",
        "ERR_AUTH",
        "ERR_INVALID_INPUT",
        "ERR_GATE",
        "ERR_NESTED_SESSION",
        "ERR_INTERNAL",
    }
)

DEFAULT_MAX_AGE_DAYS = 7  # -- STD-108 req 016
DEFAULT_ALERT_THRESHOLD = 10  # -- STD-108 req 017


def classify_retryability(error_code: str) -> str:
    """Classify an error code as transient or permanent — STD-108 req 015.

    Unknown codes default TRANSIENT: a new error code must never be
    silently dead-lettered before a human has seen it retry-fail.
    """
    return "permanent" if error_code in PERMANENT_ERROR_CODES else "transient"


def _entry_error_code(payload: dict[str, Any]) -> str:
    """Worst error code across an entry's tasks (permanent wins)."""
    codes = [t.get("error_code") or "" for t in payload.get("tasks", []) if t.get("error_code")]
    for code in codes:
        if classify_retryability(code) == "permanent":
            return code
    return codes[0] if codes else ""


def _entry_age_days(payload: dict[str, Any], path: Path, now: datetime) -> float:
    """Entry age in days — saved_at field when present, file mtime fallback."""
    saved_raw = payload.get("saved_at") or ""
    try:
        saved = datetime.fromisoformat(saved_raw)
        if saved.tzinfo is None:
            saved = saved.replace(tzinfo=UTC)
    except (ValueError, TypeError):
        try:
            saved = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
        except OSError:
            return 0.0
    return max(0.0, (now - saved).total_seconds() / 86400.0)


@dataclass
class SweepReport:
    """Outcome of a retry-queue sweep — STD-108 reqs 015-017."""

    remaining: int = 0
    dead_lettered_permanent: int = 0
    dead_lettered_expired: int = 0
    alert: str | None = None


def sweep_retry_queue(
    retry_dir: str,
    *,
    max_age_days: float = DEFAULT_MAX_AGE_DAYS,
    alert_threshold: int = DEFAULT_ALERT_THRESHOLD,
    now: datetime | None = None,
) -> SweepReport:
    """Sweep the retry queue — STD-108 reqs 015-017 (RONDO-303).

    Permanent-class entries and entries older than `max_age_days` move to
    the dead-letter/ subdirectory with a recorded reason. Returns a report
    including the depth alert (req 017) when the remaining queue is deep.
    Best-effort per entry: one unreadable file never aborts the sweep.
    """
    now = now or datetime.now(UTC)
    base = Path(retry_dir).expanduser()
    report = SweepReport()
    if not base.is_dir():
        return report

    dead_dir = base / DEAD_LETTER_DIRNAME
    for path in sorted(base.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("-WARNING- retry sweep: unreadable %s (%s) — left in place", path.name, exc)
            report.remaining += 1
            continue

        code = _entry_error_code(payload)
        reason = ""
        if code and classify_retryability(code) == "permanent":
            reason = f"permanent:{code}"
        elif _entry_age_days(payload, path, now) > max_age_days:
            reason = "expired"

        if not reason:
            report.remaining += 1
            continue

        try:
            dead_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            payload["dead_letter_reason"] = reason
            payload["dead_lettered_at"] = now.isoformat()
            target = dead_dir / path.name
            target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            target.chmod(0o600)
            path.unlink()
            if reason == "expired":
                report.dead_lettered_expired += 1
            else:
                report.dead_lettered_permanent += 1
        except OSError as exc:
            logger.warning("-WARNING- retry sweep: could not dead-letter %s: %s", path.name, exc)
            report.remaining += 1

    report.alert = queue_depth_alert(report.remaining, threshold=alert_threshold)
    return report


def queue_depth_alert(depth: int, *, threshold: int = DEFAULT_ALERT_THRESHOLD) -> str | None:
    """Depth alert — STD-108 req 017: silent queue growth is forbidden."""
    if depth <= threshold:
        return None
    return f"retry queue depth {depth} exceeds threshold {threshold} — run 'rondo spool' / sweep and triage"


def list_queue(retry_dir: str, *, now: datetime | None = None) -> list[dict[str, Any]]:
    """List queue entries with age, class, and one-line reason — STD-108 req 018."""
    now = now or datetime.now(UTC)
    base = Path(retry_dir).expanduser()
    if not base.is_dir():
        return []
    entries: list[dict[str, Any]] = []
    for path in sorted(base.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            entries.append(
                {"dispatch_id": path.stem, "error_class": "unreadable", "age_days": 0.0, "reason": "unreadable file"}
            )
            continue
        code = _entry_error_code(payload)
        entries.append(
            {
                "dispatch_id": payload.get("dispatch_id") or path.stem,
                "error_class": classify_retryability(code) if code else "unknown",
                "age_days": _entry_age_days(payload, path, now),
                "reason": code or "no error code recorded",
            }
        )
    return entries


# -- sig: mgh-6201.cd.bd955f.f1a7.rq303b
