# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Dispatch idempotency cache — RONDO-147.

Rondo-REQ-100 req 074 (extension): client-side dedupe to prevent
duplicate billable API calls on retry.

Finding #214: Retries (intentional via rondo_retry or accidental)
caused duplicate LLM API calls = duplicate cost + duplicate audit records.
No client-side dedupe meant the same prompt+model could be billed twice.

RONDO-205 Finding #241: cross-process dedupe via JSON file persistence.
Multi-process and multi-worker deployments share the cache through a
file at ~/.rondo/idempotency.jsonl.

RONDO-209 Finding #246: SWITCHED FROM JSON READ-MODIFY-WRITE TO APPEND-ONLY
JSONL to eliminate the cross-process race. The previous implementation was:
    read file → modify dict → atomic write (tmp+rename)
Which was NOT atomic at the read-modify-write level. Two processes could:
    A: read {} → write {X:result_A}
    B: read {} (before A's write) → write {Y:result_B}  ← A's entry LOST
The append-only JSONL pattern eliminates this race entirely:
    - cache_result: O(1) append of a new line to the JSONL
    - get_cached_result: linear scan of the file, latest entry wins
    - Expired entries filtered out at read time
    - Periodic compaction (when file grows beyond threshold) re-writes clean file
This matches the proven pattern used by audit.py/spool.py/history.py.

This module provides:
    compute_idempotency_key(prompt, model, execution) — SHA-256 of prompt+model+execution
    get_cached_result(key) — return cached dict if within TTL
    cache_result(key, result) — store result for future dedupe

Default TTL: 5 minutes. Cache keyed by (prompt_hash, model, execution).
Thread-safe via lock. Cross-process via append-only JSONL backing store.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from dataclasses import asdict, dataclass, is_dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# -- Default TTL: 5 minutes
DEFAULT_TTL_SEC = 300

# -- Module-level cache + lock (in-memory fast path)
_cache: dict[str, tuple[Any, float]] = {}
_cache_lock = threading.Lock()
# -- #241: file I/O lock prevents torn reads during atomic write+rename race
_file_lock = threading.Lock()


# -- RONDO-209 #246: compaction threshold — rewrite JSONL when it exceeds
# -- this size to prevent unbounded growth. Compaction runs opportunistically.
_COMPACT_THRESHOLD_BYTES = 1024 * 1024  # -- 1 MB


def _default_cache_file() -> Path:
    """Path to the cross-process idempotency JSONL file.

    RONDO-209 #246: switched from .json to .jsonl (append-only) to eliminate
    cross-process read-modify-write race. Defaults to ~/.rondo/idempotency.jsonl;
    honors RONDO_TEST_DIR for isolation.
    """
    test_dir = os.environ.get("RONDO_TEST_DIR")
    if test_dir:
        return Path(test_dir) / "idempotency.jsonl"
    return Path(os.path.expanduser("~/.rondo/idempotency.jsonl"))


def _append_cache_entry(path: Path, key: str, payload: dict[str, Any], cached_at_wall: float) -> None:
    """Append a single cache entry as one JSONL line — #246.

    POSIX guarantees that a single write() < PIPE_BUF (typically 4KB) is
    atomic. JSON lines are typically <1KB each so append() is race-safe.
    This replaces the previous read-modify-write pattern that could lose
    entries under concurrent cross-process access.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        entry = {
            "key": key,
            "data": payload,
            "cached_at_wall": cached_at_wall,
        }
        # -- Use mode='a' + single newline-terminated write for atomic append.
        # -- open() with 'a' guarantees O_APPEND semantics on POSIX, so even
        # -- concurrent writers won't interleave within a single line.
        line = json.dumps(entry, default=str) + "\n"
        with open(path, "a", encoding="utf-8") as f:
            f.write(line)
    except (OSError, TypeError, ValueError) as exc:
        logger.debug("Idempotency JSONL append failed (non-fatal): %s", exc)


def _scan_cache_file(path: Path, ttl_sec: int) -> dict[str, tuple[Any, float]]:
    """Scan the JSONL file and return the latest valid entry per key — #246.

    Walks every line in the file. For each key, keeps the MOST RECENT entry
    (by cached_at_wall). Skips entries expired beyond ttl_sec. Malformed
    lines are silently skipped. Returns {key: (value, cached_at_wall)}.
    """
    result: dict[str, tuple[Any, float]] = {}
    try:
        if not path.exists():
            return result
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
    except OSError as exc:
        logger.debug("Idempotency JSONL read failed (non-fatal): %s", exc)
        return result

    cutoff = time.time() - ttl_sec
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except (ValueError, json.JSONDecodeError):
            continue
        if not isinstance(entry, dict):
            continue
        key = entry.get("key")
        cached_at = float(entry.get("cached_at_wall", 0.0))
        if not isinstance(key, str) or cached_at <= cutoff:
            continue
        # -- Later entries win (append order = write order)
        existing = result.get(key)
        if existing is None or cached_at > existing[1]:
            value = entry.get("data")
            if value is not None:
                result[key] = (value, cached_at)
    return result


def _compact_if_needed(path: Path) -> None:
    """Rewrite the JSONL file with only non-expired entries — #246.

    Runs opportunistically when the file exceeds _COMPACT_THRESHOLD_BYTES.
    RONDO-217: added fcntl.flock to prevent two processes compacting
    simultaneously (Option B finding — 2/3 providers flagged this race).
    If lock fails, skip compaction (try again next time).
    """
    try:
        if not path.exists() or path.stat().st_size < _COMPACT_THRESHOLD_BYTES:
            return

        lock_path = path.with_suffix(".compact.lock")
        try:
            import fcntl  # pylint: disable=import-outside-toplevel

            with open(lock_path, "a+", encoding="utf-8") as lock_f:
                try:
                    fcntl.flock(lock_f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError:
                    # -- Another process is compacting — skip, try next time
                    logger.debug("Idempotency compaction skipped — lock held by peer")
                    return

                fresh = _scan_cache_file(path, ttl_sec=DEFAULT_TTL_SEC)
                tmp_path = path.with_suffix(".tmp")
                with open(tmp_path, "w", encoding="utf-8") as f:
                    for k, (value, cached_at) in fresh.items():
                        f.write(json.dumps({"key": k, "data": value, "cached_at_wall": cached_at}, default=str) + "\n")
                os.replace(tmp_path, path)
                logger.debug("Idempotency JSONL compacted: %d live entries", len(fresh))

                fcntl.flock(lock_f.fileno(), fcntl.LOCK_UN)
        except ImportError:
            # -- Windows: no fcntl, fall back to unlocked compaction (benign)
            fresh = _scan_cache_file(path, ttl_sec=DEFAULT_TTL_SEC)
            tmp_path = path.with_suffix(".tmp")
            with open(tmp_path, "w", encoding="utf-8") as f:
                for k, (value, cached_at) in fresh.items():
                    f.write(json.dumps({"key": k, "data": value, "cached_at_wall": cached_at}, default=str) + "\n")
            os.replace(tmp_path, path)
            logger.debug("Idempotency JSONL compacted (no lock): %d live entries", len(fresh))
    except (OSError, TypeError, ValueError) as exc:
        logger.debug("Idempotency compaction failed (non-fatal): %s", exc)


def _serialize_result(result: Any) -> dict[str, Any] | None:
    """Serialize a TaskResult (or any dataclass/dict) to a JSON-safe dict.

    Returns None if the value is not serializable — caller treats as no-op.
    """
    try:
        if is_dataclass(result) and not isinstance(result, type):
            return asdict(result)
        if isinstance(result, dict):
            return result
        return None
    except (TypeError, ValueError) as exc:
        logger.debug("Idempotency serialize failed (non-fatal): %s", exc)
        return None


def compute_idempotency_key(prompt: str, model: str, execution: str = "") -> str:
    """Generate stable idempotency key from prompt + model + execution.

    Returns SHA-256 hex digest. Same prompt + same model + same execution = same key.
    """
    normalized = f"{model}\n{execution}\n{prompt}"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def get_cached_result(key: str, ttl_sec: int = DEFAULT_TTL_SEC) -> Any | None:
    """Return cached result if present AND within TTL. Else None.

    Two-layer lookup (#246 append-only JSONL):
      1. In-memory cache (fast path, current process)
      2. JSONL file scan (cross-process, O(N) in file size)

    Thread-safe. Expired entries filtered at scan time.
    """
    # -- Layer 1: in-memory (wall-clock because shared with file layer)
    with _cache_lock:
        if key in _cache:
            cached_value, cached_at = _cache[key]
            if time.time() - cached_at <= ttl_sec:
                return cached_value
            # -- Expired — evict
            del _cache[key]

    # -- Layer 2: JSONL file backing store (#246 append-only, race-safe)
    path = _default_cache_file()
    with _file_lock:
        fresh = _scan_cache_file(path, ttl_sec=ttl_sec)
    if key not in fresh:
        return None
    value, cached_at_wall = fresh[key]

    # -- Promote to in-memory so next read is fast
    with _cache_lock:
        _cache[key] = (value, cached_at_wall)
    return value


def cache_result(key: str, result: Any) -> None:
    """Store result for future idempotency lookups.

    RONDO-209 #246: append-only JSONL write — NO read-modify-write race.
    Writes to BOTH in-memory (fast path) AND JSONL file (cross-process).
    """
    now = time.time()
    with _cache_lock:
        _cache[key] = (result, now)

    # -- #246 cross-process layer: append-only, race-safe
    payload = _serialize_result(result)
    if payload is None:
        return  # -- not serializable → memory-only

    path = _default_cache_file()
    with _file_lock:
        _append_cache_entry(path, key, payload, now)
        # -- Opportunistic compaction when file grows beyond threshold
        _compact_if_needed(path)


def clear_cache() -> None:
    """Clear the entire idempotency cache. For testing/admin.

    Clears BOTH in-memory and JSON file layers.
    """
    with _cache_lock:
        _cache.clear()
    with _file_lock:
        path = _default_cache_file()
        try:
            if path.exists():
                path.unlink()
        except OSError as exc:
            logger.debug("Idempotency file unlink failed (non-fatal): %s", exc)


def cache_size() -> int:
    """Return current in-memory cache size (number of entries)."""
    with _cache_lock:
        return len(_cache)


@dataclass
class IdempotencyConfig:
    """Idempotency cache configuration."""

    enabled: bool = True
    ttl_sec: int = DEFAULT_TTL_SEC


# -- sig: mgh-6201.cd.bd955f.f1c0.f0c061
