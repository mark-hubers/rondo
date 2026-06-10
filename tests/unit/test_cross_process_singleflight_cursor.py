# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Regression tests for quality-checklist item 22: CROSS-PROCESS single-flight.

VER-001 verification matrix: cross-process dispatch-dedup concurrency contract.

``src/rondo/idempotency.py`` (RONDO-360/369) + ``mcp_dispatch._dispatch_and_cache``
give SINGLE-PROCESS single-flight only — per-key ``threading.Lock`` serializes
same-key callers WITHIN one interpreter. Two separate PROCESSES (the long-lived
MCP server + a one-shot CLI run) dispatching the IDENTICAL prompt at the same
moment both miss the shared JSONL cache and BOTH PAY the billable call.

Mark's ruling: close it with a per-key CROSS-PROCESS file lock. The intended
contract (observables, not the mechanism):
  - a module-level context manager ``rondo.idempotency.cross_process_key_lock(key)``
    takes an EXCLUSIVE ``fcntl.flock`` on a per-key lock file under a ``locks``
    subdir next to ``idempotency.jsonl`` (file name derived from the key hash);
    it BLOCKS until the peer releases.
  - ``_dispatch_and_cache`` wraps lookup→dispatch→store in it so exactly ONE
    paid dispatch happens across two PROCESSES.
  - ``flock`` auto-releases on process death (kernel) — no stale-lockfile
    recovery; lock files persist (tiny) and are never unlinked while in use.
  - Windows / no-``fcntl``: degrade to in-process-only single-flight (the
    r019-family fallback rail) — the context manager still works.

These pin that contract. The headline cross-process test MUST FAIL today (the
context manager does not exist): the child prints a sentinel and the parent
asserts on it so the failure mode is a clean assertion, not a collection error.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from unittest import mock

# -- src/ on the child interpreter's path (mirrors test_integration_multiprocess)
_SRC_PATH = Path(__file__).parent.parent.parent / "src"

# -- Each child: take cross_process_key_lock("K") around a classic lost-update
# -- window (read counter → sleep → write counter+1). A REAL exclusive
# -- cross-process lock serializes the two children → final counter == 2;
# -- without it they interleave and one update is lost → final counter == 1.
# -- raising-tolerant getattr → if the CM is absent the child prints MISSING_CM
# -- and exits clean, so the parent fails on the sentinel (no traceback noise).
_CHILD_CODE = (
    "import sys, os, time\n"
    "sys.path.insert(0, " + repr(str(_SRC_PATH)) + ")\n"
    "from pathlib import Path\n"
    "import rondo.idempotency as idem\n"
    "counter = Path(os.environ['RONDO_TEST_DIR']) / 'counter.txt'\n"
    "cm = getattr(idem, 'cross_process_key_lock', None)\n"
    "if cm is None:\n"
    "    print('MISSING_CM')\n"
    "    sys.exit(0)\n"
    "with cm('K'):\n"
    "    val = int(counter.read_text()) if counter.exists() else 0\n"
    "    time.sleep(0.4)\n"
    "    counter.write_text(str(val + 1))\n"
    "print('RAN')\n"
)


def test_two_processes_same_key_serialize_no_lost_update(tmp_path) -> None:
    """Headline: two PROCESSES under cross_process_key_lock('K') don't lose an update.

    Spawns two ``sys.executable -c`` children simultaneously sharing one
    RONDO_TEST_DIR. Each does read→sleep(0.4s)→write+1 on a shared counter
    inside the lock. A real exclusive cross-process flock → final counter == 2;
    the in-process-only lock of today cannot see the peer → lost update == 1.

    MUST FAIL today: cross_process_key_lock does not exist, so each child prints
    MISSING_CM and the parent assertion below fails cleanly.
    """
    env = os.environ.copy()
    env["RONDO_TEST_DIR"] = str(tmp_path)

    proc_a = subprocess.Popen(
        [sys.executable, "-c", _CHILD_CODE],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    proc_b = subprocess.Popen(
        [sys.executable, "-c", _CHILD_CODE],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    out_a, err_a = proc_a.communicate(timeout=15)
    out_b, err_b = proc_b.communicate(timeout=15)

    assert "MISSING_CM" not in out_a and "MISSING_CM" not in out_b, (
        "checklist-22: rondo.idempotency.cross_process_key_lock is not implemented — "
        f"children reported it missing (a={out_a!r} b={out_b!r})"
    )
    assert "RAN" in out_a and "RAN" in out_b, (
        f"both children must complete the critical section: a={out_a!r}/{err_a!r} b={out_b!r}/{err_b!r}"
    )

    counter = tmp_path / "counter.txt"
    assert counter.exists(), "critical section never wrote the shared counter"
    final = int(counter.read_text())
    assert final == 2, f"checklist-22: cross-process lock did not serialize — lost update (counter={final}, expected 2)"


def test_different_keys_do_not_block_in_one_process(tmp_path, monkeypatch) -> None:
    """Same-process: two DIFFERENT keys lock independently (no cross-key blocking).

    Peak-concurrency pattern from test_idempotency.py: two threads each holding
    cross_process_key_lock on a DISTINCT key must overlap, so peak concurrency
    reaches >= 2. (Same-key would serialize; different keys must not.)
    """
    monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))
    import rondo.idempotency as idem

    cm = getattr(idem, "cross_process_key_lock", None)
    assert cm is not None, "checklist-22: cross_process_key_lock(key) not implemented yet"

    state = {"now": 0, "peak": 0}
    guard = threading.Lock()

    def _work(k: str) -> None:
        with cm(k):
            with guard:
                state["now"] += 1
                state["peak"] = max(state["peak"], state["now"])
            time.sleep(0.1)
            with guard:
                state["now"] -= 1

    threads = [threading.Thread(target=_work, args=(f"K{i}",)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert state["peak"] >= 2, f"different keys must lock independently: peak {state['peak']}"


def test_degrades_when_fcntl_unavailable(tmp_path, monkeypatch) -> None:
    """Windows rail: with fcntl blocked, cross_process_key_lock still works as a CM.

    Patching sys.modules{'fcntl': None} makes ``import fcntl`` raise ImportError.
    The context manager must degrade to in-process-only single-flight and still
    execute its body without crashing.
    """
    monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))
    import rondo.idempotency as idem

    with mock.patch.dict(sys.modules, {"fcntl": None}):
        cm = getattr(idem, "cross_process_key_lock", None)
        assert cm is not None, "checklist-22: cross_process_key_lock(key) not implemented yet"
        ran: list[bool] = []
        with cm("K"):
            ran.append(True)

    assert ran == [True], "context manager body must execute even when fcntl is unavailable"


# -- sig: mgh-6201.cd.bd955f.9010.871e7a
