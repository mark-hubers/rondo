# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Regression tests for ROAD-TO-8 item 8.5 (R5): bounded cross-process key lock + lock-file TTL hygiene.

VER-001 verification matrix: cross-process key-lock liveness + lock-dir hygiene contract.

``src/rondo/idempotency.py`` ``cross_process_key_lock`` today takes an UNBOUNDED
``fcntl.flock(fd, LOCK_EX)``: if process A holds a key's lock through a 30-minute
dispatch, process B's MCP-server thread stalls the whole wait — an interactive
caller freezes with no feedback. And lock files under ``idempotency-locks/`` are
never cleaned (one per unique key, forever).

The NEW contract these tests pin (observables, not the mechanism):
  (a) BOUNDED ACQUIRE — ``LOCK_EX|LOCK_NB`` retried with small sleeps up to a wait
      budget (default ~3s, ``RONDO_XPROC_LOCK_WAIT_SEC``; 0 disables waiting =
      immediate fallthrough; negative/garbage → default). On success: proceed
      locked, exactly as today.
  (b) TIMEOUT → PROCEED UNLOCKED + WARN — on exhausting the budget, log a WARNING
      (mentions the bounded wait; in-process single-flight still holds; worst
      case = the rare cross-process double-pay) and yield WITHOUT the lock. Never
      stall past the budget, never raise.
  (c) Degradation rails unchanged (no fcntl / open failure → warn + yield) —
      pinned elsewhere, not re-tested here.
  (d) TTL SWEEP with flock-probe safety — during idempotency compaction, stale
      lock FILES older than a TTL (mtime) in ``idempotency-locks/`` are unlinked
      ONLY after a successful ``LOCK_EX|LOCK_NB`` probe (provably unheld); held
      or young files are left alone.
  (e) Holding path unchanged — when acquired within budget, release/close
      semantics are identical to today.

Real peers are spawned with ``sys.executable -c`` (hermetic, no live AI). Tests 1,
3 (contention sub-case) and 4 MUST FAIL on today's blocking, sweep-less code.
"""

from __future__ import annotations

import json
import logging
import os
import select
import subprocess
import sys
import time
from pathlib import Path

# -- src/ on the child interpreter's path (mirrors test_cross_process_singleflight_cursor)
_SRC_PATH = Path(__file__).parent.parent.parent / "src"

# -- Child: hold an EXCLUSIVE flock on the lock FILE for key argv[1] for argv[2]
# -- seconds, signalling LOCKED once held. Uses the production path helper so the
# -- lock file matches exactly what the parent's cross_process_key_lock targets.
_HOLD_BY_KEY = (
    "import sys, fcntl, time\n"
    "sys.path.insert(0, " + repr(str(_SRC_PATH)) + ")\n"
    "import rondo.idempotency as idem\n"
    "p = idem._key_lock_file(sys.argv[1])\n"
    "p.parent.mkdir(parents=True, exist_ok=True)\n"
    "f = open(p, 'a+', encoding='utf-8')\n"
    "fcntl.flock(f.fileno(), fcntl.LOCK_EX)\n"
    "print('LOCKED', flush=True)\n"
    "time.sleep(float(sys.argv[2]))\n"
)

# -- Child: non-blocking probe of key argv[1]'s lock file — ACQUIRED if free,
# -- BLOCKED if a peer (e.g. the parent's context) holds it.
_PROBE_BY_KEY = (
    "import sys, fcntl\n"
    "sys.path.insert(0, " + repr(str(_SRC_PATH)) + ")\n"
    "import rondo.idempotency as idem\n"
    "p = idem._key_lock_file(sys.argv[1])\n"
    "p.parent.mkdir(parents=True, exist_ok=True)\n"
    "f = open(p, 'a+', encoding='utf-8')\n"
    "try:\n"
    "    fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)\n"
    "    print('ACQUIRED', flush=True)\n"
    "    fcntl.flock(f.fileno(), fcntl.LOCK_UN)\n"
    "except OSError:\n"
    "    print('BLOCKED', flush=True)\n"
)

# -- Child: hold an EXCLUSIVE flock on an EXPLICIT path (argv[1]) for argv[2]
# -- seconds — used to make a stale lock FILE provably held during the sweep.
_HOLD_BY_PATH = (
    "import sys, fcntl, time\n"
    "f = open(sys.argv[1], 'a+', encoding='utf-8')\n"
    "fcntl.flock(f.fileno(), fcntl.LOCK_EX)\n"
    "print('LOCKED', flush=True)\n"
    "time.sleep(float(sys.argv[2]))\n"
)


def _await_token(proc: subprocess.Popen, token: str, timeout: float) -> bool:
    """Block until ``token`` appears on the child's stdout, EOF, or timeout."""
    end = time.time() + timeout
    while time.time() < end:
        remaining = end - time.time()
        ready, _, _ = select.select([proc.stdout], [], [], max(0.0, remaining))
        if not ready:
            continue
        line = proc.stdout.readline()
        if line == "":
            return False
        if token in line:
            return True
    return False


