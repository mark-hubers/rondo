# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Regression: circuit-breaker fail-OPEN cross-process lost update — RONDO-361 #1.

VER-001 verification matrix: cross-process breaker persistence safety.

THE BUG (found in the RONDO-361 self-review, finding #1):
    CircuitBreaker._apply_memory_states has an
        `elif provider in payload: del payload[provider]`
    branch. When THIS process holds a stale-CLOSED in-memory state for a
    provider (open_until == 0) but a PEER process has already persisted that
    provider as OPEN to the shared state file, a `_save_state` triggered for an
    UNRELATED provider re-reads the peer's still-valid OPEN entry into the merge
    payload and then DELETES it — silently clearing a down provider's breaker
    for every other process. That is a fail-OPEN: traffic flows to a provider
    the fleet already knows is tripped.

These tests use two CircuitBreaker instances sharing ONE persist_path to model
two processes, reproduce the exact scenario, and assert against the ON-DISK
JSON. The first test MUST FAIL against the current (buggy) code; the second
pins that reset() still genuinely clears a provider so the eventual fix can't
be a no-op that simply drops the deletion branch.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from rondo.retry import CircuitBreaker


def _read_disk(persist_path: Path) -> dict[str, dict[str, float]]:
    """Read the persisted breaker JSON straight off disk (no class helpers)."""
    return json.loads(persist_path.read_text(encoding="utf-8"))


def test_peer_open_entry_survives_unrelated_save(tmp_path: Path) -> None:
    """A peer's OPEN entry must survive this process saving an UNRELATED trip.

    Reproduces RONDO-361 #1: proc_self carries a stale-CLOSED in-memory state
    for "openai" (it observed the provider while healthy), the peer process then
    trips "openai" OPEN to the shared file, and proc_self later trips an
    unrelated "gemini". The unrelated save must NOT erase the peer's valid OPEN
    "openai" entry from disk. FAILS against the buggy del-branch.
    """
    persist_path = tmp_path / "circuit_breaker.json"
    threshold = 2
    cooldown = 300.0

    # -- Two instances over one file == two processes sharing breaker state.
    proc_self = CircuitBreaker(failure_threshold=threshold, cooldown_sec=cooldown, persist_path=persist_path)
    proc_peer = CircuitBreaker(failure_threshold=threshold, cooldown_sec=cooldown, persist_path=persist_path)

    # -- proc_self observes "openai" while CLOSED → stale in-memory CLOSED state
    # -- (open_until == 0) that is never reloaded during a later _save_state.
    assert proc_self.is_open("openai") is False

    # -- Peer process trips "openai" OPEN and persists it to the shared file.
    for _ in range(threshold):
        proc_peer.record_failure("openai")

    on_disk = _read_disk(persist_path)
    assert "openai" in on_disk, "setup: peer should have persisted openai OPEN"
    assert on_disk["openai"]["open_until"] > time.time(), "setup: openai cooldown should be live"

    # -- proc_self trips an UNRELATED provider → triggers its read-merge-write.
    for _ in range(threshold):
        proc_self.record_failure("gemini")

    on_disk = _read_disk(persist_path)
    assert "gemini" in on_disk, "our own unrelated trip should persist"
    assert "openai" in on_disk, (
        "RONDO-361 #1 fail-OPEN: peer's still-valid OPEN 'openai' entry was "
        "DELETED from disk by an unrelated save while our in-memory state for "
        "it was stale-CLOSED — every other process now sees the down provider "
        "as healthy"
    )
    assert on_disk["openai"]["open_until"] > time.time(), (
        "peer's openai cooldown must remain in the future after the unrelated save"
    )


def test_reset_clears_provider(tmp_path: Path) -> None:
    """reset() must genuinely clear a provider — the fix can't no-op it.

    Trips "openai" OPEN (persisted), confirms it reads OPEN, then resets it and
    asserts the breaker no longer reports it open. Guards against an eventual
    fix that merely removes the deletion branch and accidentally makes reset()
    unable to clear a tripped provider.
    """
    persist_path = tmp_path / "circuit_breaker.json"
    threshold = 2
    breaker = CircuitBreaker(failure_threshold=threshold, cooldown_sec=300.0, persist_path=persist_path)

    for _ in range(threshold):
        breaker.record_failure("openai")

    assert breaker.is_open("openai") is True, "setup: openai should be OPEN after threshold failures"
    assert "openai" in _read_disk(persist_path), "setup: OPEN state should be persisted"

    breaker.reset("openai")

    assert breaker.is_open("openai") is False, "reset('openai') must clear the provider — it is still reported OPEN"


# -- sig: mgh-6201.cd.bd955f.2c5f.c292a5
