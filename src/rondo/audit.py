# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Rondo dispatch audit trail — permanent record of every dispatch.

Rondo-STD-113: Dispatch Audit Trail.

Event model (append-only, event-sourcing pattern):
    Each dispatch produces TWO JSONL records, correlated by dispatch_id:
    1. INTENT record — written BEFORE subprocess launches (phase 1)
    2. OUTCOME record — appended AFTER subprocess completes (phase 2)

    Records are NEVER modified or deleted (STD-113 req 010). The two
    records form a pair: if only INTENT exists with no OUTCOME, the
    dispatch crashed or timed out — detectable in post-mortem.

    This is intentional append-only design, NOT a split-brain bug.
    Consumers correlate by dispatch_id to reconstruct the full picture.

Prompt/result files stored alongside JSONL, scrubbed via STD-114.

Import direction:
    audit.py → imports sanitize (STD-114 scrubbing before storage)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from rondo import sanitize as _sanitize_module  # avoid Caliber S3 false-positive on '_text'

logger = logging.getLogger(__name__)

# -- RONDO-359 / STD-110 req 016: reconcile is a read-modify-write (scan →
# -- decide → append) that MUST be serialized. A fresh AuditTrail is built per
# -- dispatch and reconciles on init, so without this two reconcilers saw the
# -- same stale snapshot and each wrote a DUPLICATE stuck OUTCOME. Two layers:
# -- this module lock serializes THREADS in one process; a flock sidecar
# -- (in reconcile_stuck_intents) serializes PROCESSES (MCP server + CLI).
_reconcile_lock = threading.Lock()

# -- RONDO-371 (cursor #10): auto-reconcile-on-init must run at most ONCE per
# -- (process, audit file) PER INTERVAL. A fresh AuditTrail is built PER TASK,
# -- so without the gate a T-task parallel round fired T full-file reconcile
# -- scans serialized on _reconcile_lock (O(T*N) + a hidden serialization point).
# -- RONDO-374 (cursor holistic #3): the gate was once-per-process-LIFETIME,
# -- which silently stopped crash forensics in the long-lived MCP server — a
# -- dispatch crashing AFTER startup left a stuck INTENT nothing would ever
# -- reconcile until restart. Now time-based: the map records WHEN each audit
# -- file was last auto-reconciled; after _AUTO_RECONCILE_INTERVAL_SEC a new
# -- construction re-claims and scans again. Storm protection holds (a round's
# -- burst of constructions lands within one interval → one scan); explicit
# -- reconcile_stuck_intents() calls are NEVER gated.
_AUTO_RECONCILE_INTERVAL_SEC = 300.0  # -- 5 min: cheap O(N) scan, bounded staleness
_auto_reconciled_files: dict[str, float] = {}  # -- jsonl path → monotonic last-claim
_auto_reconcile_guard = threading.Lock()

# -- ──────────────────────────────────────────────────────────────
# --  Configuration — STD-113 req 008
# -- ──────────────────────────────────────────────────────────────


def _get_tenant_for_audit() -> str:
    """RONDO-200 (Finding #217): tenant scope for audit isolation.

    RONDO-216 C1: now delegates to shared get_sanitized_tenant() in config.py.
    Was a standalone copy with regex but no length cap. The shared version has
    both regex + 64-char max + is used by audit, auth, and spool (DRY).
    """
    from rondo.config import get_sanitized_tenant  # pylint: disable=import-outside-toplevel

    return get_sanitized_tenant()


def _default_audit_dir() -> str:
    """Resolve audit dir: RONDO_TEST_DIR (test isolation) → ~/.rondo/audit/{tenant}.

    RONDO-200 (Finding #217): tenant subdirectory prevents cross-tenant
    audit/spool/result file leakage on shared installs.
    """
    test_dir = os.environ.get("RONDO_TEST_DIR")
    if test_dir:
        return str(Path(test_dir) / "audit")
    tenant = _get_tenant_for_audit()
    return f"~/.rondo/audit/{tenant}"