def _spawn_holder_by_key(key: str, hold_sec: float, env: dict[str, str]) -> subprocess.Popen:
    """Spawn a peer process holding key's lock; return once it signals LOCKED."""
    proc = subprocess.Popen(
        [sys.executable, "-c", _HOLD_BY_KEY, key, str(hold_sec)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert _await_token(proc, "LOCKED", timeout=8.0), "peer never acquired the key lock"
    return proc


def _kill(proc: subprocess.Popen) -> None:
    """Terminate a peer process and reap it (no leaked children)."""
    try:
        proc.terminate()
        proc.wait(timeout=5.0)
    except Exception:  # noqa: BLE001 -- best-effort cleanup
        proc.kill()


def _warnings(caplog) -> list[str]:
    """Cross-process-lock WARNING messages captured from the module logger."""
    return [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING and r.name == "rondo.idempotency"]


def test_bounded_wait_yields_within_budget_under_contention(tmp_path, monkeypatch, caplog) -> None:
    """Bounded acquire: a held peer lock must NOT stall us past the wait budget.

    A second REAL process holds key 'K' for 4s. With RONDO_XPROC_LOCK_WAIT_SEC=1
    we enter cross_process_key_lock under a wall-clock timer: the new contract
    yields (unlocked, WARNING) within ~1s+slack. Today's unbounded LOCK_EX blocks
    until the peer exits (~4s).

    MUST FAIL today: elapsed ~4s >= 2.5s threshold (no bounded wait, no warning).
    """
    monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))
    monkeypatch.setenv("RONDO_XPROC_LOCK_WAIT_SEC", "1")
    caplog.set_level(logging.WARNING, logger="rondo.idempotency")
    import rondo.idempotency as idem

    env = os.environ.copy()
    env["RONDO_TEST_DIR"] = str(tmp_path)
    peer = _spawn_holder_by_key("K", hold_sec=4.0, env=env)
    try:
        start = time.perf_counter()
        with idem.cross_process_key_lock("K"):
            elapsed = time.perf_counter() - start
    finally:
        _kill(peer)

    assert elapsed < 2.5, (
        f"8.5(a/b): cross_process_key_lock stalled {elapsed:.2f}s on a held peer lock — "
        "unbounded LOCK_EX, no bounded-wait budget"
    )
    warns = _warnings(caplog)
    assert any("wait" in m.lower() or "budget" in m.lower() for m in warns), (
        f"8.5(b): bounded-wait timeout must log a WARNING mentioning the wait — got {warns!r}"
    )


def test_fast_path_acquires_and_holds_no_warning(tmp_path, monkeypatch, caplog) -> None:
    """Acquired-fast path: no contention → prompt entry, lock truly held, NO warning.

    With the key uncontended we enter the context; while inside, a subprocess
    LOCK_NB probe of the same key's lock file must report BLOCKED (we hold it).
    No WARNING is emitted on the happy path.
    """
    monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))
    caplog.set_level(logging.WARNING, logger="rondo.idempotency")
    import rondo.idempotency as idem

    env = os.environ.copy()
    env["RONDO_TEST_DIR"] = str(tmp_path)

    start = time.perf_counter()
    with idem.cross_process_key_lock("K"):
        elapsed = time.perf_counter() - start
        probe = subprocess.run(
            [sys.executable, "-c", _PROBE_BY_KEY, "K"],
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
        )

    assert elapsed < 1.0, f"uncontended acquire should be prompt, took {elapsed:.2f}s"
    assert "BLOCKED" in probe.stdout, (
        f"8.5(a/e): lock must actually be HELD inside the context — probe got {probe.stdout!r}/{probe.stderr!r}"
    )
    assert _warnings(caplog) == [], f"happy path must not warn — got {_warnings(caplog)!r}"


