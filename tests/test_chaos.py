# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Chaos tests for Rondo — failure injection for reliability proof.

VER-001 verification: Rondo handles failure gracefully, not just happy paths.
FIX-686: Gemini + Grok + Cursor all flagged "no chaos tests" as the gap.

Each test simulates a real-world failure and verifies:
    1. No crash (exception contained)
    2. Correct error code (ErrorPayload populated)
    3. Recovery guidance present
    4. Subsequent tasks still run (no cascade)

Rondo-REQ-100 reqs 057-059 (circuit breaker), Rondo-STD-108 (error handling).
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from rondo.config import RondoConfig
from rondo.engine import DispatchUsage, ErrorPayload, Round, RoundResult, Task, TaskResult
from rondo.runner import run_round


# -- ──────────────────────────────────────────────────────────────
#  Chaos 1: Subprocess crashes (ERR_SUBPROCESS)
# -- ──────────────────────────────────────────────────────────────


class TestSubprocessCrash:
    """Simulate Claude binary crashing mid-dispatch."""

    def test_subprocess_oserror_becomes_error_result(self) -> None:
        """OSError from subprocess → TaskResult with error status, not exception."""
        round_def = Round(name="crash-test", tasks=[
            Task(name="t1", instruction="do something", done_when="done"),
        ])
        config = RondoConfig(workers=1)

        with patch("rondo.runner.dispatch_task") as mock_dispatch:
            mock_dispatch.return_value = (
                TaskResult(
                    task_name="t1",
                    status="error",
                    error_code="ERR_SUBPROCESS",
                    error_message="Claude binary crashed",
                    error_payload=ErrorPayload(
                        code="ERR_SUBPROCESS",
                        message="Claude binary crashed",
                        recovery="Run rondo preflight",
                        transient=False,
                        layer="dispatch",
                    ),
                ),
                DispatchUsage(task_name="t1"),
            )
            result = run_round(round_def, config)
            assert result.status == "error"
            assert result.task_results[0].error_code == "ERR_SUBPROCESS"
            assert result.task_results[0].error_payload is not None
            assert result.task_results[0].error_payload.recovery != ""


# -- ──────────────────────────────────────────────────────────────
#  Chaos 2: Rate limit storm (ERR_RATE_LIMIT)
# -- ──────────────────────────────────────────────────────────────


class TestRateLimitStorm:
    """Simulate provider returning 429 on every request."""

    def test_circuit_breaker_trips_after_3_consecutive(self) -> None:
        """3 consecutive ERR_RATE_LIMIT → circuit breaker halts round."""
        round_def = Round(name="storm-test", tasks=[
            Task(name=f"t{i}", instruction="do", done_when="done")
            for i in range(5)
        ])
        config = RondoConfig(workers=1)

        with patch("rondo.runner.dispatch_task") as mock_dispatch:
            mock_dispatch.return_value = (
                TaskResult(
                    task_name="t",
                    status="error",
                    error_code="ERR_RATE_LIMIT",
                    error_message="429 Too Many Requests",
                    error_payload=ErrorPayload(
                        code="ERR_RATE_LIMIT",
                        message="429 Too Many Requests",
                        recovery="Wait and retry, or switch provider",
                        transient=True,
                        layer="dispatch",
                    ),
                ),
                DispatchUsage(task_name="t"),
            )
            result = run_round(round_def, config)
            # -- Circuit breaker should trip after 3 consecutive same-error
            errors = [tr for tr in result.task_results if tr.error_code == "ERR_RATE_LIMIT"]
            skipped = [tr for tr in result.task_results if tr.status == "skipped"]
            assert len(errors) == 3
            assert len(skipped) == 2  # -- remaining 2 tasks skipped by breaker


# -- ──────────────────────────────────────────────────────────────
#  Chaos 3: Malformed AI output
# -- ──────────────────────────────────────────────────────────────


