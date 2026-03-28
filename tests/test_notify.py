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


# -- sig: mgh-6201.cd.bd955f.e4a1.f1a2b3
