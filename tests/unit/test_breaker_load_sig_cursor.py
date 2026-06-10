# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Regression: breaker load-path records its change-signature AFTER reading — holistic #7.

VER-001 verification matrix: cross-process breaker live-reload visibility.

THE BUG (cursor holistic-review finding #7 / quality-checklist item 7):
    CircuitBreaker._load_state() captures its (mtime, size) change-signature with
    a FRESH stat() taken AFTER the file was read::

        raw = self._persist_path.read_text(...)
        self._record_mtime()        # <-- a fresh stat(), NOT of the bytes in `raw`
        data = json.loads(raw)

    A peer process that writes BETWEEN read_text() and that stat() makes
    _persist_sig describe bytes this instance NEVER parsed. _maybe_reload then
    compares against that post-write signature, sees "no change", and SKIPS the
    reload — so the peer's trip stays invisible to this live instance. This is the
    exact live-visibility miss the (mtime, size) signature was added to prevent
    (RONDO-361 #5 / RONDO-368 #7), reintroduced on the LOAD path.

These tests model two processes as two CircuitBreaker instances sharing ONE
persist_path. The headline test drives instance B through _load_state and injects
peer A's trip INSIDE the read window — after B's read_text() returns the pre-trip
bytes but BEFORE B's stat() — using a patched Path.read_text side-effect as the
deterministic interleave point (no sleeps-as-synchronization). It asserts the
OBSERVABLE contract: a peer trip written WHILE B is mid-_load_state is still
visible to B.is_open() afterwards. It MUST FAIL on current code, whose recorded
signature describes the post-write file and masks the change on the next reload.

The intended fix captures the signature so a mid-window peer write can never be
masked (stat BEFORE read → a stale recorded sig forces one extra converging
reload, or a signature derived from the bytes actually read). The assertion keys
only on the observable outcome, so it holds for whichever fix is chosen.

Pure pytest + unittest.mock; no source under src/ is touched.
"""

from __future__ import annotations

from pathlib import Path
from unittest import mock

from rondo.retry import CircuitBreaker

# -- Pre-trip file content whose SIZE differs from the bare "{}" recorded at
# -- construction, so B's _maybe_reload detects a change and enters _load_state.
# -- It still parses to an empty mapping (no entry for the provider), so the
# -- racy load merges nothing — the ONLY way B can later see the trip is by
# -- reloading the peer's bytes.
_PRE_TRIP_CONTENT = "{}\n\n"


def test_peer_trip_written_during_load_state_is_not_masked(tmp_path: Path) -> None:
    """A peer trip landing mid-_load_state stays visible to is_open() afterwards.

    Two instances share one persist_path (two processes). B is driven into
    _load_state; a patched Path.read_text returns the pre-trip bytes and THEN, in
    the same call (the in-window interleave point), peer A trips the provider OPEN
    and persists it. On buggy code B's fresh post-read stat() records the peer's
    file as "already seen", so the next _maybe_reload finds no change and B keeps
    reporting the provider CLOSED — the trip is masked. The fix records a
    signature that cannot describe unparsed bytes, so B reloads and sees the trip.
    MUST FAIL on current code.
    """
    persist_path = tmp_path / "circuit_breaker.json"
    provider = "openai"
    threshold = 2
    cooldown = 300.0

    # -- Shared file starts empty; both instances record the "{}" signature.
    persist_path.write_text("{}", encoding="utf-8")
    breaker_b = CircuitBreaker(failure_threshold=threshold, cooldown_sec=cooldown, persist_path=persist_path)
    breaker_a = CircuitBreaker(failure_threshold=threshold, cooldown_sec=cooldown, persist_path=persist_path)

    # -- B observes the provider while healthy: confirms CLOSED and pins B's
    # -- recorded signature to the empty-file state.
    assert breaker_b.is_open(provider) is False

    # -- Stage pre-trip bytes whose size differs from "{}" so B's NEXT is_open
    # -- detects a change and descends into _load_state. They parse to {} — no
    # -- provider entry — so the racy load merges nothing on its own.
    persist_path.write_text(_PRE_TRIP_CONTENT, encoding="utf-8")

    orig_read_text = Path.read_text
    fired = {"done": False}

    def _peer_trips_during_read() -> None:
        # -- Peer process A trips the provider OPEN and persists it to the shared
        # -- file. This is the write that lands INSIDE B's read window.
        for _ in range(threshold):
            breaker_a.record_failure(provider)

    def patched_read_text(self: Path, *args: object, **kwargs: object) -> str:
        # -- Return the bytes actually on disk FIRST (the pre-trip content B is
        # -- parsing), then inject the peer write before handing them back — i.e.
        # -- after read_text() returns but before _load_state's stat(). The
        # -- one-shot `fired` guard keeps A's own internal reads (during its
        # -- persist) on the original path and prevents re-entry.
        content = orig_read_text(self, *args, **kwargs)
        if not fired["done"] and self == persist_path:
            fired["done"] = True
            _peer_trips_during_read()
        return content

    with mock.patch.object(Path, "read_text", patched_read_text):
        # -- The racy load: B reads pre-trip bytes, A's trip lands mid-window.
        breaker_b.is_open(provider)
        # -- The peer trip must NOT be masked: on the next call B still has to
        # -- report the provider OPEN.
        masked_result = breaker_b.is_open(provider)

    assert masked_result is True, (
        f"holistic #7 load-path sig miss: peer tripped '{provider}' OPEN while B was "
        "mid-_load_state, but B recorded its change-signature from a FRESH stat() "
        "taken AFTER the read — describing bytes it never parsed. _maybe_reload "
        "then sees 'no change' and skips the reload, so the peer's trip is masked "
        "and B keeps reporting it CLOSED"
    )


def test_normal_trip_after_clean_load_state_is_seen(tmp_path: Path) -> None:
    """Rail: a peer trip written after a clean _load_state is still seen.

    Same two-process setup with no in-window injection. After A trips the
    provider and persists it normally, the live instance B must reload and report
    the provider OPEN. This pins the ordinary live-reload path so a fix for the
    in-window race cannot regress it.
    """
    persist_path = tmp_path / "circuit_breaker.json"
    provider = "gemini"
    threshold = 2
    cooldown = 300.0

    persist_path.write_text("{}", encoding="utf-8")
    breaker_b = CircuitBreaker(failure_threshold=threshold, cooldown_sec=cooldown, persist_path=persist_path)
    breaker_a = CircuitBreaker(failure_threshold=threshold, cooldown_sec=cooldown, persist_path=persist_path)

    # -- Clean load: B sees the provider CLOSED with no concurrent writer.
    assert breaker_b.is_open(provider) is False

    # -- Peer A trips the provider OPEN and persists it (a real entry grows the
    # -- file, so B's (mtime, size) signature changes and the reload fires).
    for _ in range(threshold):
        breaker_a.record_failure(provider)

    assert breaker_b.is_open(provider) is True, (
        f"live-reload regression: peer tripped '{provider}' OPEN after a clean load "
        "and the file changed, but the live instance still reports it CLOSED"
    )


# -- sig: mgh-6201.cd.bd955f.800d.cf4026
