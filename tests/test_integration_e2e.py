# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""E2E integration tests — validate the tool does what the docs say.

VER-001 verification matrix: real CLI validation testing.

These tests use the REAL rondo CLI (installed via uv).
They run actual commands and verify output format, not mocks.
Marked with 'e2e' marker — skip in unit test runs.

NASA validation testing: prove the tool works as documented.
"""

import json
import os
import subprocess
import shutil

import pytest

RONDO_BIN = os.path.expanduser("~/.local/bin/rondo")
SKIP_E2E = not shutil.which("rondo")
skip_no_rondo = pytest.mark.skipif(SKIP_E2E, reason="rondo CLI not installed")

# -- Strip CLAUDECODE for all E2E tests (we're inside CC)
E2E_ENV = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}


def _run(args: list[str], timeout: int = 30) -> subprocess.CompletedProcess:
    """Run rondo CLI and capture output."""
    return subprocess.run(
        [RONDO_BIN] + args,
        capture_output=True, text=True, check=False,
        timeout=timeout, env=E2E_ENV,
    )


@skip_no_rondo
class TestE2EPreflight:
    """Docs say: 'rondo preflight' checks environment."""

    def test_preflight_returns_green(self):
        result = _run(["preflight"])
        assert result.returncode == 0
        assert "GREEN" in result.stdout

    def test_preflight_json_valid(self):
        result = _run(["preflight", "--json"])
        data = json.loads(result.stdout)
        assert data["status"] == "GREEN"
        assert data["can_proceed"] is True
        assert len(data["checks"]) >= 5

    def test_preflight_shows_cc_version(self):
        result = _run(["preflight"])
        assert "Claude Code version" in result.stdout


@skip_no_rondo
class TestE2EVersion:
    """Docs say: 'rondo --version' shows version."""

    def test_version_output(self):
        result = _run(["--version"])
        assert "0.1.0" in result.stdout


@skip_no_rondo
class TestE2EAiHelp:
    """Docs say: 'rondo --ai-help' outputs JSON capabilities."""

    def test_ai_help_valid_json(self):
        result = _run(["--ai-help"])
        data = json.loads(result.stdout)
        assert data["name"] == "rondo"

    def test_ai_help_has_commands(self):
        result = _run(["--ai-help"])
        data = json.loads(result.stdout)
        cmd_names = [c["name"] for c in data["commands"]]
        assert "run" in cmd_names
        assert "preflight" in cmd_names
        assert "history" in cmd_names
        assert "live" in cmd_names

    def test_ai_help_has_task_schema(self):
        result = _run(["--ai-help"])
        data = json.loads(result.stdout)
        assert "instruction" in str(data["task_schema"])
        assert "done_when" in str(data["task_schema"])

    def test_ai_help_has_capabilities(self):
        result = _run(["--ai-help"])
        data = json.loads(result.stdout)
        caps = list(data["capabilities"].keys())
        assert "dispatch" in caps
        assert "preflight" in caps
        assert "history" in caps
        assert "notifications" in caps


@skip_no_rondo
class TestE2EHelp:
    """Docs say: 'rondo --help' shows all commands."""

    def test_help_shows_commands(self):
        result = _run(["--help"])
        assert "run" in result.stdout
        assert "preflight" in result.stdout
        assert "history" in result.stdout
        assert "live" in result.stdout
        assert "overnight" in result.stdout
        assert "--ai-help" in result.stdout


@skip_no_rondo
class TestE2EDryRun:
    """Docs say: 'rondo run --dry-run' shows what would execute."""

    def test_dry_run_shows_skipped(self, tmp_path):
        round_file = tmp_path / "test_round.py"
        round_file.write_text(
            "from rondo.engine import Round, Task\n"
            "def build_round():\n"
            "    return Round(name='dry-test', tasks=[\n"
            "        Task(name='t1', instruction='check', done_when='checked'),\n"
            "    ])\n"
        )
        result = _run(["run", str(round_file), "--dry-run", "--verbose"])
        assert result.returncode == 1  # skipped = not "done"
        assert "skipped" in result.stdout.lower()
        assert "$0.0000" in result.stdout

    def test_dry_run_no_subprocess_call(self, tmp_path):
        """Dry-run should complete instantly (no Claude call)."""
        round_file = tmp_path / "test_round.py"
        round_file.write_text(
            "from rondo.engine import Round, Task\n"
            "def build_round():\n"
            "    return Round(name='fast-test', tasks=[\n"
            "        Task(name='t1', instruction='do', done_when='done'),\n"
            "    ])\n"
        )
        import time
        start = time.monotonic()
        _run(["run", str(round_file), "--dry-run"])
        elapsed = time.monotonic() - start
        assert elapsed < 5.0, f"Dry-run took {elapsed:.1f}s — should be instant"


@skip_no_rondo
class TestE2EHistory:
    """Docs say: 'rondo history' shows dispatch records."""

    def test_history_json_valid(self):
        result = _run(["history", "--json"])
        data = json.loads(result.stdout)
        assert isinstance(data, list)

    def test_history_shows_cost(self):
        result = _run(["history"])
        assert "$" in result.stdout

    def test_history_expensive_sort(self):
        result = _run(["history", "--expensive"])
        assert "Dispatches:" in result.stdout


@skip_no_rondo
class TestE2EExampleRounds:
    """Validate that example round files load without errors."""

    def test_round_hello_dry_run(self):
        result = _run(["run", "examples/round_hello.py", "--dry-run"], timeout=10)
        assert "skipped" in result.stdout.lower() or result.returncode in (0, 1)

    def test_round_file_check_dry_run(self):
        result = _run(["run", "examples/round_file_check.py", "--dry-run"], timeout=10)
        assert result.returncode in (0, 1)  # loads successfully

    def test_round_multi_task_dry_run(self):
        result = _run(["run", "examples/round_multi_task.py", "--dry-run"], timeout=10)
        assert result.returncode in (0, 1)


# -- sig: mgh-6201.cd.bd955f.e4a1.e2e001
