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
import tempfile
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field, is_dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# -- Default TTL: 5 minutes
DEFAULT_TTL_SEC = 300

# -- Module-level cache + lock (in-memory fast path)
_cache: dict[str, tuple[Any, float]] = {}
_cache_lock = threading.Lock()

# -- RONDO-400 (R2-1): the in-memory layer is BOUNDED. One tuple holds a full
# -- result payload per unique key; with eviction only on same-key re-lookup,
# -- the long-lived MCP server grew forever (the in-memory twin of the
# -- RONDO-369/396 disk/lock leaks). Oldest-out by cached_at; eviction is
# -- never a correctness loss for dict/dataclass results — the JSONL layer
# -- re-promotes on lookup. KNOWN NUANCE: non-serializable results are
# -- memory-ONLY (by design), so for those eviction before TTL forfeits the
# -- dedupe — worst case the old rare double-pay, never wrong data.
_MAX_MEMORY_ENTRIES = 512


def _prune_memory_locked(protect: str | None = None) -> None:
    """Sweep TTL-expired entries, then oldest-out to the bound. Caller holds _cache_lock.

    O(n log n) worst case with n <= ~bound — trivial at 512. Runs on every
    insert/promote so expired-but-never-re-read entries cannot linger.
    `protect` is the just-inserted/promoted key: it is never the bound-eviction
    victim (a promote carries its ORIGINAL cached_at — oldest in the dict — and
    would otherwise be evicted by its own promotion). TTL still applies to it.
    """
    now = time.time()
    for key in [k for k, (_v, at) in _cache.items() if now - at > DEFAULT_TTL_SEC]:
        del _cache[key]
    overflow = len(_cache) - _MAX_MEMORY_ENTRIES
    if overflow > 0:
        oldest_first = sorted(_cache.items(), key=lambda kv: kv[1][1])
        victims = [key for key, _ in oldest_first if key != protect][:overflow]
        for key in victims:
            del _cache[key]


# -- #241: file I/O lock prevents torn reads during atomic write+rename race
_file_lock = threading.Lock()

# -- RONDO-360: single-flight per-key locks. lookup and store were each locked
# -- but the lookup→dispatch→store SEQUENCE was not — two identical concurrent
# -- dispatches both missed and both PAID. A per-key lock serializes same-key
# -- callers so only the first dispatches; the rest re-check and reuse it.
# -- RONDO-369 #9: ref-count each entry and evict it when the last user leaves,
# -- so the map only ever holds locks for keys with active in-flight callers —
# -- bounded by concurrency, not by the count of distinct keys ever seen (the
# -- long-lived MCP server saw a new SHA-256 key per unique prompt → unbounded
# -- growth). Eviction at zero users (under the guard) can never pull a lock out
# -- from under a waiting caller.


@dataclass
class _RefCountedLock:
    """A key's lock plus how many callers are currently using it — RONDO-369 #9."""

    lock: threading.Lock = field(default_factory=threading.Lock)
    users: int = 0


_key_locks: dict[str, _RefCountedLock] = {}
_key_locks_guard = threading.Lock()


@contextmanager
def key_lock(key: str) -> Iterator[None]:
    """Single-flight lock for one idempotency key — RONDO-360 + RONDO-369 #9.

    Serializes same-key callers in-process so identical concurrent dispatches
    don't both pay; different keys never block each other. In-process layer
    only — the cross-PROCESS layer is cross_process_key_lock (RONDO-390),
    stacked by _dispatch_and_cache. The entry is ref-counted and removed once
    no caller holds it, so the map stays bounded in the long-lived MCP server.
    """
    with _key_locks_guard:
        entry = _key_locks.get(key)
        if entry is None:
            entry = _RefCountedLock()
            _key_locks[key] = entry
        entry.users += 1
    try:
        with entry.lock:
            yield
    finally:
        with _key_locks_guard:
            entry.users -= 1
            if entry.users <= 0:
                _key_locks.pop(key, None)


def _key_lock_file(key: str) -> Path:
    """Per-key cross-process lock file under the cache dir — RONDO-390."""
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]
    return _default_cache_file().parent / "idempotency-locks" / f"{digest}.lock"


# -- RONDO-396 (8.5): bounded cross-process acquire. The RONDO-390 blocking
# -- LOCK_EX could stall an interactive caller for a peer's 30-min dispatch.
_XPROC_WAIT_ENV = "RONDO_XPROC_LOCK_WAIT_SEC"
_XPROC_WAIT_DEFAULT_SEC = 3.0
_XPROC_RETRY_INTERVAL_SEC = 0.05


