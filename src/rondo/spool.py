# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Rondo result spool — mailbox pattern for disconnected runs.

Rondo-REQ-101 reqs 042-052: Result Spool.
After each task completes, result JSON is written to a spool directory.
Consumers (OB, ACE, scripts) read and delete files — mailbox pattern.
Spool is a buffer between stateless Rondo and stateful consumers.

ALWAYS-ON: spool writes happen automatically. If spool dir is unreachable,
Rondo logs a warning and continues — never fails a task for spool issues.

Import direction:
    spool.py → no rondo imports (standalone utility)
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# -- ──────────────────────────────────────────────────────────────
# --  Configuration — REQ-101 req 042
# -- ──────────────────────────────────────────────────────────────


@dataclass
class SpoolConfig:
    """Spool configuration — REQ-101 req 042."""

    spool_dir: str = "~/.rondo/spool"
    ttl_days: int = 7  # -- req 046: auto-cleanup threshold


# -- ──────────────────────────────────────────────────────────────
# --  Spool manager — main interface
# -- ──────────────────────────────────────────────────────────────


class SpoolManager:
    """Result spool manager — REQ-101 reqs 042-052.

    Mailbox pattern: Rondo writes result files, consumers read and delete.
    Files are JSON with timestamp-based filenames. TTL-based auto-cleanup.
    """

    def __init__(self, *, config: SpoolConfig | None = None) -> None:
        self.config = config or SpoolConfig()
        self.spool_dir = Path(self.config.spool_dir).expanduser()

    def _ensure_dir(self) -> bool:
        """Create spool directory if needed — REQ-101 req 051."""
        try:
            self.spool_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            return True
        except OSError as exc:
            logger.warning("Spool dir creation failed (non-fatal): %s", exc)
            return False

    def write_result(
        self,
        *,
        task_name: str,
        result: dict[str, Any],
    ) -> Path | None:
        """Write result JSON to spool — REQ-101 req 043.

        Returns path to written file, or None if write failed (req 052).
        """
        if not self._ensure_dir():
            return None

        # -- Filename: {ISO-timestamp}-{task_name}.json (req 043)
        ts = datetime.now(UTC).strftime("%Y-%m-%dT%H%M%S")
        safe_name = task_name.replace("/", "_").replace(" ", "_")
        filename = f"{ts}-{safe_name}.json"
        filepath = self.spool_dir / filename

        try:
            filepath.write_text(
                json.dumps(result, indent=2, default=str),
                encoding="utf-8",
            )
            logger.debug("Spool write: %s", filepath)
            return filepath
        except OSError as exc:
            # -- REQ-101 req 052: never fail a task for spool issues
            logger.warning("Spool write failed (non-fatal): %s", exc)
            return None

    def list_pending(self) -> list[dict[str, Any]]:
        """List pending spool files — REQ-101 req 047.

        Returns list of {filename, age_sec, size_bytes, task_name}, newest first.
        """
        if not self.spool_dir.exists():
            return []

        entries: list[dict[str, Any]] = []
        now = time.time()
        for filepath in sorted(self.spool_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            stat = filepath.stat()
            entries.append({
                "filename": filepath.name,
                "age_sec": now - stat.st_mtime,
                "size_bytes": stat.st_size,
                "task_name": _extract_task_name(filepath.name),
                "path": str(filepath),
            })
        return entries

    def clean_expired(self) -> int:
        """Remove files older than TTL — REQ-101 req 046."""
        if not self.spool_dir.exists():
            return 0

        cutoff = time.time() - (self.config.ttl_days * 86400)
        removed = 0
        for filepath in self.spool_dir.glob("*.json"):
            if filepath.stat().st_mtime < cutoff:
                filepath.unlink()
                removed += 1
                logger.debug("Spool cleaned: %s", filepath.name)
        return removed

    def clean_all(self) -> int:
        """Remove all spool files — REQ-101 req 048 (--all flag)."""
        if not self.spool_dir.exists():
            return 0

        removed = 0
        for filepath in self.spool_dir.glob("*.json"):
            filepath.unlink()
            removed += 1
        return removed

    def export_since(self, since_date: str) -> list[dict[str, Any]]:
        """Export spool files since date — REQ-101 req 049.

        Returns list of result dicts for stdout/pipe.
        """
        if not self.spool_dir.exists():
            return []

        results: list[dict[str, Any]] = []
        for filepath in sorted(self.spool_dir.glob("*.json")):
            # -- Compare filename timestamp prefix against since_date
            fname = filepath.name
            if fname[:10] >= since_date:
                try:
                    data = json.loads(filepath.read_text(encoding="utf-8"))
                    data["_spool_file"] = fname
                    results.append(data)
                except (json.JSONDecodeError, OSError):
                    continue
        return results


def _extract_task_name(filename: str) -> str:
    """Extract task name from spool filename."""
    # -- Format: {ISO-timestamp}-{task_name}.json
    # -- Example: 2026-03-20T031400-code-review.json
    parts = filename.rsplit(".json", 1)[0]
    # -- Skip the ISO timestamp prefix (first 17 chars: YYYY-MM-DDTHHMMSS-)
    if len(parts) > 17 and parts[16] == "-":
        return parts[17:]
    return parts


def spool_result(
    *,
    task_name: str,
    result: dict[str, Any],
    spool_dir: str = "~/.rondo/spool",
) -> Path | None:
    """Convenience: write one result to spool — ALWAYS-ON pattern."""
    mgr = SpoolManager(config=SpoolConfig(spool_dir=spool_dir))
    return mgr.write_result(task_name=task_name, result=result)


# -- sig: mgh-6201.cd.bd955f.f1a4.95a4b6