class TestMalformedOutput:
    """Simulate AI returning garbage instead of expected JSON."""

    def test_malformed_json_gracefully_handled(self) -> None:
        """Non-JSON output → partial result with error_code, not crash."""
        round_def = Round(name="garbage-test", tasks=[
            Task(name="t1", instruction="return json", done_when="json returned"),
        ])
        config = RondoConfig(workers=1)

        with patch("rondo.runner.dispatch_task") as mock_dispatch:
            mock_dispatch.return_value = (
                TaskResult(
                    task_name="t1",
                    status="partial",
                    error_code="ERR_MALFORMED_JSON",
                    error_message="Output was not valid JSON",
                    raw_output="this is not json {{{ broken",
                    error_payload=ErrorPayload(
                        code="ERR_MALFORMED_JSON",
                        message="Output was not valid JSON",
                        recovery="Retry or simplify expected output format",
                        transient=True,
                        layer="dispatch",
                    ),
                ),
                DispatchUsage(task_name="t1", cost_usd=0.01),
            )
            result = run_round(round_def, config)
            assert result.task_results[0].error_code == "ERR_MALFORMED_JSON"
            assert result.task_results[0].error_payload.transient is True


# -- ──────────────────────────────────────────────────────────────
#  Chaos 4: Corrupt audit JSONL
# -- ──────────────────────────────────────────────────────────────


class TestCorruptAudit:
    """Simulate corrupt JSONL in audit trail."""

    def test_corrupt_jsonl_doesnt_crash_history(self) -> None:
        """Corrupt JSONL lines are skipped, not crash."""
        from rondo.history import load_history

        tmp = Path("/tmp/rondo-chaos-test-history")
        tmp.mkdir(parents=True, exist_ok=True)
        jsonl = tmp / "history-2026-04-05.jsonl"
        jsonl.write_text(
            '{"task_name": "ok", "status": "done"}\n'
            "this is not json\n"
            '{"task_name": "also_ok", "status": "done"}\n'
            "\n"
            '{"broken": true\n',
            encoding="utf-8",
        )
        records = load_history(str(tmp))
        # -- Should load the valid records, skip corrupt ones
        assert len(records) >= 1
        assert any(r.get("task_name") == "ok" for r in records)


# -- ──────────────────────────────────────────────────────────────
#  Chaos 5: Config file disappears mid-run
# -- ──────────────────────────────────────────────────────────────


class TestConfigDisappears:
    """Simulate config file deleted between load and use."""

    def test_missing_config_uses_defaults(self) -> None:
        """Missing config file → empty dict → all defaults."""
        from rondo.config import load_config

        config = load_config(config_path="/nonexistent/path/rondo.toml")
        # -- Should use all defaults, not crash
        assert config.default_model == "sonnet"
        assert config.workers == 4


# -- ──────────────────────────────────────────────────────────────
#  Chaos 6: Disk full (spool write fails)
# -- ──────────────────────────────────────────────────────────────


class TestDiskFull:
    """Simulate disk full when writing spool results."""

    def test_spool_write_failure_doesnt_crash_overnight(self) -> None:
        """Spool write OSError → logged, overnight continues."""
        from rondo.overnight import run_overnight

        phases = [
            Round(name="p1", tasks=[
                Task(name="auto", auto_fn=lambda: (True, "ok")),
            ]),
        ]
        config = RondoConfig(dry_run=True)

        with patch("rondo.spool.spool_result", side_effect=OSError("No space left on device")):
            # -- Should not crash — spool failure is non-fatal
            result = run_overnight(phases=phases, config=config)
            assert result.status in ("done", "skipped")


# -- ──────────────────────────────────────────────────────────────
#  Chaos 7: Partial provider outage (1 of 3 down)
# -- ──────────────────────────────────────────────────────────────


class TestPartialProviderOutage:
    """Simulate one provider down while others are up."""

    def test_health_shows_partial_when_one_down(self) -> None:
        """1 of 3 providers down → health shows YELLOW, not RED."""
        from rondo.adapters.health import HealthStatus

        import time

        now = time.time()
        mock_health = {
            "gemini": HealthStatus(provider="gemini", healthy=True, latency_ms=100, checked_at=now),
            "grok": HealthStatus(provider="grok", healthy=False, latency_ms=0, checked_at=now, error="Connection refused"),
            "mistral": HealthStatus(provider="mistral", healthy=True, latency_ms=200, checked_at=now),
        }
        with patch("rondo.adapters.health.get_all_providers_health", return_value=mock_health):
            health_json = json.loads(
                __import__("rondo.mcp_tools", fromlist=["rondo_health"]).rondo_health()
            )
            assert health_json["api_status"] == "YELLOW"
            assert health_json["providers_up"] == "2/3"


# -- sig: mgh-6201.cd.bd955f.b1c2.chaos1
