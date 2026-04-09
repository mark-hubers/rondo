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

import hashlib
import json
import logging
import os
import re
import tempfile
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_MAX_TASK_SLUG_LEN = 120


def _safe_task_slug(task_name: str) -> str:
    """Reduce task_name to a single safe path segment (no traversal, no separators).

    Malicious or odd inputs become a stable slug; never empty.
    """
    s = (task_name or "").strip()
    if not s:
        return "unnamed"
    s = s.replace("\x00", "").replace("/", "_").replace("\\", "_")
    s = re.sub(r"\.\.+", "_", s)
    s = re.sub(r"[^a-zA-Z0-9._-]+", "_", s)
    s = s.strip("._-")
    if not s:
        digest = hashlib.sha256(task_name.encode("utf-8", errors="replace")).hexdigest()[:12]
        return f"task_{digest}"
    return s[:_MAX_TASK_SLUG_LEN]


def _validated_spool_path(spool_dir: Path, filename: str) -> Path | None:
    """Resolve a spool file path; return None if filename escapes spool_dir."""
    if not filename or os.path.basename(filename) != filename:
        logger.warning("Spool path rejected (not a bare filename): %r", filename)
        return None
    if ".." in filename:
        logger.warning("Spool path rejected (parent segments): %r", filename)
        return None
    try:
        root = spool_dir.resolve()
        candidate = (spool_dir / filename).resolve()
        candidate.relative_to(root)
    except ValueError:
        logger.warning("Spool path rejected (outside spool dir): %r", filename)
        return None
    return candidate if candidate.is_file() else None


# -- ──────────────────────────────────────────────────────────────
# --  Configuration — REQ-101 req 042
# -- ──────────────────────────────────────────────────────────────


def _get_tenant_for_spool() -> str:
    """RONDO-202 (Finding #224): derive tenant from env for spool isolation.

    RONDO-216 C1: delegates to shared get_sanitized_tenant() in config.py.
    Was completely unsanitized — raw env var embedded in filesystem path.
    """
    from rondo.config import get_sanitized_tenant  # pylint: disable=import-outside-toplevel

    return get_sanitized_tenant()


def _default_spool_dir() -> str:
    """Default spool dir: ~/.rondo/spool/{tenant}/ — tenant-isolated.

    RONDO-202 (Finding #224): Gemini R3 flagged spool dir as shared across
    tenants. This path now includes tenant subdir same as audit.
    """
    tenant = _get_tenant_for_spool()
    return f"~/.rondo/spool/{tenant}"


@dataclass
class SpoolConfig:
    """Spool configuration — REQ-101 req 042."""

    spool_dir: str = ""  # -- resolved in __post_init__
    ttl_days: int = 7  # -- req 046: auto-cleanup threshold

    def __post_init__(self) -> None:
        """COALESCE: explicit dir → tenant-scoped default."""
        if not self.spool_dir:
            object.__setattr__(self, "spool_dir", _default_spool_dir())


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

        # -- STD-107 req 004/009: validate input before writing
        if not isinstance(result, dict):
            logger.warning("Spool rejected non-dict result for task '%s'", task_name)
            return None
        if not task_name or not task_name.strip():
            logger.warning("Spool rejected empty task_name")
            return None

        # -- Filename: {ISO-timestamp}-{task_name}.json (req 043)
        ts = datetime.now(UTC).strftime("%Y-%m-%dT%H%M%S")
        safe_name = _safe_task_slug(task_name)
        filename = f"{ts}-{safe_name}.json"
        filepath = self.spool_dir / filename

        try:
            # -- Atomic replace: readers never see a half-written JSON file
            fd, tmp_path = tempfile.mkstemp(
                dir=self.spool_dir,
                prefix=".spool-",
                suffix=".tmp",
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as tmp_f:
                    tmp_f.write(json.dumps(result, indent=2, default=str))
                os.replace(tmp_path, filepath)
            finally:
                if os.path.exists(tmp_path):
                    try:
                        os.unlink(tmp_path)
                    except OSError:
                        pass
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
            entries.append(
                {
                    "filename": filepath.name,
                    "age_sec": now - stat.st_mtime,
                    "size_bytes": stat.st_size,
                    "task_name": _extract_task_name(filepath.name),
                    "path": str(filepath),
                }
            )
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

    def consume_all(self) -> list[dict[str, Any]]:
        """Read and delete all spool files — REQ-101 req 044 mailbox pattern.

        Consumer reads the data, file is deleted. Once consumed, it's gone.
        Returns list of result dicts sorted oldest first.
        """
        if not self.spool_dir.exists():
            return []

        results: list[dict[str, Any]] = []
        for filepath in sorted(self.spool_dir.glob("*.json")):
            try:
                data = json.loads(filepath.read_text(encoding="utf-8"))
                results.append(data)
                filepath.unlink()
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Spool consume failed for %s: %s", filepath.name, exc)
                continue
        return results

    def consume_file(self, filename: str) -> dict[str, Any] | None:
        """Read and delete one spool file by name — REQ-101 req 044.

        Returns result dict or None if file not found.
        """
        filepath = _validated_spool_path(self.spool_dir, filename)
        if filepath is None:
            return None
        try:
            data = json.loads(filepath.read_text(encoding="utf-8"))
            filepath.unlink()
            return data
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Spool consume failed for %s: %s", filename, exc)
            return None

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
