# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Retry, circuit breaker, multi-hop fallback, and pipeline integrity paths.

Split from TestAlwaysOnPipeline in RONDO-207. The original class had
67 tests in 1479 lines — above best-practice file size. This file is
a focused slice by theme: reliability.

VER-001: Product acceptance / unit test coverage.
"""

from __future__ import annotations

import sys

import pytest

# -- Ensure rondo is importable
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent / "src"))



class TestPipelineReliability:
    """RONDO-139 + RONDO-204 + RONDO-205: Retry, circuit breaker, multi-hop fallback, and pipeline integrity paths."""

    def test_dry_run_provider_path_calls_finalize(self, tmp_path) -> None:
        """dry_run=True on provider path now goes through finalize_dispatch.

        Was: appended TaskResult(skipped) directly, no pipeline.
        Now: pipeline runs, audit records the skipped task.
        """
        from unittest.mock import patch

        from rondo.engine import Round, RoundResult, Task
        from rondo.mcp_dispatch import _dispatch_via_provider_or_claude

        round_def = Round(
            name="dry-run-test",
            tasks=[Task(name="t1", instruction="hi", done_when="done")],
        )

        with patch("rondo.mcp_dispatch.finalize_dispatch") as mock_finalize:
            from rondo.engine import DispatchUsage, TaskResult

            mock_finalize.return_value = (
                TaskResult(task_name="t1", status="skipped", model="gemini-2.5-flash"),
                DispatchUsage(task_name="t1", model="gemini-2.5-flash", cost_usd=0.0),
            )
            result = _dispatch_via_provider_or_claude(
                round_def=round_def,
                config=None,
                model="gemini:gemini-2.5-flash",
                prompt="hi",
                dry_run=True,
                run_round=lambda *a, **kw: None,
            )
        assert isinstance(result, RoundResult)
        # -- finalize_dispatch was called for the dry-run task (this is the fix)
        assert mock_finalize.called, "RONDO-139: dry-run path must call finalize_dispatch"

    def test_provider_down_path_calls_finalize(self) -> None:
        """provider-down error path now goes through finalize_dispatch.

        Was: returned RoundResult immediately, no pipeline.
        Now: error TaskResult flows through finalize.
        """
        from unittest.mock import patch

        from rondo.engine import Round, RoundResult, Task
        from rondo.mcp_dispatch import _dispatch_via_provider_or_claude

        round_def = Round(
            name="provider-down-test",
            tasks=[Task(name="t1", instruction="hi", done_when="done")],
        )

        with (
            patch("rondo.mcp_dispatch.get_provider_with_fallback") as mock_get,
            patch("rondo.mcp_dispatch.finalize_dispatch") as mock_finalize,
        ):
            from rondo.engine import DispatchUsage, TaskResult

            mock_get.return_value = (None, "")  # -- provider down, no fallback
            mock_finalize.return_value = (
                TaskResult(task_name="dispatch", status="error", error_code="ERR_PROVIDER_DOWN", model="gemini:flash"),
                DispatchUsage(task_name="dispatch", model="gemini:flash", cost_usd=0.0),
            )
            result = _dispatch_via_provider_or_claude(
                round_def=round_def,
                config=None,
                model="gemini:flash",
                prompt="hi",
                dry_run=False,
                run_round=lambda *a, **kw: None,
            )
        assert isinstance(result, RoundResult)
        assert result.status == "error"
        # -- THE FIX: provider-down path now calls finalize_dispatch
        assert mock_finalize.called, "RONDO-139: provider-down path must call finalize_dispatch"

    def test_adapter_exception_path_calls_finalize(self) -> None:
        """When provider.dispatch raises, the error TaskResult goes through finalize.

        Was: exception bubbled up to _execute_dispatch, no pipeline.
        Now: caught in dispatch loop, wrapped in TaskResult, sent through finalize.
        """
        from unittest.mock import MagicMock, patch

        from rondo.engine import Round, RoundResult, Task
        from rondo.mcp_dispatch import _dispatch_via_provider_or_claude

        round_def = Round(
            name="exception-test",
            tasks=[Task(name="t1", instruction="hi", done_when="done")],
        )

        # -- Mock provider that raises
        bad_provider = MagicMock()
        bad_provider.dispatch.side_effect = RuntimeError("simulated adapter crash")

        with (
            patch("rondo.mcp_dispatch.get_provider_with_fallback") as mock_get,
            patch("rondo.mcp_dispatch.finalize_dispatch") as mock_finalize,
        ):
            from rondo.engine import DispatchUsage, TaskResult

            mock_get.return_value = (bad_provider, "gemini-2.5-flash")
            mock_finalize.return_value = (
                TaskResult(task_name="t1", status="error", error_code="ERR_PROVIDER", model="gemini-2.5-flash"),
                DispatchUsage(task_name="t1", model="gemini-2.5-flash", cost_usd=0.0),
            )
            result = _dispatch_via_provider_or_claude(
                round_def=round_def,
                config=None,
                model="gemini:gemini-2.5-flash",
                prompt="hi",
                dry_run=False,
                run_round=lambda *a, **kw: None,
            )
        assert isinstance(result, RoundResult)
        # -- THE FIX: adapter exceptions caught + finalize called
        assert mock_finalize.called, "RONDO-139: adapter exception path must call finalize_dispatch"
        # -- The error result must be in task_results
        assert len(result.task_results) == 1
        assert result.task_results[0].status == "error"

    def test_finalize_failure_does_not_lose_result(self) -> None:
        """If finalize_dispatch itself raises, original TaskResult is preserved.

        Defensive: never lose the dispatch result to a finalization bug.
        """
        from unittest.mock import MagicMock, patch

        from rondo.engine import Round, RoundResult, Task, TaskResult
        from rondo.mcp_dispatch import _dispatch_via_provider_or_claude

        round_def = Round(
            name="finalize-fail-test",
            tasks=[Task(name="t1", instruction="hi", done_when="done")],
        )

        good_provider = MagicMock()
        good_provider.dispatch.return_value = TaskResult(
            task_name="t1", status="done", raw_output="real output", model="gemini-2.5-flash"
        )

        with (
            patch("rondo.mcp_dispatch.get_provider_with_fallback") as mock_get,
            patch("rondo.mcp_dispatch.finalize_dispatch") as mock_finalize,
        ):
            mock_get.return_value = (good_provider, "gemini-2.5-flash")
            mock_finalize.side_effect = OSError("simulated finalize crash")

            result = _dispatch_via_provider_or_claude(
                round_def=round_def,
                config=None,
                model="gemini:gemini-2.5-flash",
                prompt="hi",
                dry_run=False,
                run_round=lambda *a, **kw: None,
            )
        # -- Defensive: original result preserved even when finalize crashes
        assert isinstance(result, RoundResult)
        assert len(result.task_results) == 1
        assert result.task_results[0].raw_output == "real output"
        assert result.task_results[0].status == "done"

    def test_retry_http_retries_on_500(self) -> None:
        """RONDO-145 (Finding #211): retry_http retries on 500 errors."""
        import urllib.error

        from rondo.retry import RetryConfig, retry_http

        call_count = [0]

        def flaky_call():
            call_count[0] += 1
            if call_count[0] < 3:
                raise urllib.error.HTTPError("http://test", 503, "Service Unavailable", {}, None)
            return "success"

        result = retry_http(
            flaky_call,
            config=RetryConfig(max_attempts=5, initial_delay_sec=0.01, max_delay_sec=0.05, jitter=False),
        )
        assert result == "success"
        assert call_count[0] == 3, "Should have retried twice before succeeding"

    def test_retry_http_no_retry_on_401(self) -> None:
        """RONDO-145: 401 (auth failure) is NOT transient — no retry."""
        import urllib.error

        from rondo.retry import RetryConfig, retry_http

        call_count = [0]

        def unauth_call():
            call_count[0] += 1
            raise urllib.error.HTTPError("http://test", 401, "Unauthorized", {}, None)

        with pytest.raises(urllib.error.HTTPError) as exc_info:
            retry_http(
                unauth_call,
                config=RetryConfig(max_attempts=5, initial_delay_sec=0.01, jitter=False),
            )
        assert exc_info.value.code == 401
        assert call_count[0] == 1, "Should NOT retry on 401"

    def test_retry_http_exhausts_attempts(self) -> None:
        """RONDO-145: Gives up after max_attempts on persistent transient errors."""
        import urllib.error

        from rondo.retry import RetryConfig, retry_http

        call_count = [0]

        def always_fails():
            call_count[0] += 1
            raise urllib.error.HTTPError("http://test", 503, "Always down", {}, None)

        with pytest.raises(urllib.error.HTTPError):
            retry_http(
                always_fails,
                config=RetryConfig(max_attempts=3, initial_delay_sec=0.01, jitter=False),
            )
        assert call_count[0] == 3, f"Expected 3 attempts, got {call_count[0]}"

    def test_circuit_breaker_opens_after_threshold(self) -> None:
        """RONDO-145: Circuit breaker opens after N consecutive failures."""
        from rondo.retry import CircuitBreaker

        breaker = CircuitBreaker(failure_threshold=3, cooldown_sec=60.0)
        assert not breaker.is_open("test-provider")

        # -- Record failures up to threshold
        breaker.record_failure("test-provider")
        breaker.record_failure("test-provider")
        assert not breaker.is_open("test-provider"), "Should still be closed at 2 failures"

        breaker.record_failure("test-provider")
        assert breaker.is_open("test-provider"), "Should be OPEN at 3 failures"

    def test_circuit_breaker_isolates_providers(self) -> None:
        """RONDO-145: Failures on one provider don't affect another."""
        from rondo.retry import CircuitBreaker

        breaker = CircuitBreaker(failure_threshold=2)
        breaker.record_failure("provider-a")
        breaker.record_failure("provider-a")
        assert breaker.is_open("provider-a")
        assert not breaker.is_open("provider-b"), "Provider B should still be closed"

    def test_circuit_breaker_recovers_on_success(self) -> None:
        """RONDO-145: Successful call resets failure count."""
        from rondo.retry import CircuitBreaker

        breaker = CircuitBreaker(failure_threshold=3)
        breaker.record_failure("test")
        breaker.record_failure("test")
        breaker.record_success("test")
        # -- Failure count reset — need 3 more to trip
        breaker.record_failure("test")
        breaker.record_failure("test")
        assert not breaker.is_open("test"), "Should still be closed after recovery + 2 failures"

    def test_circuit_breaker_persists_across_restart(self, tmp_path) -> None:
        """RONDO-205 Finding #236: OPEN state survives process restart.

        Simulates a restart by creating a second CircuitBreaker pointed at
        the same persist file. Without persistence, the second breaker
        would start fresh and allow a 6th failure through to the down
        provider. With persistence, it remains OPEN.
        """
        from rondo.retry import CircuitBreaker

        persist_file = tmp_path / "breaker.json"

        # -- "Process 1": trip the breaker
        breaker_1 = CircuitBreaker(
            failure_threshold=3,
            cooldown_sec=300.0,
            persist_path=persist_file,
        )
        for _ in range(3):
            breaker_1.record_failure("down-provider")
        assert breaker_1.is_open("down-provider"), "Breaker should be OPEN after 3 failures"
        assert persist_file.exists(), "Persist file must exist after trip"

        # -- "Process 2": simulate restart — new breaker instance, same file
        breaker_2 = CircuitBreaker(
            failure_threshold=3,
            cooldown_sec=300.0,
            persist_path=persist_file,
        )
        assert breaker_2.is_open("down-provider"), (
            "After restart, breaker must still be OPEN — #236 persistence"
        )

        # -- Other providers should be unaffected
        assert not breaker_2.is_open("healthy-provider"), "Non-failed providers start closed"

    def test_circuit_breaker_expired_state_not_restored(self, tmp_path) -> None:
        """RONDO-205 Finding #236: expired OPEN states are dropped on load.

        If the persist file has a breaker whose cooldown has already
        elapsed (wall-clock), loading it should NOT restore the OPEN
        state — the provider has had time to recover.
        """
        import json as _json
        import time as _time

        from rondo.retry import CircuitBreaker

        persist_file = tmp_path / "breaker.json"
        # -- Write a stale OPEN entry (cooldown expired 100s ago)
        stale_payload = {
            "stale-provider": {
                "open_until": _time.time() - 100.0,
                "failure_count": 5.0,
            },
        }
        persist_file.write_text(_json.dumps(stale_payload), encoding="utf-8")

        breaker = CircuitBreaker(
            failure_threshold=3,
            cooldown_sec=60.0,
            persist_path=persist_file,
        )
        assert not breaker.is_open("stale-provider"), (
            "Expired OPEN state must not be restored — provider may have recovered"
        )

    def test_multi_hop_fallback_walks_chain(self) -> None:
        """RONDO-200 (Finding #219): get_provider_with_fallback walks multi-hop chain."""
        from unittest.mock import patch

        from rondo.providers import get_provider_with_fallback

        health_calls: dict[str, bool] = {
            "gemini": False,
            "grok": False,
            "mistral": True,
        }

        def fake_health(provider: str) -> bool:
            return health_calls.get(provider, False)

        def fake_fallback(provider: str) -> str:
            return {"gemini": "grok", "grok": "mistral"}.get(provider, "")

        with (
            patch("rondo.adapters.health.is_provider_healthy", side_effect=fake_health),
            patch("rondo.providers._get_fallback_provider", side_effect=fake_fallback),
        ):
            _adapter, resolved = get_provider_with_fallback("gemini:gemini-2.5-flash")
            assert "mistral" in resolved, f"Expected mistral fallback, got: {resolved}"

    def test_multi_hop_fallback_cycle_detection(self) -> None:
        """RONDO-200: cycle in fallback chain doesn't loop forever."""
        from unittest.mock import patch

        from rondo.providers import get_provider_with_fallback

        def all_unhealthy(_provider: str) -> bool:
            return False

        def cyclic_fallback(provider: str) -> str:
            return {"gemini": "grok", "grok": "gemini"}.get(provider, "")

        with (
            patch("rondo.adapters.health.is_provider_healthy", side_effect=all_unhealthy),
            patch("rondo.providers._get_fallback_provider", side_effect=cyclic_fallback),
        ):
            adapter, resolved = get_provider_with_fallback("gemini:gemini-2.5-flash")
            assert adapter is None
            assert resolved == ""

    def test_atomic_write_helper_creates_file(self, tmp_path) -> None:
        """RONDO-144 (Finding #210): atomic_write creates the file correctly."""
        from rondo.audit import atomic_write

        target = tmp_path / "test.txt"
        atomic_write(target, "hello world")
        assert target.exists()
        assert target.read_text() == "hello world"

    def test_atomic_write_no_tmp_leftover(self, tmp_path) -> None:
        """RONDO-144: atomic write cleans up temp file on success."""
        from rondo.audit import atomic_write

        target = tmp_path / "data.json"
        atomic_write(target, '{"key":"value"}')
        tmp_files = list(tmp_path.glob("*.tmp"))
        assert len(tmp_files) == 0, f"Temp file leaked: {tmp_files}"
        assert target.read_text() == '{"key":"value"}'

    def test_audit_log_auto_rotates_at_size_limit(self, tmp_path) -> None:
        """RONDO-144 (Finding #212): JSONL auto-rotates when size exceeds max_jsonl_bytes."""
        from rondo.audit import AuditConfig, AuditTrail

        # -- Tiny cap so one INTENT record triggers rotation
        trail = AuditTrail(config=AuditConfig(audit_dir=str(tmp_path), max_jsonl_bytes=100))

        # -- Record enough INTENT+OUTCOME pairs to exceed cap
        for i in range(5):
            record = trail.record_intent(
                task_name=f"t{i}", round_name="rot-test", model="gemini-2.5-flash", prompt=f"prompt {i}"
            )
            trail.record_outcome(
                dispatch_id=record.dispatch_id,
                status="done",
                exit_code=0,
                raw_output="ok",
            )

        # -- archive/ should exist with rotated file
        archive_dir = tmp_path / "archive"
        assert archive_dir.exists(), "Archive dir missing — rotation didn't fire"
        archive_files = list(archive_dir.glob("*.jsonl"))
        assert len(archive_files) >= 1, "No archive files — rotation didn't write"

    def test_audit_result_file_is_atomic(self, tmp_path) -> None:
        """RONDO-144: result file write uses atomic pattern."""
        from rondo.audit import AuditConfig, AuditTrail

        trail = AuditTrail(config=AuditConfig(audit_dir=str(tmp_path)))
        record = trail.record_intent(
            task_name="t", round_name="atomic-test", model="gemini-2.5-flash", prompt="hi"
        )
        trail.record_outcome(
            dispatch_id=record.dispatch_id,
            status="done",
            exit_code=0,
            raw_output="real output",
        )

        # -- Result file exists, no .tmp leftover
        result_files = list(tmp_path.glob("*.result.json"))
        assert len(result_files) == 1
        tmp_files = list(tmp_path.glob("*.tmp"))
        assert len(tmp_files) == 0, f"Atomic write leaked temp: {tmp_files}"

    def test_reconcile_stuck_intents(self, tmp_path) -> None:
        """RONDO-147 (Finding #213): reconcile_stuck_intents finds INTENT without OUTCOME."""
        from rondo.audit import AuditConfig, AuditTrail

        trail = AuditTrail(config=AuditConfig(audit_dir=str(tmp_path)))

        # -- Record one INTENT, complete its OUTCOME (normal flow)
        good = trail.record_intent(task_name="good", round_name="r", model="gemini-2.5-flash", prompt="ok")
        trail.record_outcome(dispatch_id=good.dispatch_id, status="done", exit_code=0)

        # -- Record an INTENT but never complete it (simulated crash)
        trail.record_intent(task_name="stuck", round_name="r", model="gemini-2.5-flash", prompt="crash")

        # -- Reconcile
        # -- RONDO-211 #257: stuck_after_sec=0 disables the in-flight age check
        # -- (this test simulates an already-crashed INTENT with no age delay)
        stuck_count = trail.reconcile_stuck_intents(stuck_after_sec=0)
        assert stuck_count == 1, f"Expected 1 stuck record, got {stuck_count}"

        # -- Second reconcile should find zero (already reconciled)
        stuck_count_again = trail.reconcile_stuck_intents(stuck_after_sec=0)
        assert stuck_count_again == 0, "Second reconcile should be no-op"


# -- sig: mgh-f917.e8.c44dff.d5db.2980df