def test_env_knob_zero_falls_through_and_garbage_uses_default(tmp_path, monkeypatch, caplog) -> None:
    """Env knob: WAIT_SEC=0 → immediate unlocked fallthrough under contention; garbage → default.

    Part 1 (contention): a peer holds key 'K'. With RONDO_XPROC_LOCK_WAIT_SEC=0 we
    must fall through WITHOUT the lock almost instantly (<0.5s) and WARN. Today's
    code ignores the knob and blocks on the peer → MUST FAIL today.
    Part 2 (garbage): RONDO_XPROC_LOCK_WAIT_SEC='banana' with no contention must
    not crash and must still yield (default budget applies; not timed).
    """
    monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))
    caplog.set_level(logging.WARNING, logger="rondo.idempotency")
    import rondo.idempotency as idem

    env = os.environ.copy()
    env["RONDO_TEST_DIR"] = str(tmp_path)

    # -- Part 1: WAIT_SEC=0 under contention → immediate unlocked fallthrough + WARN
    monkeypatch.setenv("RONDO_XPROC_LOCK_WAIT_SEC", "0")
    peer = _spawn_holder_by_key("K", hold_sec=2.0, env=env)
    try:
        start = time.perf_counter()
        with idem.cross_process_key_lock("K"):
            elapsed = time.perf_counter() - start
    finally:
        _kill(peer)

    assert elapsed < 0.5, (
        f"8.5(a): RONDO_XPROC_LOCK_WAIT_SEC=0 must fall through immediately under contention, took {elapsed:.2f}s"
    )
    assert _warnings(caplog), "8.5(b): zero-wait fallthrough must still WARN"

    # -- Part 2: garbage value → default budget, no contention, no crash, still yields
    monkeypatch.setenv("RONDO_XPROC_LOCK_WAIT_SEC", "banana")
    ran: list[bool] = []
    with idem.cross_process_key_lock("K2"):
        ran.append(True)
    assert ran == [True], "garbage RONDO_XPROC_LOCK_WAIT_SEC must fall back to default and still yield"


def _trigger_sweep(idem, ttl_sec: int) -> None:
    """Drive the lock-dir TTL sweep via its public hook, else the compaction path."""
    sweep = getattr(idem, "sweep_stale_key_locks", None)
    if callable(sweep):
        sweep(ttl_sec=ttl_sec)
        return
    # -- Fallback: force the >1MB JSONL compaction path, which is where the sweep lives.
    path = idem._default_cache_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps({"key": "x", "data": {"v": "y" * 80}, "cached_at_wall": time.time()}) + "\n"
    with open(path, "w", encoding="utf-8") as f:
        f.write(line * 15000)  # -- ~1.8 MB > _COMPACT_THRESHOLD_BYTES
    idem._compact_if_needed(path)


def test_ttl_sweep_unlinks_only_stale_and_unheld(tmp_path, monkeypatch) -> None:
    """TTL sweep: unlink ONLY lock files that are both stale (old mtime) AND unheld.

    Three files in idempotency-locks/: (i) old+unheld → swept; (ii) old+HELD by a
    live peer → survives (flock probe fails); (iii) fresh+unheld → survives (young).

    MUST FAIL today: no sweep exists, so the stale unheld file is never removed.
    """
    monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))
    import rondo.idempotency as idem

    locks_dir = idem._key_lock_file("seed").parent
    locks_dir.mkdir(parents=True, exist_ok=True)
    eight_days_ago = time.time() - 8 * 86400

    stale_unheld = locks_dir / "stale_unheld.lock"
    stale_held = locks_dir / "stale_held.lock"
    fresh_unheld = locks_dir / "fresh_unheld.lock"
    for p in (stale_unheld, stale_held, fresh_unheld):
        p.write_text("", encoding="utf-8")
    os.utime(stale_unheld, (eight_days_ago, eight_days_ago))
    os.utime(stale_held, (eight_days_ago, eight_days_ago))

    peer = subprocess.Popen(
        [sys.executable, "-c", _HOLD_BY_PATH, str(stale_held), "8"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert _await_token(peer, "LOCKED", timeout=8.0), "peer never held the stale lock file"
        _trigger_sweep(idem, ttl_sec=7 * 86400)
    finally:
        _kill(peer)

    assert not stale_unheld.exists(), "8.5(d): stale + unheld lock file must be swept"
    assert stale_held.exists(), "8.5(d): stale but HELD lock file must survive (never unlink a held lock)"
    assert fresh_unheld.exists(), "8.5(d): fresh unheld lock file must survive (younger than TTL)"


def test_release_on_exit_unchanged(tmp_path, monkeypatch) -> None:
    """Holding path unchanged: after the context exits, the lock is free again.

    Enter and exit cross_process_key_lock('K'); then a subprocess LOCK_NB probe of
    the same key's lock file must report ACQUIRED.
    """
    monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))
    import rondo.idempotency as idem

    env = os.environ.copy()
    env["RONDO_TEST_DIR"] = str(tmp_path)

    with idem.cross_process_key_lock("K"):
        pass

    probe = subprocess.run(
        [sys.executable, "-c", _PROBE_BY_KEY, "K"],
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert "ACQUIRED" in probe.stdout, (
        f"8.5(e): lock must be released on context exit — probe got {probe.stdout!r}/{probe.stderr!r}"
    )


# -- sig: mgh-6201.cd.bd955f.83eb.5503fa
