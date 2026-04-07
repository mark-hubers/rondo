# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Dispatch idempotency cache — RONDO-147.

Rondo-REQ-100 req 074 (extension): client-side dedupe to prevent
duplicate billable API calls on retry.

Finding #214: Retries (intentional via rondo_retry or accidental)
caused duplicate LLM API calls = duplicate cost + duplicate audit records.
No client-side dedupe meant the same prompt+model could be billed twice.

RONDO-205 Finding #241: cross-process dedupe via JSON file persistence.
Multi-process and multi-worker deployments now share the cache through
a flat JSON file at ~/.rondo/idempotency.json. Atomic write via tmp+rename
prevents partial-read corruption. Rondo-STD-107 req 005: Rondo is
stateless — no sqlite3. JSON file matches audit/spool/history persistence.

This module provides:
    compute_idempotency_key(prompt, model) — SHA-256 of prompt+model
    get_cached_result(key) — return cached dict if within TTL
    cache_result(key, result) — store result for future dedupe

Default TTL: 5 minutes. Cache keyed by (prompt_hash, model).
Thread-safe via lock. Cross-process via JSON file backing store.
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


def _default_cache_file() -> Path:
    """Path to the cross-process idempotency JSON file — #241.

    Defaults to ~/.rondo/idempotency.json; honors RONDO_TEST_DIR for isolation.
    Rondo-STD-107 req 005: JSON file matches audit/spool/history pattern.
    """
    test_dir = os.environ.get("RONDO_TEST_DIR")
    if test_dir:
        return Path(test_dir) / "idempotency.json"
    return Path(os.path.expanduser("~/.rondo/idempotency.json"))


def _load_file_cache(path: Path) -> dict[str, dict[str, Any]]:
    """Read the on-disk JSON file and return its contents as a dict.

    Returns empty dict on any read/parse error — caller treats as cache miss.
    """
    try:
        if not path.exists():
            return {}
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        if not isinstance(data, dict):
            return {}
        return data
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        logger.debug("Idempotency file read failed (non-fatal): %s", exc)
        return {}


def _save_file_cache(path: Path, data: dict[str, dict[str, Any]]) -> None:
    """Atomically write the cache dict to the on-disk JSON file.

    Uses tmp file + os.replace for atomicity — concurrent readers
    never see a partial file. Non-fatal on any I/O error.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(data, default=str), encoding="utf-8")
        os.replace(tmp_path, path)
    except (OSError, TypeError, ValueError) as exc:
        logger.debug("Idempotency file write failed (non-fatal): %s", exc)


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


def compute_idempotency_key(prompt: str, model: str) -> str:
    """Generate stable idempotency key from prompt + model.

    Returns SHA-256 hex digest. Same prompt + same model = same key.
    """
    normalized = f"{model}\n{prompt}"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def get_cached_result(key: str, ttl_sec: int = DEFAULT_TTL_SEC) -> Any | None:
    """Return cached result if present AND within TTL. Else None.

    Two-layer lookup (#241):
      1. In-memory cache (fast path, current process)
      2. JSON file (cross-process, slower)

    Thread-safe. Expired entries are evicted on read from both layers.
    """
    # -- Layer 1: in-memory (wall-clock because shared with file layer)
    with _cache_lock:
        if key in _cache:
            cached_value, cached_at = _cache[key]
            if time.time() - cached_at <= ttl_sec:
                return cached_value
            # -- Expired — evict
            del _cache[key]

    # -- Layer 2: JSON file backing store (#241 cross-process)
    with _file_lock:
        file_data = _load_file_cache(_default_cache_file())
    entry = file_data.get(key)
    if not isinstance(entry, dict):
        return None
    cached_at_wall = float(entry.get("cached_at_wall", 0.0))
    if time.time() - cached_at_wall > ttl_sec:
        return None  # -- expired
    value = entry.get("data")
    if value is None:
        return None
    # -- Promote to in-memory so next read is fast
    with _cache_lock:
        _cache[key] = (value, cached_at_wall)
    return value


def cache_result(key: str, result: Any) -> None:
    """Store result for future idempotency lookups.

    Writes to BOTH in-memory (fast path) AND JSON file (#241 cross-process).
    If file write fails, in-memory still works — cache is an optimization.
    """
    now = time.time()
    with _cache_lock:
        _cache[key] = (result, now)

    # -- #241 cross-process layer
    payload = _serialize_result(result)
    if payload is None:
        return  # -- not serializable → memory-only

    with _file_lock:
        path = _default_cache_file()
        file_data = _load_file_cache(path)
        file_data[key] = {
            "data": payload,
            "cached_at_wall": now,
        }
        # -- #241: opportunistic GC of expired entries during write
        cutoff = now - DEFAULT_TTL_SEC
        expired_keys = [
            k for k, v in file_data.items() if isinstance(v, dict) and float(v.get("cached_at_wall", 0.0)) < cutoff
        ]
        for k in expired_keys:
            del file_data[k]
        _save_file_cache(path, file_data)


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
