# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Dispatch idempotency cache — RONDO-147.

Rondo-REQ-100 req 074 (extension): client-side dedupe to prevent
duplicate billable API calls on retry.

Finding #214: Retries (intentional via rondo_retry or accidental)
caused duplicate LLM API calls = duplicate cost + duplicate audit records.
No client-side dedupe meant the same prompt+model could be billed twice.

This module provides:
    compute_idempotency_key(prompt, model) — SHA-256 of prompt+model
    get_cached_result(key) — return cached TaskResult if within TTL
    cache_result(key, result) — store TaskResult for future dedupe

Default TTL: 5 minutes. Cache keyed by (prompt_hash, model).
Thread-safe via lock. In-process only — survives function calls within
the same Rondo process but not across restarts.
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# -- Default TTL: 5 minutes
DEFAULT_TTL_SEC = 300

# -- Module-level cache + lock
_cache: dict[str, tuple[Any, float]] = {}
_cache_lock = threading.Lock()


def compute_idempotency_key(prompt: str, model: str) -> str:
    """Generate stable idempotency key from prompt + model.

    Returns SHA-256 hex digest. Same prompt + same model = same key.
    """
    normalized = f"{model}\n{prompt}"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def get_cached_result(key: str, ttl_sec: int = DEFAULT_TTL_SEC) -> Any | None:
    """Return cached result if present AND within TTL. Else None.

    Thread-safe.
    """
    with _cache_lock:
        if key not in _cache:
            return None
        cached_value, cached_at = _cache[key]
        if time.monotonic() - cached_at > ttl_sec:
            # -- Expired — evict
            del _cache[key]
            return None
        return cached_value


def cache_result(key: str, result: Any) -> None:
    """Store result for future idempotency lookups.

    Thread-safe.
    """
    with _cache_lock:
        _cache[key] = (result, time.monotonic())


def clear_cache() -> None:
    """Clear the entire idempotency cache. For testing/admin."""
    with _cache_lock:
        _cache.clear()


def cache_size() -> int:
    """Return current cache size (number of entries)."""
    with _cache_lock:
        return len(_cache)


@dataclass
class IdempotencyConfig:
    """Idempotency cache configuration."""

    enabled: bool = True
    ttl_sec: int = DEFAULT_TTL_SEC


# -- sig: mgh-6201.cd.bd955f.f1c0.f0c061
