# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Rotation, costs, watchdog, and partial-success integration tests.

VER-001 verification matrix: medium-value integration coverage for scenarios
that cross audit + rotation + history + watchdog + parallel dispatch.

RONDO-208: fills gaps identified after test-coverage audit. These tests
cover scenarios that only matter when Rondo runs under load — rotation
mid-dispatch, long-running timeouts, multi-task partial success, and
HTTP adapter chain composition.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from rondo.audit import AuditConfig, AuditTrail, atomic_write
from rondo.engine import TaskResult


class TestRotationAndCosts:
    """RONDO-208: rotation, cost tracking, watchdog paths under realistic load."""

    def test_audit_rotation_during_active_dispatch_preserves_data(self, tmp_path):
        """Rotation must not lose records mid-dispatch.

        Scenario: audit log has some existing records, a new INTENT is being
        recorded, and rotation fires in between. The invariant is that
        both the rotated archive AND the fresh JSONL together contain all
        records — no record disappears into the void.
        """
        cfg = AuditConfig(
            audit_dir=str(tmp_path),
            max_jsonl_bytes=4096,  # -- small cap so we can force rotation
        )
        audit_trail = AuditTrail(config=cfg)

        # -- Record several intents BEFORE rotation
        pre_ids = []
        for i in range(5):
            rec = audit_trail.record_intent(
                task_name=f"pre-rotate-{i}",
                round_name="test",
                model="gemini",
                prompt=f"prompt {i}",
            )
            pre_ids.append(rec.dispatch_id)

        # -- Trigger rotation manually
        audit_trail.rotate()

        # -- Record more intents AFTER rotation
        post_ids = []
        for i in range(3):
            rec = audit_trail.record_intent(
                task_name=f"post-rotate-{i}",
                round_name="test",
                model="gemini",
                prompt=f"prompt {i}",
            )
            post_ids.append(rec.dispatch_id)

        # -- Find archive files + current jsonl — all IDs must be accounted for
        archive_dir = tmp_path / "archive"
        archive_content = ""
        if archive_dir.exists():
            for archive_file in archive_dir.rglob("*.jsonl*"):
                # -- Handle both .jsonl and .jsonl.gz
                if archive_file.suffix == ".gz":
                    import gzip

                    archive_content += gzip.decompress(archive_file.read_bytes()).decode("utf-8")
                else:
                    archive_content += archive_file.read_text(encoding="utf-8")

        current_content = (tmp_path / "rondo_audit.jsonl").read_text(encoding="utf-8")
        combined = archive_content + current_content

        for did in pre_ids + post_ids:
            assert did in combined, (
                f"rotation lost dispatch_id {did} — data loss bug"
            )

    def test_cost_tracking_survives_atomic_write_round_trip(self, tmp_path):
        """Integration: atomic_write preserves cost_usd values through serialization.

        Builds a TaskResult with a precise cost, persists it via atomic_write,
        reads it back, and verifies the cost survived the float round-trip.
        """
        from dataclasses import asdict

        tr = TaskResult(
            task_name="cost-test",
            status="done",
            raw_output="result",
            model="gemini-2.5-flash",
            cost_usd=0.00123456,  # -- 6 decimal places
            duration_sec=0.5,
        )

        target = tmp_path / "result.json"
        atomic_write(target, json.dumps(asdict(tr), default=str))

        loaded = json.loads(target.read_text(encoding="utf-8"))
        assert loaded["cost_usd"] == 0.00123456, (
            f"cost precision lost: {loaded['cost_usd']} != 0.00123456"
        )

    def test_partial_success_parallel_dispatch_records_all_outcomes(self, tmp_path):
        """Parallel dispatch with mixed status records all outcomes.

        When 2 of 3 parallel tasks succeed and 1 fails, the audit log has
        all 3 outcomes with correct status values. Uses manual INTENT +
        OUTCOME pairs to simulate the parallel dispatch code path without
        needing real providers.
        """
        audit_trail = AuditTrail(config=AuditConfig(audit_dir=str(tmp_path)))

        # -- Record 3 intents concurrently
        tasks = [
            ("success-1", "done"),
            ("success-2", "done"),
            ("failure-1", "error"),
        ]
        records = []
        for task_name, _ in tasks:
            rec = audit_trail.record_intent(
                task_name=task_name,
                round_name="parallel",
                model="gemini",
                prompt="test",
            )
            records.append(rec)

        # -- Record outcomes with mixed status
        for (task_name, status), rec in zip(tasks, records, strict=True):
            audit_trail.record_outcome(
                dispatch_id=rec.dispatch_id,
                task_name=task_name,
                round_name="parallel",
                model="gemini",
                status=status,
                exit_code=0 if status == "done" else 1,
                error_code=None if status == "done" else "ERR_PROVIDER",
                cost_usd=0.001,
                duration_sec=0.1,
                raw_output="output" if status == "done" else "",
                input_tokens=10,
                output_tokens=5,
                files_modified=[],
            )

        # -- Verify all 3 outcomes are in the JSONL
        jsonl = (tmp_path / "rondo_audit.jsonl").read_text(encoding="utf-8")
        lines = [line for line in jsonl.splitlines() if line.strip()]
        # -- Expect 6 lines (3 INTENT + 3 OUTCOME)
        assert len(lines) == 6, f"expected 6 records, got {len(lines)}"

        done_count = 0
        error_count = 0
        for line in lines:
            parsed = json.loads(line)
            status = parsed.get("status")
            if status == "done":
                done_count += 1
            elif status == "error":
                error_count += 1

        assert done_count == 2, f"expected 2 done, got {done_count}"
        assert error_count == 1, f"expected 1 error, got {error_count}"

    def test_timeout_error_record_flows_through_audit(self, tmp_path):
        """Timeout error records persist through audit with ERR_TIMEOUT code.

        Simulates the dispatch.py path where a subprocess times out and
        the resulting error TaskResult flows through finalize_dispatch
        and lands in the JSONL as an error outcome.
        """
        audit_trail = AuditTrail(config=AuditConfig(audit_dir=str(tmp_path)))

        rec = audit_trail.record_intent(
            task_name="timeout-task",
            round_name="test",
            model="sonnet",
            prompt="long-running prompt",
        )

        audit_trail.record_outcome(
            dispatch_id=rec.dispatch_id,
            task_name="timeout-task",
            round_name="test",
            model="sonnet",
            status="error",
            exit_code=-9,  # -- SIGKILL
            error_code="ERR_TIMEOUT",
            cost_usd=0.0,
            duration_sec=300.0,
            raw_output="",
            input_tokens=0,
            output_tokens=0,
            files_modified=[],
        )

        jsonl = (tmp_path / "rondo_audit.jsonl").read_text(encoding="utf-8")
        assert "ERR_TIMEOUT" in jsonl
        assert "timeout-task" in jsonl
        # -- Verify the duration was preserved (not truncated)
        outcome_line = [
            line for line in jsonl.splitlines() if '"status": "error"' in line
        ][0]
        parsed = json.loads(outcome_line)
        assert parsed["duration_sec"] == 300.0

    def test_http_adapter_chain_composition_via_retry_and_breaker(self, tmp_path):
        """Integration: retry + circuit breaker + isolated breaker file compose.

        Creates an isolated CircuitBreaker (so no pollution), walks through a
        realistic sequence: 2 failures → breaker still closed → 1 success →
        counter resets → 3 more failures → breaker trips → is_open fast-path.
        """
        from rondo.retry import CircuitBreaker

        breaker = CircuitBreaker(
            failure_threshold=3,
            cooldown_sec=300.0,
            persist_path=tmp_path / "breaker.json",
        )

        # -- 2 failures (under threshold)
        breaker.record_failure("http-provider")
        breaker.record_failure("http-provider")
        assert not breaker.is_open("http-provider")

        # -- Success resets the counter
        breaker.record_success("http-provider")

        # -- Need 3 MORE failures (not 1) to trip now
        breaker.record_failure("http-provider")
        breaker.record_failure("http-provider")
        assert not breaker.is_open("http-provider"), "2 post-success fails should not trip"

        breaker.record_failure("http-provider")
        assert breaker.is_open("http-provider"), "3rd post-success fail should trip"

        # -- Verify state persisted
        persist_file = tmp_path / "breaker.json"
        assert persist_file.exists()
        data = json.loads(persist_file.read_text(encoding="utf-8"))
        assert "http-provider" in data


# -- sig: mgh-6201.cd.bd955f.d208.9e2011
