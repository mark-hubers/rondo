# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Tests for the nightly watchdog — RONDO-314 (finding #285 residual).

The campaign's top weakness: drift/retryq/metrics existed but NOBODY WAS
WATCHING. run_nightly_check() composes all three into one schedulable
sweep that alerts on FAILURE/STALE instead of waiting to be asked.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from rondo.nightly import (
    RELIABILITY_FLOOR,
    RELIABILITY_MIN_VOLUME,
    NightlyReport,
    run_nightly_check,
)


def _green_seams(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """Patch every data seam to a healthy state; return the notify spy log."""
    sent: list[list[str]] = []
    monkeypatch.setattr(
        "rondo.nightly._gather_drift",
        lambda refresh: [{"provider": "gemini", "model": "gemini-flash-latest", "state": "OK"}],
    )
    monkeypatch.setattr(
        "rondo.nightly._sweep_retryq",
        lambda: {"dead_lettered": 0, "remaining": 0, "queue_alert": None},
    )
    monkeypatch.setattr(
        "rondo.nightly._compute_reliability",
        lambda: {"success_rate_7d": 0.98, "dispatches_7d": 50},
    )
    monkeypatch.setattr("rondo.nightly.notify_watchdog", lambda alerts, title="": sent.append(alerts))
    return sent


class TestNightlyAllGreen:
    """Healthy fleet → OK status, zero alerts, zero notifications."""

    def test_status_ok_and_no_alerts(self, monkeypatch: pytest.MonkeyPatch) -> None:
        sent = _green_seams(monkeypatch)
        report = run_nightly_check(refresh=False)
        assert report.status == "OK"
        assert report.alerts == []
        assert sent == []

    def test_report_is_json_safe(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _green_seams(monkeypatch)
        report = run_nightly_check(refresh=False)
        blob = json.dumps(report.to_dict())
        assert '"status": "OK"' in blob


class TestNightlyAlerts:
    """Each subsystem failure surfaces as a named alert + notification."""

    def test_stale_model_alerts(self, monkeypatch: pytest.MonkeyPatch) -> None:
        sent = _green_seams(monkeypatch)
        monkeypatch.setattr(
            "rondo.nightly._gather_drift",
            lambda refresh: [{"provider": "grok", "model": "grok-3", "state": "STALE"}],
        )
        report = run_nightly_check(refresh=False)
        assert report.status == "ALERT"
        assert any("grok-3" in a and "STALE" in a for a in report.alerts)
        assert len(sent) == 1

    def test_drift_alert_uses_real_drift_report_shape(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """UNMOCKED drift shape — guards against key drift vs drift_report.

        The seam mocks once carried a fictional "status" key while the real
        entries carry "state"; STALE models would NEVER have alerted. This
        test feeds REAL drift_report output through the alert filter.
        """
        from rondo.model_registry import drift_report

        cache = {"providers": {"grok": {"models": ["grok-4.3"], "error": ""}}}
        cfg = {"grok": {"enabled": True, "default_model": "grok-3"}}
        entries = drift_report(cache, cfg)
        assert any(e["state"] == "STALE" for e in entries)  # -- shape sanity
        monkeypatch.setattr("rondo.nightly._gather_drift", lambda refresh: entries)
        report = run_nightly_check(refresh=False, notify_alerts=False)
        assert report.status == "ALERT"
        assert any("grok-3" in a and "STALE" in a for a in report.alerts)

    def test_no_cache_alerts(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _green_seams(monkeypatch)
        monkeypatch.setattr(
            "rondo.nightly._gather_drift",
            lambda refresh: [{"provider": "openai", "model": "gpt-5.5", "state": "NO_CACHE"}],
        )
        report = run_nightly_check(refresh=False)
        assert report.status == "ALERT"
        assert any("NO_CACHE" in a for a in report.alerts)

    def test_low_reliability_alerts(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _green_seams(monkeypatch)
        monkeypatch.setattr(
            "rondo.nightly._compute_reliability",
            lambda: {"success_rate_7d": 0.80, "dispatches_7d": RELIABILITY_MIN_VOLUME},
        )
        report = run_nightly_check(refresh=False)
        assert report.status == "ALERT"
        assert any("80" in a for a in report.alerts)

    def test_low_volume_skips_reliability_alert(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """3 dispatches at 50% is noise, not signal — no alert below the floor."""
        _green_seams(monkeypatch)
        monkeypatch.setattr(
            "rondo.nightly._compute_reliability",
            lambda: {"success_rate_7d": 0.50, "dispatches_7d": RELIABILITY_MIN_VOLUME - 1},
        )
        report = run_nightly_check(refresh=False)
        assert report.status == "OK"

    def test_empty_window_never_fakes_health(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """success_rate_7d=None (no dispatches) → no reliability alert, noted in report."""
        _green_seams(monkeypatch)
        monkeypatch.setattr(
            "rondo.nightly._compute_reliability",
            lambda: {"success_rate_7d": None, "dispatches_7d": 0},
        )
        report = run_nightly_check(refresh=False)
        assert report.status == "OK"
        assert report.success_rate_7d is None

    def test_queue_alert_passes_through(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _green_seams(monkeypatch)
        monkeypatch.setattr(
            "rondo.nightly._sweep_retryq",
            lambda: {
                "dead_lettered": 3,
                "remaining": 25,
                "queue_alert": "retry queue depth 25 exceeds threshold 20",
            },
        )
        report = run_nightly_check(refresh=False)
        assert report.status == "ALERT"
        assert any("depth 25" in a for a in report.alerts)

    def test_real_sweep_seam_matches_sweepreport_fields(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """UNMOCKED seam run — guards against field drift vs SweepReport.

        The seam mocks above hid a real bug once (seam used .swept which
        SweepReport never had). This test runs the REAL _sweep_retryq against
        a real queue dir so a field rename breaks loudly here, not at 3am.
        """
        from rondo.nightly import _sweep_retryq

        monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))
        result = _sweep_retryq()
        assert set(result) == {"dead_lettered", "remaining", "queue_alert"}
        assert result["remaining"] == 0
        assert result["queue_alert"] is None

    def test_no_notify_flag_suppresses_notification(self, monkeypatch: pytest.MonkeyPatch) -> None:
        sent = _green_seams(monkeypatch)
        monkeypatch.setattr(
            "rondo.nightly._gather_drift",
            lambda refresh: [{"provider": "grok", "model": "grok-3", "state": "STALE"}],
        )
        report = run_nightly_check(refresh=False, notify_alerts=False)
        assert report.status == "ALERT"
        assert sent == []

    def test_subsystem_crash_becomes_alert_not_crash(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A watchdog that dies when a subsystem dies is no watchdog at all."""
        _green_seams(monkeypatch)

        def _boom(refresh: bool) -> list[dict[str, str]]:
            raise OSError("network down")

        monkeypatch.setattr("rondo.nightly._gather_drift", _boom)
        report = run_nightly_check(refresh=False)
        assert report.status == "ALERT"
        assert any("drift check failed" in a for a in report.alerts)


class TestNightlyConstants:
    """The 95% target is the campaign's stated goal — lock it."""

    def test_reliability_floor_is_95(self) -> None:
        assert RELIABILITY_FLOOR == 0.95

    def test_report_dataclass_defaults(self) -> None:
        report = NightlyReport()
        assert report.status == "OK"
        assert report.alerts == []