def _xproc_wait_budget() -> float:
    """Wait budget for the cross-process lock — env knob, garbage-safe.

    RONDO_XPROC_LOCK_WAIT_SEC: 0 = no wait (immediate unlocked fallthrough
    under contention); unset/negative/garbage → the 3s default.
    """
    raw = os.environ.get(_XPROC_WAIT_ENV, "").strip()
    if not raw:
        return _XPROC_WAIT_DEFAULT_SEC
    try:
        val = float(raw)
    except ValueError:
        return _XPROC_WAIT_DEFAULT_SEC
    return val if val >= 0 else _XPROC_WAIT_DEFAULT_SEC


def _try_flock_bounded(lock_f: Any, budget_sec: float) -> bool:
    """LOCK_NB retry loop up to budget_sec. True = lock held.

    RONDO-396 (8.5): never stalls past the budget — on timeout the caller
    proceeds WITHOUT the cross-process lock (in-process single-flight still
    holds; worst case = the old rare cross-process double-pay, never a
    stalled MCP server). Non-contention errnos (NFS etc.) warn + proceed.
    """
    import errno  # pylint: disable=import-outside-toplevel
    import fcntl  # pylint: disable=import-outside-toplevel

    deadline = time.monotonic() + budget_sec
    while True:
        try:
            fcntl.flock(lock_f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError as exc:
            if exc.errno not in (errno.EWOULDBLOCK, errno.EAGAIN):
                logger.warning("Cross-process key lock flock failed (%s) — proceeding without it", exc)
                return False
            if time.monotonic() >= deadline:
                logger.warning(
                    "-WARNING- cross-process key lock still held by a peer after the %.1fs bounded wait — "
                    "proceeding WITHOUT it (in-process single-flight holds; worst case = rare double-pay)",
                    budget_sec,
                )
                return False
            time.sleep(_XPROC_RETRY_INTERVAL_SEC)


@contextmanager
def cross_process_key_lock(key: str) -> Iterator[None]:
    """Cross-process single-flight for one idempotency key — RONDO-390 + RONDO-396.

    Exclusive flock on a per-key lock file: two PROCESSES dispatching the same
    prompt serialize — only the first pays; the second re-checks the shared
    JSONL cache and reuses the result. BOUNDED acquire (RONDO-396, 8.5): a
    LOCK_NB retry loop up to RONDO_XPROC_LOCK_WAIT_SEC (default 3s; 0 = no
    wait) — on timeout, WARN and proceed unlocked rather than stall an
    interactive caller behind a peer's 30-minute dispatch. flock releases
    automatically on process death (kernel-managed). Live lock files are never
    unlinked (see sweep_stale_key_locks for the TTL hygiene path).
    Degradation (r019 family): no fcntl (Windows) or an unsupported FS — WARN
    and proceed with in-process single-flight only, never crash.
    """
    try:
        import fcntl  # pylint: disable=import-outside-toplevel
    except ImportError:
        logger.warning("Cross-process key lock unavailable (no fcntl, e.g. Windows) — in-process single-flight only")
        yield
        return
    lock_path = _key_lock_file(key)
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        lock_f = open(lock_path, "a+", encoding="utf-8")  # noqa: SIM115 -- held across yield
    except OSError as exc:
        logger.warning("Cross-process key lock open failed (%s) — in-process single-flight only", exc)
        yield
        return
    acquired = False
    try:
        acquired = _try_flock_bounded(lock_f, _xproc_wait_budget())
        yield
    finally:
        if acquired:
            try:
                fcntl.flock(lock_f.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
        lock_f.close()


def sweep_stale_key_locks(ttl_sec: float = 7 * 86400.0) -> int:
    """TTL hygiene for idempotency-locks/ — RONDO-396 (8.5). Returns count removed.

    Unlinks a lock file ONLY when (a) its mtime is older than ttl_sec AND
    (b) a LOCK_EX|LOCK_NB probe SUCCEEDS — provably unheld at that instant.
    A held file survives regardless of age (unlinking a held lock re-locks a
    dead inode for the holder's peers). Honesty note: a peer that has OPENED
    the file but not yet flocked when we unlink can still land on the dead
    inode — that window degrades to the old rare double-pay, never corruption.
    Runs opportunistically from compaction; callable directly.
    """
    try:
        import fcntl  # pylint: disable=import-outside-toplevel
    except ImportError:
        return 0
    locks_dir = _default_cache_file().parent / "idempotency-locks"
    if not locks_dir.is_dir():
        return 0
    removed = 0
    now = time.time()
    for path in locks_dir.glob("*.lock"):
        try:
            if now - path.stat().st_mtime <= ttl_sec:
                continue
            with open(path, "a+", encoding="utf-8") as probe_f:
                try:
                    fcntl.flock(probe_f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError:
                    continue  # -- held by a live peer (or unsupported FS) → never unlink
                try:
                    path.unlink()
                    removed += 1
                finally:
                    fcntl.flock(probe_f.fileno(), fcntl.LOCK_UN)
        except OSError:
            continue  # -- raced away / unreadable → leave it for the next sweep
    if removed:
        logger.debug("Swept %d stale idempotency lock file(s)", removed)
    return removed


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
    """Append a single cache entry as one JSONL line, under flock — #246 + RONDO-389.

    RONDO-389 (Mark's ruling, checklist 21): the old comment claimed PIPE_BUF
    atomicity — FALSE for entries beyond ~4-8KB (real task results routinely
    are). Large concurrent appends could interleave and tear lines. Now an
    exclusive flock guards write+flush (the proven audit._append_jsonl
    pattern); where flock is unavailable (Windows / odd FS) we degrade to a
    best-effort write WITH a warning — the read side's torn-line tolerance
    remains the final backstop.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        entry = {
            "key": key,
            "data": payload,
            "cached_at_wall": cached_at_wall,
        }
        line = json.dumps(entry, default=str) + "\n"
        # -- RONDO-393 (8.3 twin): cached entries carry result payloads —
        # -- born 0o600 on first append (STD-110 r012)
        append_fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        with os.fdopen(append_fd, "a", encoding="utf-8") as f:
            try:
                import fcntl  # pylint: disable=import-outside-toplevel

                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                f.write(line)
                f.flush()
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            except (ImportError, OSError) as lock_exc:
                # -- Windows or lock failure: best-effort write, loudly.
                logger.warning("Idempotency append without lock (best-effort): %s", lock_exc)
                f.write(line)
    except (OSError, TypeError, ValueError) as exc:
        logger.debug("Idempotency JSONL append failed (non-fatal): %s", exc)


def _rewrite_compacted(path: Path, fresh: dict[str, tuple[Any, float]]) -> None:
    """Rewrite the cache JSONL with only live entries — atomic, born 0o600.

    RONDO-393 (8.3 twin): cached entries carry result payloads; the compaction
    tmp is created via mkstemp so no instant exposes wider perms (STD-110 r012).
    Extracted from the two (locked/unlocked) compaction branches.
    """
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for k, (value, cached_at) in fresh.items():
                f.write(json.dumps({"key": k, "data": value, "cached_at_wall": cached_at}, default=str) + "\n")
        os.replace(tmp_name, path)
    except OSError:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


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
                _rewrite_compacted(path, fresh)
                logger.debug("Idempotency JSONL compacted: %d live entries", len(fresh))
                # -- RONDO-396 (8.5): opportunistic lock-file TTL hygiene rides
                # -- the compaction cadence (flock-probe safe, see the sweep).
                sweep_stale_key_locks()

                fcntl.flock(lock_f.fileno(), fcntl.LOCK_UN)
        except ImportError:
            # -- Windows: no fcntl, fall back to unlocked compaction (benign)
            fresh = _scan_cache_file(path, ttl_sec=DEFAULT_TTL_SEC)
            _rewrite_compacted(path, fresh)
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
        _prune_memory_locked(protect=key)  # -- RONDO-400: bound holds on the promote path too
    return value


def cache_result(key: str, result: Any) -> None:
    """Store result for future idempotency lookups.

    RONDO-209 #246: append-only JSONL write — NO read-modify-write race.
    Writes to BOTH in-memory (fast path) AND JSONL file (cross-process).
    """
    now = time.time()
    with _cache_lock:
        _cache[key] = (result, now)
        _prune_memory_locked(protect=key)  # -- RONDO-400: expired sweep + oldest-out bound

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


# -- sig: mgh-6201.cd.bd955f.f5da.126f00