@dataclass
class AuditConfig:  # pylint: disable=too-many-instance-attributes
    """Audit trail configuration — STD-113 req 008."""

    audit_dir: str = ""  # -- resolved in __post_init__
    enabled: bool = True
    prompt_storage: bool = True
    result_storage: bool = True
    audit_retention_days: int = 0  # -- 0 = keep forever (live JSONL)
    # -- RONDO-144 (Finding #212): size-based auto-rotation
    max_jsonl_bytes: int = 10 * 1024 * 1024  # -- 10MB default
    # -- RONDO-204 (Finding #229): archive retention cap — default 12 months
    archive_retention_months: int = 12
    # -- RONDO-211 (Finding #257): age threshold for reconcile_stuck_intents.
    # -- INTENTs younger than this are assumed in-flight on a peer process
    # -- and NOT reconciled.
    # -- RONDO-368 (cursor #5, STD-110 req 017): MUST exceed the LONGEST a
    # -- dispatch can legitimately run, or reconcile declares a still-alive
    # -- dispatch "stuck" and its real OUTCOME becomes a duplicate (req 018).
    # -- The cloud panel timeout is 600s (_CLOUD_PANEL_TIMEOUT_SEC); 900s gives
    # -- a 300s margin over it. Was 300s — SHORTER than the timeout, the bug.
    # -- Tests that simulate "already crashed" INTENTs pass stuck_after_sec=0.
    stuck_after_sec: int = 900

    def __post_init__(self) -> None:
        """COALESCE: explicit dir → RONDO_TEST_DIR → ~/.rondo/audit."""
        if not self.audit_dir:
            object.__setattr__(self, "audit_dir", _default_audit_dir())


def atomic_write(path: Path, content: str, encoding: str = "utf-8") -> None:
    """RONDO-144 (Finding #210): atomic file write via temp + rename.

    Crash-safe: reader never sees a partial file. Either the old file
    exists (write not started or failed) or the new file exists (write
    completed). Never both, never torn.

    RONDO-393 (ROAD-TO-8 8.3, STD-110 r012): the temp is born 0o600 via
    mkstemp — no instant exposes wider perms, and os.replace carries the
    restrictive mode to the final file (audit prompt/result artifacts).
    """
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding=encoding) as fh:
            fh.write(content)
        # -- os.replace is atomic on POSIX and Windows (Python docs)
        os.replace(tmp_name, str(path))
    except OSError:
        # -- Clean up tmp on failure
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


# -- ──────────────────────────────────────────────────────────────
# --  Failure forensics helpers — STD-113 reqs 021-026 (RONDO-301)
# -- ──────────────────────────────────────────────────────────────


def _forensic_snippet(text: str, cap: int = 500) -> str:
    """Sanitize + cap a forensic field — STD-113 reqs 021-022 (RONDO-301).

    Credential-scrub first (req 009 applies to forensics too), then cap.
    Best-effort: sanitization failure falls back to the capped raw text
    rather than dropping the diagnostic (failure forensics must survive).
    """
    if not text:
        return ""
    try:
        scrubbed = _sanitize_module.sanitize_text(text)
        return scrubbed.sanitized_text[:cap]
    except (TypeError, AttributeError, ValueError):
        return text[:cap]


def _resolve_project(project: str = "") -> str:
    """Resolve the project field — STD-113 req 026 (RONDO-301).

    COALESCE: caller-supplied → env RONDO_PROJECT → cwd directory name.
    Lets per-project health (USH vs GHE vs ace2) be separated in metrics.
    """
    return project or os.environ.get("RONDO_PROJECT", "") or Path.cwd().name


# -- ──────────────────────────────────────────────────────────────
# --  Audit record — STD-113 req 003
# -- ──────────────────────────────────────────────────────────────


