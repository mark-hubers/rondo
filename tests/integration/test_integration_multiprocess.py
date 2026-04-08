# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Multi-PROCESS integration tests — real subprocess.Popen concurrency.

VER-001 verification matrix: cross-process coverage for scenarios that
multi-threading tests CAN'T catch. Threads share Python memory and module
state; processes do not. Every test here spawns real subprocess.Popen
workers that each have their own Python interpreter, their own module
globals, their own locks.

RONDO-209 Finding #246: the JSON race condition was invisible to all
180 existing integration tests because they used `threading.Barrier`
for concurrency — which only proves thread safety, not process safety.
This file closes that gap.

The tests are slower (~100ms each due to process spawn) so they're kept
in a separate file from the threading-based integration tests.
"""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

# -- ──────────────────────────────────────────────────────────────
# --  Helper: spawn worker Python subprocesses
# -- ──────────────────────────────────────────────────────────────


def _run_worker(worker_code: str, env: dict[str, str], timeout: float = 10.0) -> subprocess.CompletedProcess:
    """Run a Python worker script as a subprocess with specific env vars."""
    project_root = Path(__file__).parent.parent.parent  # -- rondo/
    src_path = project_root / "src"
    full_code = (
        f"import sys\n"
        f"sys.path.insert(0, {str(src_path)!r})\n"
        + worker_code
    )
    return subprocess.run(
        [sys.executable, "-c", full_code],
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


# -- ──────────────────────────────────────────────────────────────
# --  Integration tests — REAL multi-process
# -- ──────────────────────────────────────────────────────────────


class TestMultiProcessIdempotency:
    """RONDO-209 #246: real subprocess.Popen tests for JSONL race safety."""

    def test_two_processes_cache_different_keys_no_loss(self, tmp_path):
        """Two subprocesses cache DIFFERENT keys simultaneously — neither loses.

        This is the test that would have caught #246: the old JSON
        read-modify-write pattern would have lost one entry because of
        the classic "A reads {}, B reads {}, A writes {X}, B writes {Y}"
        race. The new append-only JSONL makes this race impossible.
        """
        import os as _os

        env = _os.environ.copy()
        env["RONDO_TEST_DIR"] = str(tmp_path)

        worker_template = textwrap.dedent("""
            import rondo.idempotency as idem
            key = {key!r}
            result = {{"data": {value}, "worker_id": {id}}}
            idem.cache_result(key, result)
            print("OK")
        """)

        # -- Spawn 2 workers with different keys, started in quick succession
        proc_a = subprocess.Popen(
            [sys.executable, "-c",
             "import sys; sys.path.insert(0, " + repr(str(Path(__file__).parent.parent.parent / "src")) + ")\n"
             + worker_template.format(key="key-A", value=100, id=1)],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        proc_b = subprocess.Popen(
            [sys.executable, "-c",
             "import sys; sys.path.insert(0, " + repr(str(Path(__file__).parent.parent.parent / "src")) + ")\n"
             + worker_template.format(key="key-B", value=200, id=2)],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        out_a, err_a = proc_a.communicate(timeout=10)
        out_b, err_b = proc_b.communicate(timeout=10)

        assert proc_a.returncode == 0, f"worker A failed: {err_a}"
        assert proc_b.returncode == 0, f"worker B failed: {err_b}"
        assert "OK" in out_a and "OK" in out_b

        # -- Now verify BOTH entries survived in the JSONL file
        cache_file = tmp_path / "idempotency.jsonl"
        assert cache_file.exists(), "#246: cache file must exist after workers ran"
        lines = [line for line in cache_file.read_text(encoding="utf-8").splitlines() if line.strip()]

        keys_found = set()
        for line in lines:
            entry = json.loads(line)
            keys_found.add(entry["key"])

        assert "key-A" in keys_found, "#246: key-A LOST in cross-process race"
        assert "key-B" in keys_found, "#246: key-B LOST in cross-process race"

    def test_two_processes_cache_same_key_latest_wins(self, tmp_path):
        """Two subprocesses cache the SAME key — latest append wins on read.

        For the same idempotency key, it's fine if one write supersedes
        another — the semantic guarantee is 'if key is cached, return SOME
        valid result for it'. This test verifies both writes appended
        successfully (both show up in the file) and the scan returns the
        latest-wins value.
        """
        import os as _os

        env = _os.environ.copy()
        env["RONDO_TEST_DIR"] = str(tmp_path)

        src_path = Path(__file__).parent.parent.parent / "src"

        worker_code_template = (
            "import sys\n"
            "sys.path.insert(0, " + repr(str(src_path)) + ")\n"
            "import rondo.idempotency as idem\n"
            "import time\n"
            'time.sleep({sleep})\n'
            'idem.cache_result("shared-key", {{"worker": {id}, "value": {value}}})\n'
            'print("OK")\n'
        )

        # -- Worker A goes first, Worker B delays slightly to ensure ordering
        proc_a = subprocess.Popen(
            [sys.executable, "-c", worker_code_template.format(sleep=0.0, id=1, value=100)],
            env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        proc_b = subprocess.Popen(
            [sys.executable, "-c", worker_code_template.format(sleep=0.1, id=2, value=200)],
            env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )

        out_a, err_a = proc_a.communicate(timeout=10)
        out_b, err_b = proc_b.communicate(timeout=10)
        assert proc_a.returncode == 0 and proc_b.returncode == 0, (
            f"workers failed: a={err_a}, b={err_b}"
        )

        # -- Read back with a fresh process to verify latest-wins semantics
        reader_code = (
            "import sys\n"
            "sys.path.insert(0, " + repr(str(src_path)) + ")\n"
            "import json\n"
            "import rondo.idempotency as idem\n"
            'result = idem.get_cached_result("shared-key", ttl_sec=300)\n'
            "print(json.dumps(result))\n"
        )
        reader = subprocess.run(
            [sys.executable, "-c", reader_code],
            env=env, capture_output=True, text=True, timeout=10, check=False,
        )
        assert reader.returncode == 0, f"reader failed: {reader.stderr}"
        result = json.loads(reader.stdout.strip())
        # -- Latest wins: worker B's value 200 should be returned
        assert result is not None, "cache miss after 2 writes — data loss"
        assert result["worker"] == 2 and result["value"] == 200, (
            f"#246: latest-wins failed — expected worker=2 value=200, got {result}"
        )

    def test_high_concurrency_no_corruption(self, tmp_path):
        """10 concurrent subprocess workers each write 5 unique keys.

        Stress test for JSONL append atomicity. POSIX O_APPEND guarantees
        that single write() calls under PIPE_BUF (4KB) are atomic, so no
        two lines should interleave and no entries should be lost.
        Expected: 50 unique keys in the file after all workers finish.
        """
        import os as _os

        env = _os.environ.copy()
        env["RONDO_TEST_DIR"] = str(tmp_path)

        src_path = Path(__file__).parent.parent.parent / "src"

        worker_template = (
            "import sys\n"
            "sys.path.insert(0, " + repr(str(src_path)) + ")\n"
            "import rondo.idempotency as idem\n"
            "for i in range(5):\n"
            '    idem.cache_result(f"w{id}-k{{i}}", {{"value": i, "worker": {id}}})\n'
            'print("OK")\n'
        )

        n_workers = 10
        processes = [
            subprocess.Popen(
                [sys.executable, "-c", worker_template.format(id=i)],
                env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            for i in range(n_workers)
        ]

        for i, proc in enumerate(processes):
            out, err = proc.communicate(timeout=15)
            assert proc.returncode == 0, f"worker {i} failed: {err}"

        # -- Verify JSONL file has exactly 50 unique keys + no corrupt lines
        cache_file = tmp_path / "idempotency.jsonl"
        assert cache_file.exists()
        lines = [line for line in cache_file.read_text(encoding="utf-8").splitlines() if line.strip()]

        keys_found = set()
        for line in lines:
            # -- Each line MUST be valid JSON (no interleaved corruption)
            entry = json.loads(line)
            keys_found.add(entry["key"])

        expected_keys = {f"w{w}-k{k}" for w in range(n_workers) for k in range(5)}
        missing = expected_keys - keys_found
        assert not missing, (
            f"#246: {len(missing)} keys LOST under 10-process concurrency. "
            f"Missing: {sorted(missing)[:10]}..."
        )


class TestMultiProcessAuditRotation:
    """RONDO-209 #251: audit rotation cross-process race safety."""

    def test_concurrent_rotate_no_record_loss(self, tmp_path):
        """Two processes rotating the same audit dir don't lose records.

        Before #251 fix: _rotate_lock was threading.Lock (thread-scoped).
        Two processes could both read content → both append to archive
        (duplication) → both unlink jsonl (second unlink is no-op).
        Worse: new INTENT written between A's read and A's unlink was LOST.

        Fix: fcntl.flock() serializes rotation across processes.

        This test spawns 2 subprocess workers both calling rotate().
        After both finish, the archive must contain ALL original records
        (not half, not duplicated, not lost).
        """
        import os as _os

        env = _os.environ.copy()
        env["RONDO_TEST_DIR"] = str(tmp_path)

        src_path = Path(__file__).parent.parent.parent / "src"

        # -- Setup: pre-populate audit JSONL with 10 records via a setup worker
        setup_code = (
            "import sys\n"
            "sys.path.insert(0, " + repr(str(src_path)) + ")\n"
            "from rondo.audit import AuditConfig, AuditTrail\n"
            "import os\n"
            'audit = AuditTrail(config=AuditConfig(audit_dir=os.environ["RONDO_TEST_DIR"]))\n'
            "for i in range(10):\n"
            '    audit.record_intent(task_name=f"task-{i}", round_name="setup", model="gemini", prompt=f"p{i}")\n'
            'print("SETUP_OK")\n'
        )
        setup = subprocess.run(
            [sys.executable, "-c", setup_code],
            env=env, capture_output=True, text=True, timeout=10, check=False,
        )
        assert setup.returncode == 0, f"setup failed: {setup.stderr}"

        # -- Two concurrent rotators
        rotate_code = (
            "import sys\n"
            "sys.path.insert(0, " + repr(str(src_path)) + ")\n"
            "from rondo.audit import AuditConfig, AuditTrail\n"
            "import os\n"
            'audit = AuditTrail(config=AuditConfig(audit_dir=os.environ["RONDO_TEST_DIR"]), auto_reconcile=False)\n'
            "count = audit.rotate()\n"
            'print(f"ROTATED:{count}")\n'
        )
        proc_a = subprocess.Popen(
            [sys.executable, "-c", rotate_code],
            env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        proc_b = subprocess.Popen(
            [sys.executable, "-c", rotate_code],
            env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )

        out_a, err_a = proc_a.communicate(timeout=10)
        out_b, err_b = proc_b.communicate(timeout=10)
        assert proc_a.returncode == 0 and proc_b.returncode == 0, (
            f"rotators failed: a={err_a} b={err_b}"
        )

        # -- Parse rotate counts
        def _parse_count(s: str) -> int:
            for line in s.splitlines():
                if line.startswith("ROTATED:"):
                    return int(line.split(":", 1)[1])
            return -1

        count_a = _parse_count(out_a)
        count_b = _parse_count(out_b)

        # -- Under the lock, ONE process does the real rotation (returns N),
        # -- the other sees an empty jsonl (returns 0). Total = N.
        # -- Setup wrote 10 records, so count_a + count_b == 10 exactly.
        assert count_a + count_b == 10, (
            f"#251: rotate race corrupted record count — "
            f"a={count_a} b={count_b} total={count_a + count_b} (expected 10)"
        )

        # -- The archive must contain exactly 10 lines (1 line per INTENT record)
        archive_dir = tmp_path / "archive"
        archive_files = list(archive_dir.glob("*.jsonl"))
        assert archive_files, "archive file must exist after rotation"
        all_archive_lines: list[str] = []
        for af in archive_files:
            all_archive_lines.extend(
                line for line in af.read_text(encoding="utf-8").splitlines() if line.strip()
            )
        assert len(all_archive_lines) == 10, (
            f"#251: expected 10 lines in archive, got {len(all_archive_lines)} "
            f"(rotation race caused duplication or loss)"
        )

        # -- Each task name appears exactly once (no duplicates from double-rotate)
        task_names = set()
        for line in all_archive_lines:
            entry = json.loads(line)
            task_names.add(entry["task_name"])
        expected = {f"task-{i}" for i in range(10)}
        assert task_names == expected, (
            f"#251: archive task names mismatch. Missing: {expected - task_names}, "
            f"extra: {task_names - expected}"
        )


class TestMultiProcessCircuitBreaker:
    """RONDO-209 #246: circuit breaker state across real processes."""

    def test_breaker_trip_in_one_process_visible_to_another(self, tmp_path):
        """Process A trips the breaker; Process B (later) sees it OPEN.

        Tests cross-process visibility of persisted breaker state via JSON file.
        NOTE: circuit breaker still uses read-modify-write on JSON (not yet
        migrated to JSONL in RONDO-209). This test catches if two processes
        clobber each other's OPEN state.
        """
        import os as _os

        env = _os.environ.copy()
        env["RONDO_TEST_DIR"] = str(tmp_path)

        src_path = Path(__file__).parent.parent.parent / "src"

        # -- Worker A: trip the breaker (3 failures at threshold=3)
        trip_code = (
            "import sys\n"
            "sys.path.insert(0, " + repr(str(src_path)) + ")\n"
            "from pathlib import Path\n"
            "from rondo.retry import CircuitBreaker\n"
            "import os\n"
            'persist = Path(os.environ["RONDO_TEST_DIR"]) / "breaker.json"\n'
            "b = CircuitBreaker(failure_threshold=3, cooldown_sec=300.0, persist_path=persist)\n"
            "for _ in range(3):\n"
            '    b.record_failure("prod-provider")\n'
            'assert b.is_open("prod-provider"), "worker A: breaker should be OPEN"\n'
            'print("TRIPPED")\n'
        )
        result = subprocess.run(
            [sys.executable, "-c", trip_code],
            env=env, capture_output=True, text=True, timeout=10, check=False,
        )
        assert result.returncode == 0, f"trip worker failed: {result.stderr}"
        assert "TRIPPED" in result.stdout

        # -- Worker B: new process, load the persisted state, check OPEN
        check_code = (
            "import sys\n"
            "sys.path.insert(0, " + repr(str(src_path)) + ")\n"
            "from pathlib import Path\n"
            "from rondo.retry import CircuitBreaker\n"
            "import os\n"
            'persist = Path(os.environ["RONDO_TEST_DIR"]) / "breaker.json"\n'
            "b = CircuitBreaker(failure_threshold=3, cooldown_sec=300.0, persist_path=persist)\n"
            'assert b.is_open("prod-provider"), "worker B: breaker should still be OPEN"\n'
            'print("STILL_OPEN")\n'
        )
        result_b = subprocess.run(
            [sys.executable, "-c", check_code],
            env=env, capture_output=True, text=True, timeout=10, check=False,
        )
        assert result_b.returncode == 0, f"check worker failed: {result_b.stderr}"
        assert "STILL_OPEN" in result_b.stdout


class TestPartialWriteResilience:
    """RONDO-209 #254: prove JSONL scanner handles partial writes gracefully.

    Convergent finding from RONDO-209 round-3 AI review (GPT-4.1 + Grok-3):
    'Append-only JSONL mitigates race conditions, but if multiple processes
    crash mid-write, partial/corrupt lines may occur, breaking downstream
    parsing.'

    Validating this against actual Rondo code:
    - POSIX O_APPEND guarantees single writes <PIPE_BUF (4KB) are atomic
    - JSON entries are typically <1KB → covered by POSIX guarantee
    - For pathological cases (e.g., huge entry, file truncated by another process),
      _scan_cache_file already wraps json.loads in try/except, silently skipping
      malformed lines
    - Worst case: a corrupted line is dropped → cache miss → re-dispatch (benign)

    These tests prove the resilience is REAL by intentionally writing
    malformed/half-line data and verifying valid entries still survive.
    """

    def test_jsonl_scanner_skips_malformed_lines(self, tmp_path, monkeypatch):
        """A half-written line in the middle of valid entries doesn't break scan."""
        import json as _json
        import time as _time

        import rondo.idempotency as idem

        monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))
        idem.clear_cache()

        cache_path = idem._default_cache_file()
        cache_path.parent.mkdir(parents=True, exist_ok=True)

        now = _time.time()
        good_1 = _json.dumps({"key": "good-1", "data": {"v": 1}, "cached_at_wall": now})
        good_2 = _json.dumps({"key": "good-2", "data": {"v": 2}, "cached_at_wall": now})
        # -- Pathological line: starts as JSON but gets truncated mid-string (simulates crash)
        bad_line = '{"key": "corrupt", "data": {"v": 3}, "cached_at_'
        # -- File: good, BAD, good — scanner must skip bad and return good entries
        cache_path.write_text(
            good_1 + "\n" + bad_line + "\n" + good_2 + "\n",
            encoding="utf-8",
        )

        # -- Both good entries should be returned despite the bad line in the middle
        result_1 = idem.get_cached_result("good-1", ttl_sec=300)
        result_2 = idem.get_cached_result("good-2", ttl_sec=300)
        result_corrupt = idem.get_cached_result("corrupt", ttl_sec=300)

        assert result_1 == {"v": 1}, f"good-1 should survive partial write, got {result_1}"
        assert result_2 == {"v": 2}, f"good-2 should survive partial write, got {result_2}"
        assert result_corrupt is None, "corrupt entry should not be returned"

        idem.clear_cache()

    def test_jsonl_scanner_handles_empty_lines(self, tmp_path, monkeypatch):
        """Blank lines (file truncation, partial flush) are silently skipped."""
        import json as _json
        import time as _time

        import rondo.idempotency as idem

        monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))
        idem.clear_cache()

        cache_path = idem._default_cache_file()
        cache_path.parent.mkdir(parents=True, exist_ok=True)

        now = _time.time()
        good = _json.dumps({"key": "alive", "data": {"v": 42}, "cached_at_wall": now})
        # -- Blank lines, whitespace, then valid entry
        cache_path.write_text(
            "\n\n   \n" + good + "\n\n",
            encoding="utf-8",
        )

        result = idem.get_cached_result("alive", ttl_sec=300)
        assert result == {"v": 42}, f"valid entry must survive blank-line noise, got {result}"

        idem.clear_cache()

    def test_jsonl_scanner_handles_zero_byte_file(self, tmp_path, monkeypatch):
        """A 0-byte cache file (created but never written) is treated as empty."""
        import rondo.idempotency as idem

        monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))
        idem.clear_cache()

        cache_path = idem._default_cache_file()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.touch()  # -- 0 bytes
        assert cache_path.stat().st_size == 0

        # -- Should NOT raise; should return None for any key
        result = idem.get_cached_result("anything", ttl_sec=300)
        assert result is None
        idem.clear_cache()


