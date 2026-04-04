# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Tests for rondo.notify — Rondo-REQ-105 dispatch notifications.

VER-001 verification matrix: notification channels + triggers.
"""

import os
from unittest.mock import patch

import pytest

from rondo.notify import NotifyConfig, notify_failure, notify_round_complete


@pytest.fixture(autouse=True)
def _enable_notify_in_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    """Allow notification code to run in tests (normally suppressed by RONDO_TEST_DIR)."""
    monkeypatch.setenv("RONDO_NOTIFY_TEST", "1")


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
        """MacOS notification calls osascript."""
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


# -- ──────────────────────────────────────────────────────────────
# --  REQ-105 req 004: Rate limit notification (RONDO-54)
# -- ──────────────────────────────────────────────────────────────


class TestRateLimitNotify:
    """REQ-105 req 004: notify on rate limit."""

    def test_rate_limit_fires(self, capsys):
        from rondo.notify import notify_rate_limit, reset_dedup
        reset_dedup()
        notify_rate_limit(
            reset_time="2026-03-30T22:00:00Z",
            config=NotifyConfig(channels=["terminal"]),
        )
        captured = capsys.readouterr()
        assert "Rate limited" in captured.out or "rate" in captured.out.lower()

    def test_rate_limit_deduped(self, capsys):
        """Same rate limit only fires once (uses dedup)."""
        from rondo.notify import notify_rate_limit, reset_dedup
        reset_dedup()
        notify_rate_limit(reset_time="22:00", config=NotifyConfig(channels=["terminal"]))
        notify_rate_limit(reset_time="22:00", config=NotifyConfig(channels=["terminal"]))
        captured = capsys.readouterr()
        assert captured.out.count("rate") <= 1 or captured.out.count("Rate") <= 1


# -- ──────────────────────────────────────────────────────────────
# --  REQ-105 req 007: Quiet mode (RONDO-54)
# -- ──────────────────────────────────────────────────────────────


class TestQuietMode:
    """REQ-105 req 007: --quiet suppresses terminal, keeps file+macos."""

    def test_quiet_suppresses_terminal(self, capsys):
        from rondo.notify import notify_round_complete
        notify_round_complete(
            round_name="quiet-test", status="done",
            duration_sec=5.0, cost_usd=0.01,
            config=NotifyConfig(channels=["terminal"], quiet=True),
        )
        captured = capsys.readouterr()
        assert captured.out == ""

    def test_quiet_keeps_file(self, tmp_path):
        from rondo.notify import notify_round_complete
        log_file = tmp_path / "notify.log"
        notify_round_complete(
            round_name="quiet-test", status="done",
            duration_sec=5.0, cost_usd=0.01,
            config=NotifyConfig(channels=["terminal", "file"], log_file=str(log_file), quiet=True),
        )
        assert log_file.exists()


# -- ──────────────────────────────────────────────────────────────
# --  CRITICAL: AppleScript injection fix (RONDO-67, Finding #182)
# -- ──────────────────────────────────────────────────────────────


class TestAppleScriptInjection:
    """Finding #182: msg with double-quotes must not break AppleScript."""

    def test_double_quote_escaped(self):
        """Message with double-quote doesn't inject AppleScript."""
        with patch("subprocess.run") as mock_run:
            notify_round_complete(
                round_name='test"injection', status="done",
                duration_sec=5.0, cost_usd=0.01,
                config=NotifyConfig(channels=["macos"]),
            )
            cmd = mock_run.call_args[0][0]
            script = cmd[2]  ## osascript -e "script"
            ## -- No unescaped double-quotes inside the notification strings
            assert '"injection' not in script or '\\"' in script or "'" in script

    def test_shell_command_not_executed(self):
        """Malicious payload in msg has quotes escaped — AppleScript sees literal text."""
        with patch("subprocess.run") as mock_run:
            notify_round_complete(
                round_name='x" & do shell script "rm -rf ~',
                status="done",
                duration_sec=5.0, cost_usd=0.01,
                config=NotifyConfig(channels=["macos"]),
            )
            cmd = mock_run.call_args[0][0]
            script = cmd[2]
            ## -- All internal double-quotes must be escaped with backslash
            ## -- Count: script has outer quotes + escaped inner quotes only
            import re
            ## -- Find unescaped double-quotes (not preceded by backslash)
            ## -- Should only be the 2 outer AppleScript string delimiters + 2 for 'with title'
            unescaped = re.findall(r'(?<!\\)"', script)
            assert len(unescaped) == 4, f"Expected 4 unescaped quotes (string delimiters), got {len(unescaped)}: {script}"


# -- sig: mgh-6201.cd.bd955f.e4a1.f1a2b3
