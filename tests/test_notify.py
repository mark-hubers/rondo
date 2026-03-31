# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Tests for rondo.notify — Rondo-REQ-105 dispatch notifications.

VER-001 verification matrix: notification channels + triggers.
"""

from unittest.mock import patch


from rondo.notify import notify_round_complete, notify_failure, NotifyConfig


class TestNotifyRoundComplete:
    """Rondo-REQ-105 req 001: notify on round completion."""

    def test_terminal_notification(self, capsys):
        """Round complete prints to terminal."""
        notify_round_complete(
            round_name="test-round", status="done",
            duration_sec=12.5, cost_usd=0.03,
            config=NotifyConfig(channels=["terminal"]),
        )
        captured = capsys.readouterr()
        assert "test-round" in captured.out
        assert "done" in captured.out

    def test_file_notification(self, tmp_path):
        """Round complete writes to notification log."""
        log_file = tmp_path / "notifications.log"
        notify_round_complete(
            round_name="test-round", status="done",
            duration_sec=5.0, cost_usd=0.01,
            config=NotifyConfig(channels=["file"], log_file=str(log_file)),
        )
        assert log_file.exists()
        assert "test-round" in log_file.read_text()

    def test_macos_notification(self):
        """macOS notification calls osascript."""
        with patch("subprocess.run") as mock_run:
            notify_round_complete(
                round_name="test-round", status="done",
                duration_sec=5.0, cost_usd=0.01,
                config=NotifyConfig(channels=["macos"]),
            )
            mock_run.assert_called_once()
            cmd = mock_run.call_args[0][0]
            assert "osascript" in cmd[0]


class TestNotifyFailure:
    """Rondo-REQ-105 req 002: notify on dispatch failure."""

    def test_failure_notification(self, capsys):
        """Failure prints error details."""
        notify_failure(
            task_name="bad-task", error_code="ERR_AUTH",
            error_message="Invalid API key",
            config=NotifyConfig(channels=["terminal"]),
        )
        captured = capsys.readouterr()
        assert "bad-task" in captured.out
        assert "ERR_AUTH" in captured.out


class TestNotifyConfig:
    """Rondo-REQ-105 req 006: configurable channels."""

    def test_default_channels(self):
        c = NotifyConfig()
        assert "terminal" in c.channels

    def test_custom_channels(self):
        c = NotifyConfig(channels=["macos", "file"])
        assert "terminal" not in c.channels
        assert "macos" in c.channels


# -- ──────────────────────────────────────────────────────────────
# --  REQ-105 req 003: Budget threshold notifications (RONDO-51)
# -- ──────────────────────────────────────────────────────────────


class TestBudgetThreshold:
    """REQ-105 req 003: notify at 50%, 75%, 90% of budget."""

    def test_budget_75_fires(self, capsys):
        """Crossing 75% threshold fires notification."""
        from rondo.notify import notify_budget_threshold
        notify_budget_threshold(
            spent_usd=7.50, budget_usd=10.0,
            config=NotifyConfig(channels=["terminal"]),
        )
        captured = capsys.readouterr()
        assert "75%" in captured.out

    def test_budget_50_fires(self, capsys):
        """Crossing 50% threshold fires notification."""
        from rondo.notify import notify_budget_threshold
        notify_budget_threshold(
            spent_usd=5.0, budget_usd=10.0,
            config=NotifyConfig(channels=["terminal"]),
        )
        captured = capsys.readouterr()
        assert "50%" in captured.out

    def test_budget_under_50_no_fire(self, capsys):
        """Under 50% = no notification."""
        from rondo.notify import notify_budget_threshold
        notify_budget_threshold(
            spent_usd=3.0, budget_usd=10.0,
            config=NotifyConfig(channels=["terminal"]),
        )
        captured = capsys.readouterr()
        assert captured.out == ""


# -- ──────────────────────────────────────────────────────────────
# --  REQ-105 req 009: Deduplication (RONDO-51)
# -- ──────────────────────────────────────────────────────────────


class TestNotifyDedup:
    """REQ-105 req 009: don't spam same notification."""

    def test_dedup_blocks_repeat(self, capsys):
        """Same message twice = only one output."""
        from rondo.notify import notify_with_dedup, reset_dedup
        reset_dedup()
        notify_with_dedup(
            "rate_limited", "Rate limited",
            config=NotifyConfig(channels=["terminal"]),
        )
        notify_with_dedup(
            "rate_limited", "Rate limited",
            config=NotifyConfig(channels=["terminal"]),
        )
        captured = capsys.readouterr()
        assert captured.out.count("Rate limited") == 1

    def test_different_keys_both_fire(self, capsys):
        """Different dedup keys both fire."""
        from rondo.notify import notify_with_dedup, reset_dedup
        reset_dedup()
        notify_with_dedup(
            "rate_limited", "Rate limited",
            config=NotifyConfig(channels=["terminal"]),
        )
        notify_with_dedup(
            "budget_warning", "Budget high",
            config=NotifyConfig(channels=["terminal"]),
        )
        captured = capsys.readouterr()
        assert "Rate limited" in captured.out
        assert "Budget high" in captured.out


# -- sig: mgh-6201.cd.bd955f.e4a1.f1a2b3