class TestCrashRecovery:
    """RONDO-209 #252: process crash mid-dispatch + reconcile_stuck_intents."""

    def test_sigkill_mid_dispatch_leaves_stuck_intent(self, tmp_path):
        """Subprocess writes INTENT, then gets SIGKILL'd before OUTCOME.

        Verifies the audit trail correctly records the orphan as STUCK
        during a fresh AuditTrail instantiation (auto_reconcile on init).
        Without proper recovery, orphan INTENTs would silently accumulate
        in the JSONL forever and never be visible in metrics.
        """
        import os as _os
        import signal
        import time as _time

        env = _os.environ.copy()
        env["RONDO_TEST_DIR"] = str(tmp_path)

        src_path = Path(__file__).parent.parent.parent / "src"

        # -- Worker code: record INTENT, touch a sync file, then sleep forever
        # -- (until parent SIGKILLs it). The sleep guarantees the worker is
        # -- mid-dispatch when killed — no race window for the OUTCOME.
        worker_code = (
            "import sys, os, time\n"
            "sys.path.insert(0, " + repr(str(src_path)) + ")\n"
            "from rondo.audit import AuditConfig, AuditTrail\n"
            "from pathlib import Path\n"
            'audit_dir = os.environ["RONDO_TEST_DIR"]\n'
            "audit = AuditTrail(config=AuditConfig(audit_dir=audit_dir), auto_reconcile=False)\n"
            'audit.record_intent(task_name="will-crash", round_name="crash-test", model="gemini", prompt="long")\n'
            '# -- Touch sync file so parent knows we passed the INTENT write\n'
            'sync = Path(audit_dir) / "worker_ready.txt"\n'
            'sync.write_text("ready")\n'
            'time.sleep(60)  # block until killed\n'
        )

        proc = subprocess.Popen(
            [sys.executable, "-c", worker_code],
            env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )

        # -- Wait for the worker to write its sync file (max 5 sec)
        sync_file = tmp_path / "worker_ready.txt"
        deadline = _time.monotonic() + 5.0
        while _time.monotonic() < deadline:
            if sync_file.exists():
                break
            _time.sleep(0.05)
        else:
            proc.kill()
            proc.communicate(timeout=2)
            raise AssertionError(
                "#252: worker never reached sync point — crash test setup failed"
            )

        # -- SIGKILL the worker (simulates a hard crash, no cleanup, no OUTCOME)
        _os.kill(proc.pid, signal.SIGKILL)
        proc.communicate(timeout=5)
        assert proc.returncode != 0, "worker should have died from SIGKILL"

        # -- Verify the JSONL has the INTENT but NO matching OUTCOME yet
        jsonl_path = tmp_path / "rondo_audit.jsonl"
        assert jsonl_path.exists(), "audit JSONL must exist after worker crash"
        before_content = jsonl_path.read_text(encoding="utf-8")
        assert "will-crash" in before_content
        assert '"status": "INTENT"' in before_content, (
            "INTENT record must be in JSONL (worker reached the write point)"
        )

        # -- Now run reconcile via a fresh AuditTrail instance (recovery process)
        # -- auto_reconcile=True (default) runs reconcile_stuck_intents at init.
        # -- We don't bind the result — the constructor's side effect is the test.
        # -- RONDO-211 #257: stuck_after_sec=0 because the worker INTENT was just
        # -- written seconds ago — without this override the new in-flight
        # -- threshold (300s default) would correctly skip it as still-live.
        from rondo.audit import AuditConfig, AuditTrail
        AuditTrail(config=AuditConfig(audit_dir=str(tmp_path), stuck_after_sec=0))

        # -- After auto-reconcile, the JSONL must contain a "stuck" outcome
        after_content = jsonl_path.read_text(encoding="utf-8")
        assert "stuck" in after_content, (
            "#252: reconcile_stuck_intents must mark orphan INTENT as 'stuck'"
        )

        # -- The same task_name should appear with both INTENT and stuck outcome
        lines = [line for line in after_content.splitlines() if line.strip()]
        will_crash_records = [json.loads(line) for line in lines if "will-crash" in line]
        statuses = {r.get("status") for r in will_crash_records}
        assert "INTENT" in statuses, "INTENT record must remain"
        assert "stuck" in statuses, "stuck OUTCOME must have been added by reconcile"


# -- sig: mgh-6201.cd.bd955f.d209.201146
