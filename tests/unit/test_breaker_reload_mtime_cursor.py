# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Regression: breaker live-reload misses a peer trip on an mtime collision — RONDO-361 #7.

VER-001 verification matrix: cross-process breaker live-reload visibility.

THE BUG (found in the RONDO-361 self-review, finding #7):
    CircuitBreaker._maybe_reload() gates the disk re-read on an mtime EQUALITY
    check:
        current = self._persist_path.stat().st_mtime
        if current != self._persist_mtime:
            self._load_state()
    On a filesystem with coarse mtime granularity (1s) or with NFS attribute
    caching, a PEER process can persist a fresh breaker trip within the SAME
    mtime tick that this instance last recorded. Then current == _persist_mtime,
    the reload is SKIPPED, and the peer's trip stays invisible to this live
    instance — defeating RONDO-361 #5 (a live instance must see a peer's trip).
    is_open() keeps returning False for a provider the peer already tripped OPEN.

These tests model two processes as two CircuitBreaker instances sharing ONE
persist_path. The headline test forces the persisted file's mtime to EQUAL what
this instance last recorded (os.utime to a fixed mtime), simulating the coarse/
NFS collision, and asserts the live instance STILL sees the peer trip. It MUST
FAIL against the current (equality-gated) code. The second test pins that a
normal mtime-advancing peer trip is still seen, so the fix can't regress the
ordinary path.

The test asserts the OBSERVABLE outcome (the live instance reports the provider
OPEN) — robust to whichever change signal a correct fix picks (size+mtime, a
content hash, etc.), since a real trip also changes the file SIZE even when the
mtime collides.
"""

from __future__ import annotations

import os
from pathlib import Path

from rondo.retry import CircuitBreaker

# -- A fixed mtime we pin onto the shared state file to simulate a coarse-
# -- granularity / NFS-cached clock where a peer's write lands in the SAME tick.
_FROZEN_MTIME = 1_000_000.0


def test_peer_trip_seen_when_mtime_does_not_advance(tmp_path: Path) -> None:
    """A live instance must see a peer trip even when the file mtime collides.

    Two instances share one persist_path (two processes). Instance B observes a
    provider while healthy, recording the file's (frozen) mtime. Instance A then
    trips that provider OPEN and persists it; we force the file's mtime back to
    the exact value B recorded — simulating coarse/NFS mtime granularity where
    the peer's write lands in the same tick. B.is_open(provider) must STILL be
    True. FAILS on the current code, whose mtime-equality gate skips the reload.
    """
    persist_path = tmp_path / "circuit_breaker.json"
    provider = "openai"
    threshold = 2
    cooldown = 300.0

    # -- Pre-create the shared file with a known, frozen mtime so that BOTH
    # -- instances record _persist_mtime == _FROZEN_MTIME at construction. (If
    # -- the file were absent, B would record 0.0 and any later real mtime would
    # -- differ — the collision we are testing could not be reproduced.)
    persist_path.write_text("{}", encoding="utf-8")
    os.utime(persist_path, (_FROZEN_MTIME, _FROZEN_MTIME))

    breaker_b = CircuitBreaker(failure_threshold=threshold, cooldown_sec=cooldown, persist_path=persist_path)
    breaker_a = CircuitBreaker(failure_threshold=threshold, cooldown_sec=cooldown, persist_path=persist_path)

    # -- B observes the provider while healthy: confirms CLOSED and locks in
    # -- B._persist_mtime == _FROZEN_MTIME (the stat equals what it last recorded).
    assert breaker_b.is_open(provider) is False

    # -- Peer process A trips the provider OPEN and persists it to the shared file.
    for _ in range(threshold):
        breaker_a.record_failure(provider)

    # -- Simulate the coarse/NFS collision: force the file's mtime back to the
    # -- exact value B already recorded, even though the CONTENT now carries the
    # -- peer's OPEN entry. The reload gate sees no mtime change.
    os.utime(persist_path, (_FROZEN_MTIME, _FROZEN_MTIME))

    assert breaker_b.is_open(provider) is True, (
        f"RONDO-361 #7 live-reload miss: the peer tripped '{provider}' OPEN but the "
        "live instance still reports it CLOSED because the file's mtime did not "
        "advance (coarse-granularity / NFS collision) and _maybe_reload's "
        "equality gate skipped the re-read — the peer's trip is invisible"
    )


def test_peer_trip_seen_when_mtime_advances(tmp_path: Path) -> None:
    """A normal mtime-advancing peer trip is still seen — no regression.

    Same two-process setup, but after A trips the provider we let the file's
    mtime move forward. The live instance B must reload and report the provider
    OPEN. This pins the ordinary live-reload path so a fix for the collision case
    cannot break it.
    """
    persist_path = tmp_path / "circuit_breaker.json"
    provider = "gemini"
    threshold = 2
    cooldown = 300.0

    persist_path.write_text("{}", encoding="utf-8")
    os.utime(persist_path, (_FROZEN_MTIME, _FROZEN_MTIME))

    breaker_b = CircuitBreaker(failure_threshold=threshold, cooldown_sec=cooldown, persist_path=persist_path)
    breaker_a = CircuitBreaker(failure_threshold=threshold, cooldown_sec=cooldown, persist_path=persist_path)

    assert breaker_b.is_open(provider) is False

    for _ in range(threshold):
        breaker_a.record_failure(provider)

    # -- Let the mtime advance well past what B recorded (deterministic — avoids
    # -- depending on real wall-clock granularity of the test filesystem).
    os.utime(persist_path, (_FROZEN_MTIME + 10.0, _FROZEN_MTIME + 10.0))

    assert breaker_b.is_open(provider) is True, (
        f"live-reload regression: peer tripped '{provider}' OPEN and the file mtime "
        "advanced, but the live instance still reports it CLOSED"
    )


# -- sig: mgh-6201.cd.bd955f.5821.22c1e1