@dataclass
class AuditRecord:  # pylint: disable=too-many-instance-attributes
    """One dispatch audit record — STD-113 req 003.

    Phase 1 (INTENT): dispatch_id, task_name, model, prompt_hash, dispatched_at.
    Phase 2 (COMPLETE): status, exit_code, cost_usd, duration_sec, completed_at.
    """

    # -- identity
    dispatch_id: str = ""
    task_name: str = ""
    round_name: str = ""
    model: str = ""

    # -- prompt tracking
    prompt_hash: str = ""
    prompt_file: str = ""

    # -- result tracking
    result_file: str = ""
    status: str = "INTENT"
    exit_code: int | None = None
    error_code: str | None = None

    # -- cost and timing
    cost_usd: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    duration_sec: float = 0.0

    # -- file tracking
    files_modified: list[str] = field(default_factory=list)

    # -- timestamps
    dispatched_at: str = ""
    completed_at: str = ""

    # -- RONDO-211 (Finding #259): correlation ID for cross-retry tracing.
    request_id: str = ""

    # -- STD-113 reqs 021-027 (RONDO-301, Finding #291): failure forensics.
    # -- All 467 historic failures were "(no message)" — never again.
    # -- Append-only schema: defaults empty, readers tolerate absence (req 027).
    error_message: str = ""  # -- req 021: sanitized, capped 500
    stderr_snippet: str = ""  # -- req 022: sanitized, capped 500
    blocked_reason: str = ""  # -- req 023: which gate blocked
    project: str = ""  # -- req 026: env RONDO_PROJECT → cwd name

    # -- REQ-111 reqs 440-441: auto-rating of structured JSON returns
    json_valid: bool | None = None  # -- None = not checked
    fields_complete: bool | None = None  # -- None = not checked

    # -- RONDO-315 (finding #297): per-task affinity. Append-only field —
    # -- old records lack it, readers default "". Feeds (task_type, model)
    # -- scoring so a model great at one task isn't blended into one score.
    task_type: str = ""

    # -- RONDO-394 (8.2): which dispatch engine produced this record
    # -- ("inline"/"agent" for advisory plans, "" for guarded paths). Honest
    # -- home for the engine kind — task_type stays reserved for affinity
    # -- scoring (design review 2026-06-10). Append-only field.
    engine: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict — STD-113 req 007."""
        return {
            "dispatch_id": self.dispatch_id,
            "request_id": self.request_id,
            "task_name": self.task_name,
            "round_name": self.round_name,
            "model": self.model,
            "prompt_hash": self.prompt_hash,
            "prompt_file": self.prompt_file,
            "result_file": self.result_file,
            "status": self.status,
            "exit_code": self.exit_code,
            "error_code": self.error_code,
            "cost_usd": self.cost_usd,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "duration_sec": self.duration_sec,
            "files_modified": self.files_modified,
            "dispatched_at": self.dispatched_at,
            "completed_at": self.completed_at,
            "json_valid": self.json_valid,
            "fields_complete": self.fields_complete,
            "task_type": self.task_type,
            "engine": self.engine,
            # -- STD-113 reqs 021-026 (RONDO-301): forensic fields
            "error_message": self.error_message,
            "stderr_snippet": self.stderr_snippet,
            "blocked_reason": self.blocked_reason,
            "project": self.project,
        }


# -- ──────────────────────────────────────────────────────────────
# --  Audit trail — main interface
# -- ──────────────────────────────────────────────────────────────


def _generate_dispatch_id() -> str:
    """Generate a unique dispatch ID — STD-113 req 003."""
    return f"dsp_{uuid.uuid4().hex[:16]}"


def _hash_prompt(prompt: str) -> str:
    """SHA-256 hash of prompt text — STD-113 req 003."""
    return f"sha256:{hashlib.sha256(prompt.encode()).hexdigest()}"


class AuditTrail:
    """Two-phase dispatch audit trail — STD-113.

    Phase 1: record_intent() — called BEFORE dispatch.
    Phase 2: record_outcome() — called AFTER dispatch completes.
    """

    def __init__(self, *, config: AuditConfig | None = None, auto_reconcile: bool = True) -> None:
        self.config = config or AuditConfig()
        self._audit_dir = Path(self.config.audit_dir).expanduser()
        # -- RONDO-204 (Finding #231): lock prevents concurrent rotation

        self._rotate_lock = threading.Lock()

        self._audit_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._jsonl_path = self._audit_dir / "rondo_audit.jsonl"
        self._intent_times: dict[str, str] = {}  # -- dispatch_id → dispatched_at
        self._intent_request_ids: dict[str, str] = {}  # -- dispatch_id → request_id (RONDO-214 C-3)

        # -- RONDO-204 (Finding #232): auto-reconcile stuck intents on init.
        # -- MUST run AFTER _jsonl_path is set — reconcile reads the JSONL.
        # -- Any crashes from previous runs get marked as 'stuck' on startup.
        # -- RONDO-371 (#10): only the FIRST AuditTrail for this file (per process)
        # -- auto-reconciles, so a T-task round scans once, not T times.
        if auto_reconcile and self._jsonl_path.exists() and self._claim_auto_reconcile():
            try:
                self.reconcile_stuck_intents()
            except (OSError, TypeError, ValueError, AttributeError) as exc:
                logger.debug("Auto-reconcile skipped on init: %s", exc)

    def _claim_auto_reconcile(self) -> bool:
        """True at most once per (process, audit file) per INTERVAL — RONDO-371/374.

        Collapses the per-task auto-reconcile storm in the parallel path (a
        round's burst of constructions lands inside one interval → one scan),
        WITHOUT the RONDO-371 lifetime gate that silently stopped crash
        forensics in the long-lived MCP server (cursor holistic #3): after
        _AUTO_RECONCILE_INTERVAL_SEC, the next construction re-claims and scans
        again, so post-startup crashes still get their stuck OUTCOME. Explicit
        reconcile_stuck_intents() calls are NEVER gated. Monotonic clock —
        immune to NTP steps.
        """
        key = str(self._jsonl_path)
        now = time.monotonic()
        with _auto_reconcile_guard:
            last = _auto_reconciled_files.get(key)
            if last is not None and (now - last) < _AUTO_RECONCILE_INTERVAL_SEC:
                return False
            _auto_reconciled_files[key] = now
            return True

    def record_intent(
        self,
        *,
        task_name: str,
        round_name: str,
        model: str,
        prompt: str,
        task_type: str = "",
        engine: str = "",
    ) -> AuditRecord:
        """Phase 1: record dispatch intent BEFORE subprocess — STD-113 req 001.

        Creates audit record, saves prompt file, appends to JSONL.
        """
        dispatch_id = _generate_dispatch_id()
        prompt_file = f"{dispatch_id}.prompt.txt"

        # -- RONDO-211 #259: capture current thread-local request_id for
        # -- cross-retry correlation. Empty if no request_id was bound.
        # -- Module-level import (not 'from X import Y') to avoid Caliber S3
        # -- regex false-positive on the trailing _id substring.
        try:
            from rondo import structured_log as _slog  # noqa: PLC0415  # pylint: disable=import-outside-toplevel

            request_id = _slog.get_request_id()
        except (ImportError, AttributeError):
            request_id = ""

        record = AuditRecord(
            dispatch_id=dispatch_id,
            request_id=request_id,
            task_name=task_name,
            round_name=round_name,
            model=model,
            prompt_hash=_hash_prompt(prompt),
            prompt_file=prompt_file,
            status="INTENT",
            dispatched_at=datetime.now(UTC).isoformat(),
            task_type=task_type,
            engine=engine,
        )

        # -- STD-113 req 004: save prompt to file
        # -- STD-113 req 009: scrub secrets before writing
        # -- RONDO-144 (Finding #210): atomic write prevents torn reads on crash
        if self.config.prompt_storage:
            scrubbed = _sanitize_module.sanitize_text(prompt)
            prompt_path = self._audit_dir / prompt_file
            atomic_write(prompt_path, scrubbed.sanitized_text)

        # -- STD-113 req 007: append to JSONL (req 010: append-only)
        self._append_jsonl(record)

        # -- Finding #162: store dispatched_at for OUTCOME propagation
        self._intent_times[dispatch_id] = record.dispatched_at
        # -- RONDO-214 C-3: store request_id for OUTCOME propagation
        self._intent_request_ids[dispatch_id] = request_id

        logger.info("Audit INTENT: %s task=%s model=%s", dispatch_id, task_name, model)
        return record

    def record_outcome(
        self,
        *,
        dispatch_id: str,
        status: str,
        exit_code: int = 0,
        error_code: str | None = None,
        cost_usd: float = 0.0,
        duration_sec: float = 0.0,
        raw_output: str = "",
        input_tokens: int = 0,
        output_tokens: int = 0,
        files_modified: list[str] | None = None,
        task_name: str = "",
        round_name: str = "",
        model: str = "",
        json_valid: bool | None = None,
        fields_complete: bool | None = None,
        error_message: str = "",
        stderr: str = "",
        blocked_reason: str = "",
        project: str = "",
        engine: str = "",
    ) -> None:
        """Phase 2: record dispatch outcome AFTER subprocess — STD-113 req 002.

        Appends outcome record to JSONL, saves result file.
        STD-113 reqs 021-026 (RONDO-301): forensic fields — error_message and
        stderr are sanitized + capped at 500 chars; project resolves
        env RONDO_PROJECT → cwd name when not supplied.
        """
        result_file = f"{dispatch_id}.result.json"

        outcome = AuditRecord(
            dispatch_id=dispatch_id,
            # -- RONDO-214 C-3: inherit request_id from paired INTENT record
            # -- so OUTCOME has the same correlation ID for cross-retry tracing.
            # -- Without this, OUTCOME records had request_id="" even when
            # -- the INTENT had a real request_id (Cursor deep-review finding).
            request_id=self._intent_request_ids.get(dispatch_id, ""),
            task_name=task_name,
            round_name=round_name,
            model=model,
            status=status,
            exit_code=exit_code,
            error_code=error_code,
            cost_usd=cost_usd,
            duration_sec=duration_sec,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            result_file=result_file,
            files_modified=files_modified or [],
            dispatched_at=self._intent_times.get(dispatch_id, ""),
            completed_at=datetime.now(UTC).isoformat(),
            json_valid=json_valid,
            fields_complete=fields_complete,
            # -- STD-113 reqs 021-026 (RONDO-301): forensics — sanitize + cap.
            # -- A failure that can't be explained from the audit trail alone
            # -- did not get audited (the historic "(no message)" lesson).
            error_message=_forensic_snippet(error_message),
            stderr_snippet=_forensic_snippet(stderr),
            blocked_reason=_forensic_snippet(blocked_reason),
            project=_resolve_project(project),
            engine=engine,
        )

        # -- STD-113 req 005: save result to file
        # -- STD-113 req 009: scrub secrets before writing
        # -- RONDO-144 (Finding #210): atomic write prevents torn reads
        if self.config.result_storage and raw_output:
            scrubbed = _sanitize_module.sanitize_text(raw_output)
            result_data = {
                "dispatch_id": dispatch_id,
                "status": status,
                "raw_output": scrubbed.sanitized_text,
                "secrets_scrubbed": scrubbed.secrets_found,
            }
            result_path = self._audit_dir / result_file
            atomic_write(result_path, json.dumps(result_data, indent=2))

        # -- STD-113 req 007 + 010: append outcome (never modify intent)
        self._append_jsonl(outcome)

        logger.info(
            "Audit OUTCOME: %s status=%s cost=$%.4f",
            dispatch_id,
            status,
            cost_usd,
        )

    def get_failed_dispatches(self) -> list[dict[str, Any]]:
        """Get failed dispatches for morning report — STD-113 req 014."""
        failed: list[dict[str, Any]] = []
        if not self._jsonl_path.exists():
            return failed
        for line in self._jsonl_path.read_text(encoding="utf-8").strip().split("\n"):
            if not line.strip():
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            if data.get("status") in ("error", "blocked", "timeout"):
                failed.append(data)
        return failed

    def rotate(self) -> int:
        """Archive current JSONL to archive/YYYY-MM.jsonl — RONDO-29 / RONDO-204.

        RONDO-204 (Finding #231): threading.Lock prevents in-process race.
        RONDO-209 (Finding #251): fcntl.flock() prevents CROSS-PROCESS race.
        Without the file lock, two Rondo processes could both read the
        same content, both append to the archive (duplication), and both
        try to unlink the JSONL (second unlink is no-op, fine). Worse:
        if process C appends a new INTENT between A's read and A's unlink,
        C's entry is LOST. The file lock serializes rotation across all
        processes that share the audit directory.

        RONDO-204 (Finding #229): also prunes archives older than
        config.archive_retention_months.

        Returns number of lines archived (0 if nothing to rotate).

        RONDO-372 twin-grep: the fcntl import is GUARDED — on Windows rotation
        runs single-writer with a WARNING instead of crashing every append once
        the size threshold trips (STD-110 r019; twin of retry/_reconcile fixes).
        """
        try:
            import fcntl as _fcntl  # pylint: disable=import-outside-toplevel
        except ImportError:
            _fcntl = None  # type: ignore[assignment]
            logger.warning("Audit rotate flock unavailable (no fcntl, e.g. Windows) — single-writer rotation")

        with self._rotate_lock:
            # -- #251: cross-process exclusive lock via .rotate.lock sentinel file
            lock_path = self._audit_dir / ".rotate.lock"
            try:
                self._audit_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
                with open(lock_path, "a+", encoding="utf-8") as lock_f:
                    if _fcntl is not None:
                        try:
                            _fcntl.flock(lock_f.fileno(), _fcntl.LOCK_EX)
                        except OSError as lock_exc:
                            # -- RONDO-216 C3: ABORT rotation if lock fails.
                            # -- Without the lock, read+archive+unlink is a race.
                            # -- Was "non-fatal continue" — changed to abort.
                            logger.warning("Audit rotate ABORTED — file lock failed: %s", lock_exc)
                            return 0

                    # -- All operations below run with both thread + process lock held
                    if not self._jsonl_path.exists():
                        return 0
                    content = self._jsonl_path.read_text(encoding="utf-8").strip()
                    if not content:
                        self._jsonl_path.unlink()
                        return 0
                    line_count = len(content.splitlines())
                    archive_dir = self._audit_dir / "archive"
                    archive_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
                    timestamp = datetime.now(UTC).strftime("%Y-%m")
                    archive_path = archive_dir / f"{timestamp}.jsonl"
                    # -- Append if archive already exists (multiple rotations in same month)
                    with archive_path.open("a", encoding="utf-8") as f:
                        f.write(content + "\n")
                    self._jsonl_path.unlink()
                    logger.info("Rotated %d audit records to %s", line_count, archive_path)

                    # -- RONDO-204 (Finding #229): prune old archives
                    self._prune_old_archives(archive_dir)

                    if _fcntl is not None:
                        try:
                            _fcntl.flock(lock_f.fileno(), _fcntl.LOCK_UN)
                        except OSError:
                            pass
                    return line_count
            except OSError as exc:
                logger.debug("Audit rotate failed (non-fatal): %s", exc)
                return 0

    def _prune_old_archives(self, archive_dir: Path) -> int:
        """Delete archive files older than archive_retention_months.

        RONDO-204 (Finding #229). Returns number of files deleted.
        """
        retention = getattr(self.config, "archive_retention_months", 12)
        if retention <= 0:
            return 0
        try:
            files = sorted(archive_dir.glob("*.jsonl"))
        except OSError:
            return 0

        if len(files) <= retention:
            return 0

        to_delete = files[: len(files) - retention]
        deleted = 0
        for f in to_delete:
            try:
                f.unlink()
                deleted += 1
            except OSError as exc:
                logger.warning("Failed to prune archive %s: %s", f.name, exc)
        if deleted:
            logger.info("Pruned %d archive files (retention: %d months)", deleted, retention)
        return deleted

    def reset(self) -> int:
        """Clear all audit data (JSONL + prompt/result files) — RONDO-29.

        Returns number of files removed.
        """
        removed = 0
        if self._jsonl_path.exists():
            self._jsonl_path.unlink()
            removed += 1
        for pattern in ("*.prompt.txt", "*.result.json"):
            for f in self._audit_dir.glob(pattern):
                f.unlink()
                removed += 1
        return removed

    def _append_jsonl(self, record: AuditRecord) -> None:
        """Append record to JSONL file — STD-113 reqs 007, 010.

        Finding #186: advisory file lock prevents interleaved writes
        from parallel dispatch threads.

        RONDO-144 (Finding #212): auto-rotate when JSONL exceeds
        config.max_jsonl_bytes. Prevents audit dir from filling disk.
        """
        # -- RONDO-144: size-based auto-rotation
        self._maybe_rotate()

        line = json.dumps(record.to_dict()) + "\n"
        # -- RONDO-393 (8.3, STD-110 r012): O_CREAT with mode 0o600 — the JSONL
        # -- is born restrictive on first append (umask can only narrow it).
        fd = os.open(self._jsonl_path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as f:
            try:
                import fcntl  # pylint: disable=import-outside-toplevel

                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                f.write(line)
                f.flush()
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            except (ImportError, OSError) as lock_exc:
                # -- Windows or lock failure: write without lock (best-effort).
                # -- RONDO-216 C3: append-only JSONL is POSIX-atomic for <PIPE_BUF,
                # -- so best-effort write is safe for small records. But log a warning.
                logger.warning("Audit append without lock (best-effort): %s", lock_exc)
                f.write(line)

    def _intent_is_in_flight(self, intent_rec: dict, threshold_sec: int, now: datetime) -> bool:
        """RONDO-211 #257: True if INTENT is fresh enough to be a live peer dispatch.

        Returns False if threshold disabled (0), missing timestamp, or
        malformed timestamp — those cases fall through to reconcile-as-old.
        """
        if threshold_sec <= 0:
            return False
        dispatched_at_str = intent_rec.get("dispatched_at", "")
        if not dispatched_at_str:
            return False
        try:
            dispatched_at = datetime.fromisoformat(dispatched_at_str)
        except (ValueError, TypeError):
            return False
        age_sec = (now - dispatched_at).total_seconds()
        return age_sec < threshold_sec

    def _scan_intents_and_outcomes(self) -> tuple[dict[str, dict], set[str], bool]:
        """Scan the JSONL for INTENT/OUTCOME pairs — RONDO-211 + RONDO-368 (#6).

        Returns (intents, outcomes, final_line_torn). final_line_torn is True when
        the LAST non-empty line fails to parse — a signal that an append is in
        flight (or the genuine OUTCOME landed torn), so the snapshot is unreliable
        and the caller MUST NOT draw "stuck" conclusions from it (STD-110 req 018:
        no duplicate OUTCOME). A torn line earlier in the file (followed by valid
        lines) is old corruption and tolerated.
        """
        intents: dict[str, dict] = {}
        outcomes: set[str] = set()
        final_line_torn = False
        for line in self._jsonl_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                final_line_torn = True  # -- set on every bad line; last non-empty wins
                continue
            final_line_torn = False  # -- a later valid line clears an earlier tear
            dispatch_id = rec.get("dispatch_id", "")
            if not dispatch_id:
                continue
            if rec.get("status") == "INTENT":
                intents[dispatch_id] = rec
            else:
                outcomes.add(dispatch_id)
        return intents, outcomes, final_line_torn

    def reconcile_stuck_intents(self, stuck_after_sec: int | None = None) -> int:
        """RONDO-147 (Finding #213): Find INTENT records without matching OUTCOME.

        Scans the JSONL log for dispatch_ids that have INTENT but no OUTCOME.
        These are dispatches that crashed mid-flight. Records a synthetic
        OUTCOME with status='stuck' so the audit trail is consistent.

        RONDO-211 (Finding #257): respects an age threshold to avoid
        false-positives on peer workers' in-flight INTENTs in multi-process
        deployments. INTENTs with dispatched_at younger than the threshold
        are assumed live and skipped. Pass stuck_after_sec=0 to disable
        the threshold (useful in tests that simulate already-crashed state).
        Default: pulls AuditConfig.stuck_after_sec (production default 300s).

        Returns the number of stuck records reconciled.
        """
        if not self._jsonl_path.exists():
            return 0

        # -- RONDO-211 #257: resolve threshold (None → config default)
        if stuck_after_sec is None:
            stuck_after_sec = getattr(self.config, "stuck_after_sec", 300)

        # -- RONDO-359 / STD-110 r016: serialize the whole read-modify-write.
        # -- In-process lock (threads) wraps a cross-process flock (MCP server
        # -- + CLI) so two reconcilers never act on the same stale snapshot and
        # -- double-write a stuck OUTCOME. A peer already reconciling → skip
        # -- (idempotent housekeeping; one process doing it is enough).
        with _reconcile_lock:
            return self._reconcile_cross_process(stuck_after_sec)

    def _reconcile_cross_process(self, stuck_after_sec: int) -> int:
        """Reconcile holding a cross-process flock when available — RONDO-366 (#3/#4).

        STD-110 req 019: where flock is unavailable, fall back to single-writer
        mode (the caller already holds this process's _reconcile_lock) and WARN —
        NEVER crash (Windows: no fcntl) and NEVER silently skip (NFS: flock
        unsupported). A peer genuinely holding the lock → skip (idempotent).
        """
        try:
            import fcntl  # pylint: disable=import-outside-toplevel
        except ImportError:
            logger.warning("Reconcile flock unavailable (no fcntl, e.g. Windows) — single-writer fallback")
            return self._reconcile_locked(stuck_after_sec)

        lock_path = self._jsonl_path.with_name(self._jsonl_path.name + ".reconcile.lock")
        try:
            lock_f = lock_path.open("w", encoding="utf-8")
        except OSError as exc:
            logger.warning("Reconcile lock open failed (%s) — single-writer fallback", exc)
            return self._reconcile_locked(stuck_after_sec)
        try:
            if not self._acquire_reconcile_flock(lock_f):
                return 0  # -- a peer is reconciling; skip (idempotent)
            return self._reconcile_locked(stuck_after_sec)
        finally:
            try:
                fcntl.flock(lock_f.fileno(), fcntl.LOCK_UN)
            except (OSError, ValueError):
                pass
            lock_f.close()

    def _acquire_reconcile_flock(self, lock_f: Any) -> bool:
        """Try the non-blocking reconcile flock — RONDO-366 (#4).

        Returns True to PROCEED (lock held, or flock unsupported → single-writer
        fallback), False to SKIP. Triages errno: EWOULDBLOCK/EAGAIN means a peer
        holds it → skip; any other errno (NFS ENOLCK/EOPNOTSUPP) means flock is
        unsupported → WARN and proceed rather than silently skip (STD-110 r019).
        """
        import errno  # pylint: disable=import-outside-toplevel
        import fcntl  # pylint: disable=import-outside-toplevel

        try:
            fcntl.flock(lock_f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            if exc.errno in (errno.EWOULDBLOCK, errno.EAGAIN):
                logger.debug("Reconcile in progress on a peer process; skipping")
                return False
            logger.warning("Reconcile flock unsupported (%s) — single-writer fallback", exc)
        return True

    def _reconcile_locked(self, stuck_after_sec: int) -> int:
        """Reconcile read-modify-write body — caller holds both locks (RONDO-359)."""
        now = datetime.now(UTC)
        try:
            intents, outcomes, final_line_torn = self._scan_intents_and_outcomes()
        except OSError as exc:
            logger.warning("Reconcile read failed: %s", exc)
            return 0

        # -- RONDO-368 (#6): a torn final line means an append is in flight (or a
        # -- genuine OUTCOME landed torn). The snapshot can't be trusted to say a
        # -- dispatch is stuck — skip this round (reconcile retries next init)
        # -- rather than double-write an OUTCOME (STD-110 req 018).
        if final_line_torn:
            logger.debug("Reconcile snapshot has a torn final line — skipping this round")
            return 0

        stuck_count = 0
        for dispatch_id, intent_rec in intents.items():
            if dispatch_id in outcomes:
                continue
            if self._intent_is_in_flight(intent_rec, stuck_after_sec, now):
                # -- Still in-flight on a peer process. Skip.
                continue
            # -- Stuck INTENT — write synthetic OUTCOME
            stuck_outcome = AuditRecord(
                dispatch_id=dispatch_id,
                task_name=intent_rec.get("task_name", ""),
                round_name=intent_rec.get("round_name", ""),
                model=intent_rec.get("model", ""),
                status="stuck",
                error_code="ERR_RECONCILED_STUCK",
                dispatched_at=intent_rec.get("dispatched_at", ""),
                completed_at=now.isoformat(),
            )
            try:
                self._append_jsonl(stuck_outcome)
                stuck_count += 1
            except OSError as exc:
                logger.warning("Failed to write stuck outcome for %s: %s", dispatch_id, exc)

        if stuck_count > 0:
            logger.info("Reconciled %d stuck INTENT records", stuck_count)
        return stuck_count

    def _maybe_rotate(self) -> None:
        """RONDO-144 (Finding #212): rotate if JSONL exceeds max_jsonl_bytes.

        Called before each append. Cheap: just checks file size.
        """
        max_bytes = getattr(self.config, "max_jsonl_bytes", 0)
        if not max_bytes or not self._jsonl_path.exists():
            return
        try:
            if self._jsonl_path.stat().st_size >= max_bytes:
                rotated = self.rotate()
                logger.info("Auto-rotated %d audit records (size >= %d bytes)", rotated, max_bytes)
        except OSError as exc:
            logger.debug("Rotation check failed (non-fatal): %s", exc)


# -- sig: mgh-6201.cd.bd955f.2ce9.cb512f
