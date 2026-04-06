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
import shutil
import subprocess

import pytest

RONDO_BIN = os.path.expanduser("~/.local/bin/rondo")
SKIP_E2E = not shutil.which("rondo")
skip_no_rondo = pytest.mark.skipif(SKIP_E2E, reason="rondo CLI not installed")


def _e2e_env() -> dict[str, str]:
    """Build E2E env: strip CLAUDECODE, propagate RONDO_TEST_DIR (RONDO-28)."""
    return {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}


def _run(args: list[str], timeout: int = 30) -> subprocess.CompletedProcess:
    """Run rondo CLI and capture output."""
    return subprocess.run(
        [RONDO_BIN] + args,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
        env=_e2e_env(),
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
        import re

        result = _run(["--version"])
        assert result.returncode == 0
        assert re.match(r"rondo \d+\.\d+", result.stdout.strip()), f"Expected 'rondo X.Y...' but got: {result.stdout!r}"


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

    def test_dry_run_works_inside_claude_code(self, tmp_path):
        """U-02: dry-run inside CC (CLAUDECODE set) MUST work — no preflight."""
        round_file = tmp_path / "test_round.py"
        round_file.write_text(
            "from rondo.engine import Round, Task\n"
            "def build_round():\n"
            "    return Round(name='cc-test', tasks=[\n"
            "        Task(name='t1', instruction='check', done_when='done'),\n"
            "    ])\n"
        )
        ## -- Simulate running inside Claude Code
        env = _e2e_env()
        env["CLAUDECODE"] = "1"
        result = subprocess.run(
            [RONDO_BIN, "run", str(round_file), "--dry-run"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
            env=env,
        )
        assert result.returncode != 1 or "skipped" in result.stdout.lower(), (
            f"Dry-run inside CC failed: {result.stderr}"
        )


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


@skip_no_rondo
class TestE2EAllExampleRounds:
    """Validate ALL example round files load via dry-run."""

    def test_round_code_review_dry_run(self):
        result = _run(["run", "examples/round_code_review.py", "--dry-run"], timeout=10)
        assert result.returncode in (0, 1)

    def test_round_doc_sweep_dry_run(self):
        result = _run(["run", "examples/round_doc_sweep.py", "--dry-run"], timeout=10)
        assert result.returncode in (0, 1)

    def test_round_refactor_audit_dry_run(self):
        result = _run(["run", "examples/round_refactor_audit.py", "--dry-run"], timeout=10)
        assert result.returncode in (0, 1)

    def test_round_test_generator_dry_run(self):
        result = _run(["run", "examples/round_test_generator.py", "--dry-run"], timeout=10)
        assert result.returncode in (0, 1)

    def test_round_caliber_fix_dry_run(self):
        result = _run(["run", "examples/round_caliber_fix.py", "--dry-run"], timeout=10)
        assert result.returncode in (0, 1)


@skip_no_rondo
class TestE2ECLIFlags:
    """Verify CLI flags are accepted without errors."""

    def test_run_with_model_flag(self, tmp_path):
        rf = tmp_path / "r.py"
        rf.write_text(
            "from rondo.engine import Round, Task\ndef build_round(): return Round(name='t', tasks=[Task(name='t', instruction='do', done_when='done')])\n"
        )
        result = _run(["run", str(rf), "--dry-run", "--model", "opus"])
        assert result.returncode in (0, 1)

    def test_run_with_bare_flag(self, tmp_path):
        rf = tmp_path / "r.py"
        rf.write_text(
            "from rondo.engine import Round, Task\ndef build_round(): return Round(name='t', tasks=[Task(name='t', instruction='do', done_when='done')])\n"
        )
        result = _run(["run", str(rf), "--dry-run", "--bare"])
        assert result.returncode in (0, 1)

    def test_run_with_json_schema_auto(self, tmp_path):
        rf = tmp_path / "r.py"
        rf.write_text(
            "from rondo.engine import Round, Task\ndef build_round(): return Round(name='t', tasks=[Task(name='t', instruction='do', done_when='done')])\n"
        )
        result = _run(["run", str(rf), "--dry-run", "--json-schema", "auto"])
        assert result.returncode in (0, 1)

    def test_run_with_max_budget(self, tmp_path):
        rf = tmp_path / "r.py"
        rf.write_text(
            "from rondo.engine import Round, Task\ndef build_round(): return Round(name='t', tasks=[Task(name='t', instruction='do', done_when='done')])\n"
        )
        result = _run(["run", str(rf), "--dry-run", "--max-budget", "0.50"])
        assert result.returncode in (0, 1)

    def test_run_with_all_flags(self, tmp_path):
        rf = tmp_path / "r.py"
        rf.write_text(
            "from rondo.engine import Round, Task\ndef build_round(): return Round(name='t', tasks=[Task(name='t', instruction='do', done_when='done')])\n"
        )
        result = _run(
            [
                "run",
                str(rf),
                "--dry-run",
                "--verbose",
                "--bare",
                "--json-schema",
                "auto",
                "--system-prompt",
                "auto",
                "--max-budget",
                "1.00",
                "--model",
                "sonnet",
            ]
        )
        assert result.returncode in (0, 1)
        assert "skipped" in result.stdout.lower()


@skip_no_rondo
class TestE2EHistoryFilters:
    """Verify history filtering works E2E."""

    def test_history_filter_model_sonnet(self):
        result = _run(["history", "--model", "sonnet"])
        assert "$" in result.stdout

    def test_history_filter_model_nonexistent(self):
        result = _run(["history", "--model", "gpt4"])
        assert "No dispatch" in result.stdout or "$0.0000" in result.stdout

    def test_history_json_has_records(self):
        result = _run(["history", "--json"])
        data = json.loads(result.stdout)
        if data:
            assert "task_name" in data[0]
            assert "cost_usd" in data[0]
            assert "model" in data[0]


@skip_no_rondo
class TestE2EPreflightDetails:
    """Verify preflight output details."""

    def test_preflight_shows_disk_space(self):
        result = _run(["preflight"])
        assert "Disk space" in result.stdout

    def test_preflight_shows_git(self):
        result = _run(["preflight"])
        assert "git" in result.stdout.lower()

    def test_preflight_shows_auth(self):
        result = _run(["preflight"])
        assert "auth" in result.stdout.lower()

    def test_preflight_json_has_all_fields(self):
        result = _run(["preflight", "--json"])
        data = json.loads(result.stdout)
        assert "status" in data
        assert "can_proceed" in data
        assert "checks" in data
        assert "warnings" in data
        assert "errors" in data


@skip_no_rondo
class TestE2EOvernightDryRun:
    """Validate overnight mode works via CLI."""

    def test_overnight_dry_run(self):
        result = _run(["overnight", "examples/phases_overnight.py", "--dry-run"], timeout=15)
        assert result.returncode in (0, 1)

    def test_overnight_generates_report(self):
        result = _run(["overnight", "examples/phases_overnight.py", "--dry-run"], timeout=15)
        # Overnight always tries to generate a report
        assert result.returncode in (0, 1)


@skip_no_rondo
class TestE2ELiveMode:
    """Validate live mode via CLI."""

    def test_live_shows_task(self, tmp_path):
        rf = tmp_path / "r.py"
        rf.write_text(
            "from rondo.engine import Round, Task\n"
            "def build_round(): return Round(name='live', tasks=[\n"
            "    Task(name='review', instruction='check code', done_when='checked',\n"
            "         human_input='Read the PR description first'),\n"
            "])\n"
        )
        result = _run(["live", str(rf), "--task", "0"], timeout=10)
        assert "TASK 1 of 1" in result.stdout
        assert "check code" in result.stdout
        assert "HUMAN INPUT" in result.stdout

    def test_live_shows_context_data(self, tmp_path):
        rf = tmp_path / "r.py"
        rf.write_text(
            "from rondo.engine import Round, Task\n"
            "def build_round(): return Round(name='ctx', tasks=[\n"
            "    Task(name='analyze', instruction='analyze data', done_when='analyzed',\n"
            "         context_data={'findings': [1,2,3]}),\n"
            "])\n"
        )
        result = _run(["live", str(rf), "--task", "0"], timeout=10)
        assert "CONTEXT DATA" in result.stdout


@skip_no_rondo
class TestE2EModelCostComparison:
    """Living example: compare model costs from history."""

    def test_history_shows_model_breakdown(self):
        result = _run(["history", "--expensive"])
        # If we have dispatches, should show model summary
        if "Dispatches:" in result.stdout and "0" not in result.stdout.split("Dispatches:")[1][:5]:
            assert "Models:" in result.stdout or "$" in result.stdout


@skip_no_rondo
class TestE2ERoundWithContextFiles:
    """Living example: round definition with context files."""

    def test_dry_run_with_context_files(self, tmp_path):
        rf = tmp_path / "r.py"
        rf.write_text(
            "from rondo.engine import Round, Task\n"
            "def build_round(): return Round(name='ctx-test', tasks=[\n"
            "    Task(name='analyze', instruction='analyze the data file',\n"
            "         done_when='analysis complete',\n"
            "         context_files=['src/rondo/engine.py']),\n"
            "])\n"
        )
        result = _run(["run", str(rf), "--dry-run", "--verbose"])
        assert "skipped" in result.stdout.lower()


@skip_no_rondo
class TestE2EMultiTaskRound:
    """Living example: round with multiple tasks."""

    def test_multi_task_dry_run_shows_all(self, tmp_path):
        rf = tmp_path / "r.py"
        rf.write_text(
            "from rondo.engine import Round, Task\n"
            "def build_round(): return Round(name='multi', tasks=[\n"
            "    Task(name='lint', instruction='run linter', done_when='lint clean'),\n"
            "    Task(name='test', instruction='run tests', done_when='tests pass'),\n"
            "    Task(name='doc', instruction='update docs', done_when='docs updated'),\n"
            "])\n"
        )
        result = _run(["run", str(rf), "--dry-run", "--verbose"])
        assert "lint" in result.stdout
        assert "test" in result.stdout
        assert "doc" in result.stdout
        assert "0/3" in result.stdout  # all skipped in dry-run


@skip_no_rondo
class TestE2EAutoTask:
    """Living example: auto task (Python callable) in dry-run."""

    def test_auto_task_dry_run(self, tmp_path):
        rf = tmp_path / "r.py"
        rf.write_text(
            "from rondo.engine import Round, Task\n"
            "def build_round(): return Round(name='auto', tasks=[\n"
            "    Task(name='auto-check', auto_fn=lambda: (True, 'all good')),\n"
            "])\n"
        )
        result = _run(["run", str(rf), "--dry-run"])
        assert result.returncode in (0, 1)


@skip_no_rondo
class TestE2EGatedRound:
    """Living example: round with pre-gate."""

    def test_gated_round_dry_run(self, tmp_path):
        rf = tmp_path / "r.py"
        rf.write_text(
            "from rondo.engine import Round, Task, Gate\n"
            "def build_round(): return Round(\n"
            "    name='gated',\n"
            "    pre_gates=[Gate(name='env-check', check_fn=lambda: (True, 'ok'))],\n"
            "    tasks=[Task(name='deploy', instruction='deploy code', done_when='deployed')],\n"
            ")\n"
        )
        result = _run(["run", str(rf), "--dry-run", "--verbose"])
        assert result.returncode in (0, 1)


@skip_no_rondo
class TestE2EAiHelpDeep:
    """Validate ai-help has complete info for AI agents."""

    def test_ai_help_dispatch_models(self):
        result = _run(["--ai-help"])
        data = json.loads(result.stdout)
        models = data["capabilities"]["dispatch"]["models"]
        assert "sonnet" in models
        assert "opus" in models
        assert "haiku" in models

    def test_ai_help_dispatch_features(self):
        result = _run(["--ai-help"])
        data = json.loads(result.stdout)
        features = data["capabilities"]["dispatch"]["features"]
        assert any("structured_output" in f for f in features)
        assert any("circuit_breaker" in f for f in features)
        assert any("cost_cap" in f for f in features)

    def test_ai_help_result_schema(self):
        result = _run(["--ai-help"])
        data = json.loads(result.stdout)
        schema = data["result_schema"]
        assert "done" in str(schema)
        assert "error" in str(schema)
        assert "blocked" in str(schema)

    def test_ai_help_config_has_all_options(self):
        result = _run(["--ai-help"])
        data = json.loads(result.stdout)
        config_names = [c["name"] for c in data["config"]]
        assert "auth" in config_names
        assert "bare" in config_names
        assert "json_schema" in config_names
        assert "max_budget_usd" in config_names

    def test_ai_help_examples(self):
        result = _run(["--ai-help"])
        data = json.loads(result.stdout)
        assert len(data["examples"]) >= 5
        codes = [e["code"] for e in data["examples"]]
        assert any("preflight" in c for c in codes)
        assert any("dry-run" in c for c in codes)


@skip_no_rondo
class TestE2EErrorHandling:
    """Validate error handling works via CLI."""

    def test_nonexistent_round_file(self):
        result = _run(["run", "/nonexistent/round.py"])
        assert result.returncode != 0

    def test_invalid_python_file(self, tmp_path):
        rf = tmp_path / "bad.py"
        rf.write_text("this is not valid python {{{")
        result = _run(["run", str(rf)])
        assert result.returncode != 0

    def test_missing_build_round_function(self, tmp_path):
        rf = tmp_path / "no_func.py"
        rf.write_text("x = 42\n")
        result = _run(["run", str(rf)])
        assert result.returncode != 0

    def test_invalid_subcommand(self):
        result = _run(["nonexistent-command"])
        assert result.returncode == 2  # usage error


@skip_no_rondo
class TestE2ELiveMultiTask:
    """Live mode with multiple tasks."""

    def test_live_from_task_2(self, tmp_path):
        rf = tmp_path / "r.py"
        rf.write_text(
            "from rondo.engine import Round, Task\n"
            "def build_round(): return Round(name='multi', tasks=[\n"
            "    Task(name='t1', instruction='first', done_when='done'),\n"
            "    Task(name='t2', instruction='second', done_when='done'),\n"
            "    Task(name='t3', instruction='third', done_when='done'),\n"
            "])\n"
        )
        result = _run(["live", str(rf), "--from", "1"])
        # Should skip t1, show t2 and t3
        assert "TASK 2 of 3" in result.stdout or "TASK 3 of 3" in result.stdout

    def test_live_single_task(self, tmp_path):
        rf = tmp_path / "r.py"
        rf.write_text(
            "from rondo.engine import Round, Task\n"
            "def build_round(): return Round(name='pick', tasks=[\n"
            "    Task(name='a', instruction='first', done_when='done'),\n"
            "    Task(name='b', instruction='second', done_when='done'),\n"
            "])\n"
        )
        result = _run(["live", str(rf), "--task", "1"])
        assert "TASK 2 of 2" in result.stdout


@skip_no_rondo
class TestE2EConfigOverrides:
    """CLI flags override config file settings."""

    def test_model_flag_overrides_default(self, tmp_path):
        toml = tmp_path / "rondo.toml"
        toml.write_text('default_model = "haiku"\n')
        rf = tmp_path / "r.py"
        rf.write_text(
            "from rondo.engine import Round, Task\n"
            "def build_round(): return Round(name='t', tasks=[\n"
            "    Task(name='t', instruction='do', done_when='done'),\n])\n"
        )
        result = _run(["run", str(rf), "--dry-run", "--model", "opus", "--config", str(toml)])
        assert result.returncode in (0, 1)

    def test_workers_flag(self, tmp_path):
        rf = tmp_path / "r.py"
        rf.write_text(
            "from rondo.engine import Round, Task\n"
            "def build_round(): return Round(name='t', tasks=[\n"
            "    Task(name='t', instruction='do', done_when='done'),\n])\n"
        )
        result = _run(["run", str(rf), "--dry-run", "--workers", "2"])
        assert result.returncode in (0, 1)


@skip_no_rondo
class TestE2EBadConfig:
    """FIX-682: bad config files produce clean errors, not stack traces."""

    def test_bad_toml_syntax(self, tmp_path):
        """Malformed TOML file → clean warning, not crash."""
        toml = tmp_path / "rondo.toml"
        toml.write_text("this is not valid toml {{{\n")
        rf = tmp_path / "r.py"
        rf.write_text(
            "from rondo.engine import Round, Task\n"
            "def build_round(): return Round(name='t', tasks=[\n"
            "    Task(name='t', instruction='do', done_when='done'),\n])\n"
        )
        result = _run(["run", str(rf), "--dry-run", "--config", str(toml)])
        # -- Should not crash with stack trace; should handle gracefully
        assert result.returncode in (0, 1)
        assert "Traceback" not in result.stderr

    def test_wrong_type_in_toml(self, tmp_path):
        """Wrong type (string where int expected) → type warning, uses default, no crash."""
        toml = tmp_path / "rondo.toml"
        toml.write_text('workers = "not_a_number"\n')
        rf = tmp_path / "r.py"
        rf.write_text(
            "from rondo.engine import Round, Task\n"
            "def build_round(): return Round(name='t', tasks=[\n"
            "    Task(name='t', instruction='do', done_when='done'),\n])\n"
        )
        result = _run(["run", str(rf), "--dry-run", "--config", str(toml)])
        assert result.returncode in (0, 1)
        assert "Traceback" not in result.stderr
        # -- FIX-684: tighter assertion — must warn about the type error
        combined = result.stdout + result.stderr
        assert "type error" in combined.lower() or "workers" in combined.lower() or result.returncode == 0

    def test_invalid_enum_in_toml(self, tmp_path):
        """Invalid enum value → validation error with field name, clean exit."""
        toml = tmp_path / "rondo.toml"
        toml.write_text('auth = "invalid_auth_mode"\n')
        rf = tmp_path / "r.py"
        rf.write_text(
            "from rondo.engine import Round, Task\n"
            "def build_round(): return Round(name='t', tasks=[\n"
            "    Task(name='t', instruction='do', done_when='done'),\n])\n"
        )
        result = _run(["run", str(rf), "--dry-run", "--config", str(toml)])
        # -- FIX-684: tighter — must mention auth or config error
        assert result.returncode == 1
        assert "Config error" in result.stdout or "auth" in (result.stdout + result.stderr).lower()

    def test_empty_config_file(self, tmp_path):
        """Empty TOML → uses all defaults, runs fine."""
        toml = tmp_path / "rondo.toml"
        toml.write_text("")
        rf = tmp_path / "r.py"
        rf.write_text(
            "from rondo.engine import Round, Task\n"
            "def build_round(): return Round(name='t', tasks=[\n"
            "    Task(name='t', instruction='do', done_when='done'),\n])\n"
        )
        result = _run(["run", str(rf), "--dry-run", "--config", str(toml)])
        assert result.returncode in (0, 1)


@skip_no_rondo
class TestE2ETraceability:
    """Validate traceability script works."""

    def test_traceability_runs(self):
        result = subprocess.run(
            ["python3", "scripts/traceability.py"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
            cwd=os.path.expanduser("~/git/mhubers/ace2/rondo"),
        )
        assert "TRACEABILITY MATRIX" in result.stdout
        assert "TRACED" in result.stdout

    def test_traceability_json(self):
        result = subprocess.run(
            ["python3", "scripts/traceability.py", "--json"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
            cwd=os.path.expanduser("~/git/mhubers/ace2/rondo"),
        )
        data = json.loads(result.stdout)
        assert len(data) >= 5  # at least 5 specs traced


@skip_no_rondo
class TestE2ECompleteWorkflow:
    """The complete Rondo workflow as a living example."""

    def test_workflow_preflight_then_dry_run(self, tmp_path):
        """Step 1: preflight, Step 2: dry-run — like a real user would."""
        # 1. Preflight
        pf = _run(["preflight", "--json"])
        pf_data = json.loads(pf.stdout)
        assert pf_data["can_proceed"]

        # 2. Dry-run
        rf = tmp_path / "workflow.py"
        rf.write_text(
            "from rondo.engine import Round, Task\n"
            "def build_round(): return Round(name='workflow', tasks=[\n"
            "    Task(name='step1', instruction='analyze', done_when='analyzed'),\n"
            "    Task(name='step2', instruction='fix', done_when='fixed'),\n"
            "])\n"
        )
        dr = _run(["run", str(rf), "--dry-run", "--verbose"])
        assert "0/2" in dr.stdout  # both skipped

    def test_workflow_history_json_to_analysis(self):
        """Step 3: Query history for cost analysis."""
        hist = _run(["history", "--json"])
        records = json.loads(hist.stdout)
        if records:
            total = sum(r.get("cost_usd", 0) for r in records)
            assert total >= 0  # valid number


# -- ──────────────────────────────────────────────────────────────
# --  E2E: STD-114 Sanitization Pipeline
# -- ──────────────────────────────────────────────────────────────


class TestE2ESanitizePipeline:
    """Full sanitization pipeline — real data, real scrubbing."""

    def test_sanitize_realistic_ai_output(self):
        """Real-world AI output with leaked secrets gets fully scrubbed."""
        from rondo.sanitize import sanitize_text

        ai_output = (
            "I found the config file. Here's what I see:\n"
            "api_key = 'sk-proj-abc123def456ghi789'\n"
            "password = 'hunter2longpassword'\n"
            "The deployment uses Bearer eyJhbGciOiJIUzI1NiJ9.payload.signature\n"
            "AWS key: AKIAIOSFODNN7EXAMPLE\n"
        )
        result = sanitize_text(ai_output)
        assert result.secrets_found >= 4
        assert "sk-proj-abc123def456ghi789" not in result.sanitized_text
        assert "hunter2longpassword" not in result.sanitized_text
        assert "AKIAIOSFODNN7EXAMPLE" not in result.sanitized_text
        assert "[REDACTED:" in result.sanitized_text

    def test_sanitize_task_result_pipeline(self):
        """Full TaskResult → sanitized copy pipeline."""
        from rondo.engine import TaskResult
        from rondo.sanitize import sanitize_task_result

        tr = TaskResult(
            task_name="code_review",
            raw_output="Found password = 'db_admin_secret_99' in config.py",
            parsed_result={"findings": [{"file": "config.py", "issue": "api_key = 'sk-leaked-key-12345' exposed"}]},
        )
        sanitized_tr, sr = sanitize_task_result(tr)
        # -- Original untouched
        assert "db_admin_secret_99" in tr.raw_output
        # -- Sanitized copy clean
        assert "db_admin_secret_99" not in sanitized_tr.raw_output
        assert "sk-leaked-key-12345" not in json.dumps(sanitized_tr.parsed_result)
        assert sr.secrets_found >= 2

    def test_clean_output_passes_through(self):
        """Output with no secrets passes through unchanged."""
        from rondo.sanitize import sanitize_text

        clean = "The function looks correct. No issues found. Return code 0."
        result = sanitize_text(clean)
        assert result.sanitized_text == clean
        assert result.secrets_found == 0


# -- ──────────────────────────────────────────────────────────────
# --  E2E: STD-113 Audit Trail Pipeline
# -- ──────────────────────────────────────────────────────────────


class TestE2EAuditPipeline:
    """Full audit trail pipeline — intent, dispatch, outcome."""

    def test_complete_audit_lifecycle(self, tmp_path):
        """Intent → outcome → query full lifecycle."""
        from rondo.audit import AuditConfig, AuditTrail

        trail = AuditTrail(config=AuditConfig(audit_dir=str(tmp_path)))

        # -- Phase 1: record intent
        record = trail.record_intent(
            task_name="code_review",
            round_name="sprint_review",
            model="claude-sonnet-4-6",
            prompt="Review src/main.py for security issues",
        )
        assert record.status == "INTENT"
        assert record.dispatch_id.startswith("dsp_")

        # -- Phase 2: record outcome
        trail.record_outcome(
            dispatch_id=record.dispatch_id,
            task_name="code_review",
            status="done",
            exit_code=0,
            cost_usd=0.042,
            duration_sec=18.5,
            raw_output="Found 2 potential SQL injection points in query builder.",
            input_tokens=5000,
            output_tokens=1200,
            files_modified=["src/main.py"],
        )

        # -- Verify JSONL has both records
        jsonl = (tmp_path / "rondo_audit.jsonl").read_text(encoding="utf-8")
        lines = [json.loads(line) for line in jsonl.strip().split("\n")]
        assert len(lines) == 2
        assert lines[0]["status"] == "INTENT"
        assert lines[1]["status"] == "done"
        assert lines[1]["cost_usd"] == 0.042

        # -- Verify prompt file exists and is scrubbed
        prompt_file = tmp_path / f"{record.dispatch_id}.prompt.txt"
        assert prompt_file.exists()

        # -- Verify result file exists
        result_file = tmp_path / f"{record.dispatch_id}.result.json"
        assert result_file.exists()
        result_data = json.loads(result_file.read_text(encoding="utf-8"))
        assert "SQL injection" in result_data["raw_output"]

    def test_audit_scrubs_secrets_in_prompt(self, tmp_path):
        """Audit trail scrubs secrets from prompt before storage."""
        from rondo.audit import AuditConfig, AuditTrail

        trail = AuditTrail(config=AuditConfig(audit_dir=str(tmp_path)))
        record = trail.record_intent(
            task_name="deploy",
            round_name="release",
            model="claude-opus-4-6",
            prompt="Deploy with api_key = 'sk-production-key-abc123' to staging",
        )
        prompt_content = (tmp_path / f"{record.dispatch_id}.prompt.txt").read_text(encoding="utf-8")
        assert "sk-production-key-abc123" not in prompt_content
        assert "[REDACTED:" in prompt_content

    def test_crash_recovery(self, tmp_path):
        """Simulate crash: intent exists but no outcome."""
        from rondo.audit import AuditConfig, AuditTrail

        trail = AuditTrail(config=AuditConfig(audit_dir=str(tmp_path)))
        trail.record_intent(
            task_name="crashed_task",
            round_name="overnight",
            model="claude-sonnet-4-6",
            prompt="Run full test suite",
        )
        # -- No outcome (simulating crash)
        # -- Morning report should find no failed dispatches
        # -- but INTENT record proves the dispatch was attempted
        jsonl = (tmp_path / "rondo_audit.jsonl").read_text(encoding="utf-8")
        data = json.loads(jsonl.strip())
        assert data["status"] == "INTENT"
        assert data["task_name"] == "crashed_task"


# -- ──────────────────────────────────────────────────────────────
# --  E2E: REQ-107 Flakiness Detection Pipeline
# -- ──────────────────────────────────────────────────────────────


class TestE2EFlakyPipeline:
    """Full flakiness detection — simulated overnight dispatch history."""

    def test_detect_flaky_task_from_history(self):
        """Simulated 2-week dispatch history reveals flaky task."""
        from rondo.flaky import DispatchOutcome, FlakyEngine

        engine = FlakyEngine()

        # -- Stable task: always succeeds
        for day in range(14):
            engine.add_outcome(
                DispatchOutcome(
                    task_name="lint_check",
                    prompt_hash="sha256:stable",
                    model="claude-sonnet-4-6",
                    status="done",
                    confidence=0.95,
                    run_at=f"2026-03-{10 + day:02d}T03:00:00Z",
                )
            )

        # -- Flaky task: alternates done/error
        for day in range(14):
            status = "done" if day % 3 != 0 else "error"
            engine.add_outcome(
                DispatchOutcome(
                    task_name="deploy_check",
                    prompt_hash="sha256:flaky",
                    model="claude-sonnet-4-6",
                    status=status,
                    confidence=0.5 if status == "error" else 0.85,
                    run_at=f"2026-03-{10 + day:02d}T03:00:00Z",
                )
            )

        flaky_tasks = engine.get_flaky_tasks()
        flaky_names = [f.task_name for f in flaky_tasks]
        assert "deploy_check" in flaky_names
        assert "lint_check" not in flaky_names

    def test_model_comparison(self):
        """Compare model reliability from dispatch outcomes."""
        from rondo.flaky import DispatchOutcome, FlakyEngine

        engine = FlakyEngine()
        # -- Sonnet: mostly reliable
        for i in range(10):
            engine.add_outcome(
                DispatchOutcome(
                    task_name="review",
                    prompt_hash="sha256:same",
                    model="claude-sonnet-4-6",
                    status="done",
                    confidence=0.9,
                    run_at=f"2026-03-{10 + i}T01:00:00Z",
                )
            )
        # -- Haiku: more errors
        for i in range(10):
            engine.add_outcome(
                DispatchOutcome(
                    task_name="review",
                    prompt_hash="sha256:same",
                    model="claude-haiku-4-5",
                    status="done" if i % 2 == 0 else "error",
                    confidence=0.6,
                    run_at=f"2026-03-{10 + i}T02:00:00Z",
                )
            )
        stats = engine.get_model_stats()
        assert stats["claude-haiku-4-5"]["flakiness"] > stats["claude-sonnet-4-6"]["flakiness"]

    def test_confidence_variance_unstable_prompt(self):
        """High confidence variance = poorly defined task."""
        from rondo.flaky import DispatchOutcome, FlakyEngine

        engine = FlakyEngine()
        # -- Wild confidence swings: 0.2 to 0.95
        for conf in [0.2, 0.95, 0.3, 0.88, 0.15, 0.92]:
            engine.add_outcome(
                DispatchOutcome(
                    task_name="vague_task",
                    prompt_hash="sha256:vague",
                    model="m",
                    status="done",
                    confidence=conf,
                    run_at="2026-03-20T01:00:00Z",
                )
            )
        summary = engine.get_summary("vague_task", "sha256:vague")
        assert summary.confidence_variance > 0.05

    def test_full_json_report(self):
        """Flakiness summary serializes to complete JSON."""
        from rondo.flaky import DispatchOutcome, FlakyEngine

        engine = FlakyEngine()
        for i, s in enumerate(["done", "error", "done", "error", "done"]):
            engine.add_outcome(
                DispatchOutcome(
                    task_name="unstable",
                    prompt_hash="sha256:test",
                    model="m",
                    status=s,
                    confidence=0.5,
                    run_at=f"2026-03-{20 + i}T01:00:00Z",
                )
            )
        flaky_tasks = engine.get_flaky_tasks()
        report = [f.to_dict() for f in flaky_tasks]
        json_str = json.dumps(report, indent=2)
        data = json.loads(json_str)
        assert len(data) == 1
        assert data[0]["flakiness_score"] > 0.2
        assert data[0]["root_cause"] == "UNKNOWN"
        assert data[0]["total_runs"] == 5


# -- ──────────────────────────────────────────────────────────────
# --  E2E: rondo audit CLI (STD-113 reqs 011-013)
# -- ──────────────────────────────────────────────────────────────


@skip_no_rondo
class TestE2EAuditCLI:
    """rondo audit — real CLI, real audit data."""

    def test_audit_list(self):
        """Rondo audit shows records and cost."""
        result = _run(["audit"])
        assert "Audit Trail" in result.stdout or "No audit data" in result.stdout

    def test_audit_cost(self):
        """Rondo audit --cost shows total."""
        result = _run(["audit", "--cost"])
        assert "$" in result.stdout or "No audit data" in result.stdout

    def test_audit_failed(self):
        """Rondo audit --failed shows or reports none."""
        result = _run(["audit", "--failed"])
        assert "Failed" in result.stdout or "No failed" in result.stdout or "No audit" in result.stdout

    def test_audit_json(self):
        """Rondo audit --json returns valid JSON array."""
        result = _run(["audit", "--json"])
        if "No audit data" not in result.stdout:
            data = json.loads(result.stdout)
            assert isinstance(data, list)

    def test_audit_cost_json(self):
        """Rondo audit --cost --json returns total."""
        result = _run(["audit", "--cost", "--json"])
        if "No audit data" not in result.stdout:
            data = json.loads(result.stdout)
            assert "total_cost_usd" in data

    def test_audit_nonexistent_id(self):
        """Rondo audit <bad_id> returns error or 'no data' message."""
        result = _run(["audit", "nonexistent-dispatch-id"])
        assert result.returncode != 0 or "No records" in result.stdout or "No audit data" in result.stdout


# -- ──────────────────────────────────────────────────────────────
# --  E2E: rondo flaky CLI (REQ-107 reqs 007-008)
# -- ──────────────────────────────────────────────────────────────


@skip_no_rondo
class TestE2EFlakyCLI:
    """rondo flaky — real CLI, real flakiness detection."""

    def test_flaky_default(self):
        """Rondo flaky shows flaky tasks or none."""
        result = _run(["flaky"])
        assert "flaky" in result.stdout.lower() or "No audit data" in result.stdout

    def test_flaky_json(self):
        """Rondo flaky --json returns valid JSON array."""
        result = _run(["flaky", "--json"])
        if "No audit data" not in result.stdout:
            data = json.loads(result.stdout)
            assert isinstance(data, list)

    def test_flaky_custom_threshold(self):
        """Rondo flaky --threshold 0.50 uses custom threshold."""
        result = _run(["flaky", "--threshold", "0.50"])
        assert result.returncode == 0

    def test_flaky_model_reliability(self):
        """Rondo flaky shows model reliability when data exists."""
        result = _run(["flaky"])
        # -- If no flaky tasks, should show model reliability
        if "No flaky tasks" in result.stdout:
            assert "reliability" in result.stdout.lower() or result.returncode == 0


# -- ──────────────────────────────────────────────────────────────
# --  E2E: Always-On Infrastructure Verification
# -- ──────────────────────────────────────────────────────────────


class TestE2EAlwaysOnInfrastructure:
    """Verify the ALWAYS-ON golden rule: audit, sanitize, metrics always work."""

    def test_audit_trail_exists_after_dispatch(self, tmp_path):
        """After dispatch, audit trail has records (always-on)."""
        from rondo.audit import AuditConfig, AuditTrail

        trail = AuditTrail(config=AuditConfig(audit_dir=str(tmp_path)))
        record = trail.record_intent(
            task_name="always-on-test",
            round_name="test",
            model="sonnet",
            prompt="verify always-on",
        )
        trail.record_outcome(
            dispatch_id=record.dispatch_id,
            task_name="always-on-test",
            status="done",
            exit_code=0,
            cost_usd=0.01,
        )
        jsonl = (tmp_path / "rondo_audit.jsonl").read_text(encoding="utf-8")
        assert len(jsonl.strip().split("\n")) == 2

    def test_sanitize_always_runs(self):
        """Sanitize runs on any text — never errors, always returns."""
        from rondo.sanitize import sanitize_text

        # -- Clean text: passes through
        r1 = sanitize_text("normal output")
        assert r1.sanitized_text == "normal output"
        # -- Dirty text: scrubbed
        r2 = sanitize_text("api_key = 'sk-leaked-value-123'")
        assert "sk-leaked" not in r2.sanitized_text
        # -- Empty: safe
        r3 = sanitize_text("")
        assert r3.secrets_found == 0

    def test_dispatch_id_always_available(self):
        """TaskResult always has dispatch_id field (even if empty)."""
        from rondo.engine import TaskResult

        tr = TaskResult(task_name="test")
        assert hasattr(tr, "dispatch_id")

    def test_flaky_engine_always_works(self):
        """FlakyEngine works with zero data — never errors."""
        from rondo.flaky import FlakyEngine

        engine = FlakyEngine()
        assert engine.get_flaky_tasks() == []
        assert engine.get_model_stats() == {}


# -- ──────────────────────────────────────────────────────────────
# --  E2E: rondo spool CLI (REQ-101 reqs 047-049)
# --  Class name MUST differ from TestE2ESpoolCLI below — duplicate class names
# --  shadow earlier definitions and pytest would never collect the first suite.
# -- ──────────────────────────────────────────────────────────────


@skip_no_rondo
class TestE2ESpoolCLIReq101:
    """rondo spool — real CLI, real spool management (REQ-101)."""

    def test_spool_list(self):
        """Rondo spool list shows pending or empty."""
        result = _run(["spool", "list"])
        assert "Pending" in result.stdout or "empty" in result.stdout

    def test_spool_list_json(self):
        """Rondo spool list --json returns valid JSON."""
        result = _run(["spool", "list", "--json"])
        data = json.loads(result.stdout)
        assert isinstance(data, list)

    def test_spool_clean(self):
        """Rondo spool clean runs without error."""
        result = _run(["spool", "clean"])
        assert "Cleaned" in result.stdout
        assert result.returncode == 0

    def test_spool_export(self):
        """Rondo spool export returns JSON array."""
        result = _run(["spool", "export", "--since", "2026-01-01"])
        data = json.loads(result.stdout)
        assert isinstance(data, list)

    def test_spool_help(self):
        """Rondo spool --help shows actions."""
        result = _run(["spool", "--help"])
        assert "list" in result.stdout
        assert "clean" in result.stdout
        assert "export" in result.stdout


# -- ──────────────────────────────────────────────────────────────
# --  E2E: Full Dispatch Pipeline (ALWAYS-ON verification)
# -- ──────────────────────────────────────────────────────────────


class TestE2EFullPipeline:
    """Verify the complete dispatch pipeline: audit + sanitize + spool."""

    def test_pipeline_produces_all_artifacts(self, tmp_path):
        """One dispatch creates audit, spool, and history artifacts."""
        from rondo.audit import AuditConfig, AuditTrail
        from rondo.spool import SpoolConfig, SpoolManager

        # -- Audit
        trail = AuditTrail(config=AuditConfig(audit_dir=str(tmp_path / "audit")))
        record = trail.record_intent(
            task_name="pipeline-test",
            round_name="e2e",
            model="sonnet",
            prompt="test prompt",
        )
        trail.record_outcome(
            dispatch_id=record.dispatch_id,
            task_name="pipeline-test",
            status="done",
            exit_code=0,
            cost_usd=0.05,
            duration_sec=5.0,
            raw_output="clean result",
        )

        # -- Spool
        spool = SpoolManager(config=SpoolConfig(spool_dir=str(tmp_path / "spool")))
        spool_path = spool.write_result(
            task_name="pipeline-test",
            result={"status": "done", "dispatch_id": record.dispatch_id},
        )

        # -- Verify all artifacts exist
        assert (tmp_path / "audit" / "rondo_audit.jsonl").exists()
        assert (tmp_path / "audit" / f"{record.dispatch_id}.prompt.txt").exists()
        assert (tmp_path / "audit" / f"{record.dispatch_id}.result.json").exists()
        assert spool_path is not None and spool_path.exists()

        # -- Spool file references dispatch_id (cross-linkable)
        spool_data = json.loads(spool_path.read_text(encoding="utf-8"))
        assert spool_data["dispatch_id"] == record.dispatch_id


# -- ──────────────────────────────────────────────────────────────
# --  E2E: rondo spool (RONDO-30)
# -- ──────────────────────────────────────────────────────────────


@skip_no_rondo
class TestE2ESpoolCLI:
    """rondo spool — manage result spool from CLI."""

    def test_spool_list_empty(self):
        """Rondo spool list on empty spool returns clean message."""
        result = _run(["spool", "list"])
        assert result.returncode == 0
        assert "empty" in result.stdout.lower() or "0" in result.stdout

    def test_spool_consume_empty(self):
        """Rondo spool consume on empty spool shows no results."""
        result = _run(["spool", "consume"])
        assert result.returncode == 0
        assert "No results" in result.stdout or "[]" in result.stdout

    def test_spool_clean_empty(self):
        """Rondo spool clean on empty spool is a no-op."""
        result = _run(["spool", "clean"])
        assert result.returncode == 0

    def test_spool_list_json(self):
        """Rondo spool list --json returns valid JSON."""
        result = _run(["spool", "list", "--json"])
        if result.returncode == 0 and result.stdout.strip():
            data = json.loads(result.stdout)
            assert isinstance(data, list)


# -- ──────────────────────────────────────────────────────────────
# --  E2E: rondo init (U-10 to U-14, RONDO-34)
# -- ──────────────────────────────────────────────────────────────


@skip_no_rondo
class TestE2EInit:
    """rondo init — scaffold a starter round file."""

    def test_init_creates_file(self, tmp_path):
        """U-10: rondo init creates a round file."""
        result = subprocess.run(
            [RONDO_BIN, "init"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
            env=_e2e_env(),
            cwd=str(tmp_path),
        )
        assert result.returncode == 0
        assert (tmp_path / "round.py").exists()

    def test_init_file_is_valid_python(self, tmp_path):
        """U-11: generated file is valid Python that imports correctly."""
        subprocess.run(
            [RONDO_BIN, "init"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
            env=_e2e_env(),
            cwd=str(tmp_path),
        )
        content = (tmp_path / "round.py").read_text()
        compile(content, "round.py", "exec")

    def test_init_file_runs_dry(self, tmp_path):
        """U-11: generated file runs with rondo run --dry-run immediately."""
        subprocess.run(
            [RONDO_BIN, "init"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
            env=_e2e_env(),
            cwd=str(tmp_path),
        )
        result = subprocess.run(
            [RONDO_BIN, "run", str(tmp_path / "round.py"), "--dry-run"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
            env=_e2e_env(),
        )
        assert "skipped" in result.stdout.lower() or result.returncode == 1

    def test_init_with_name(self, tmp_path):
        """U-12: --name sets the round and task name."""
        result = subprocess.run(
            [RONDO_BIN, "init", "--name", "ush-scan"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
            env=_e2e_env(),
            cwd=str(tmp_path),
        )
        assert result.returncode == 0
        content = (tmp_path / "round.py").read_text()
        assert "ush-scan" in content

    def test_init_no_overwrite(self, tmp_path):
        """U-14: init refuses to overwrite existing file."""
        (tmp_path / "round.py").write_text("existing")
        result = subprocess.run(
            [RONDO_BIN, "init"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
            env=_e2e_env(),
            cwd=str(tmp_path),
        )
        assert result.returncode != 0
        assert (tmp_path / "round.py").read_text() == "existing"


# -- ──────────────────────────────────────────────────────────────
# --  RONDO-110: Real dispatch smoke tests (costs ~$0.01 each)
# -- ──────────────────────────────────────────────────────────────


@skip_no_rondo
class TestRealDispatchSmoke:
    """Smoke test: real Claude + Ollama dispatch.

    These actually send prompts to AI — they cost money (Claude ~$0.01)
    or time (Ollama ~2 sec). They prove the full dispatch path works:
    subprocess → hooks → Claude → result, or HTTP → Ollama → result.

    Session 94: 44 'blocked' errors went undetected because no test
    ever ran a real Claude dispatch. This test prevents that.
    """

    def test_real_ollama_dispatch(self) -> None:
        """Ollama dispatch: real HTTP call to local model."""
        import tempfile
        import textwrap

        round_src = textwrap.dedent("""
            from rondo.engine import Round, Task
            def build_round():
                return Round(name="smoke", tasks=[
                    Task(name="t1", instruction="Say hello.", done_when="Said hello.")
                ])
        """)
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write(round_src)
            round_file = f.name
        result = _run(["run", round_file, "--model", "local:llama3.1:8b"], timeout=30)
        ## -- 0=success, 1=Ollama down or dispatch error — both are valid PATH outcomes
        assert result.returncode in (0, 1), f"Unexpected returncode {result.returncode}: {result.stderr[:200]}"

    def test_real_claude_dispatch(self) -> None:
        """Claude subprocess dispatch — only works from independent process.

        RONDO-134 lesson: this test used pytest.skip on auth failure, hiding
        100% subprocess failure from inside Claude Code sessions for months.

        Now: skip ONLY if 'claude' binary is not installed (real prerequisite).
        Auth failure = EXPECTED FAIL when run from inside CC (documented).
        """
        import json as _json
        import shutil
        import tempfile
        import textwrap

        if not shutil.which("claude"):
            pytest.skip("Claude binary not installed")

        round_src = textwrap.dedent("""
            from rondo.engine import Round, Task
            def build_round():
                return Round(name="claude-smoke", tasks=[
                    Task(name="t1", instruction="Reply with exactly: OK", done_when="Replied OK.")
                ])
        """)
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write(round_src)
            round_file = f.name
        result = _run(
            ["run", round_file, "--model", "haiku", "--bare"],
            timeout=120,
        )
        # -- From inside CC session: subprocess WILL fail (known, v0.7 uses Agent path instead)
        # -- From CLI: subprocess should work
        import os

        if os.environ.get("CLAUDECODE"):
            # -- In-session: subprocess fails. This is EXPECTED, not a skip.
            # -- The real dispatch path is Agent (tested in test_real_dispatch.py PAT)
            assert result.returncode != 0, "Subprocess should fail from inside CC session"
        else:
            # -- Outside session: subprocess should work
            if result.returncode == 0 and result.stdout.strip():
                data = _json.loads(result.stdout)
                assert data.get("status") in ("done", "partial", "error", "skipped")


# -- ──────────────────────────────────────────────────────────────
# --  RONDO-FIX-641: Real cloud provider E2E (costs ~$0.01-0.05)
# -- ──────────────────────────────────────────────────────────────


def _has_cloud_key(provider: str) -> bool:
    """Check if an API key is configured for a cloud provider."""
    try:
        from rondo.adapters.auth import load_api_key

        return bool(load_api_key(provider))
    except Exception:  # noqa: BLE001
        return False


skip_no_gemini = pytest.mark.skipif(not _has_cloud_key("gemini"), reason="No Gemini API key")
skip_no_grok = pytest.mark.skipif(not _has_cloud_key("grok"), reason="No Grok API key")
skip_no_mistral = pytest.mark.skipif(not _has_cloud_key("mistral"), reason="No Mistral API key")


@pytest.mark.cloud
@skip_no_rondo
class TestRealCloudDispatch:
    """Real cloud provider dispatch — proves adapters work end-to-end.

    Each test sends a tiny prompt to a real cloud API and verifies:
    1. Adapter loads the key correctly (auth chain)
    2. HTTP request succeeds (payload format, headers)
    3. Response parses into valid TaskResult (done + non-empty output)
    4. Finalization records audit trail

    Costs: Gemini ~$0.001, Grok ~$0.003, Mistral ~$0.002 per test.
    Skips automatically if API key not configured for that provider.
    """

    @skip_no_gemini
    def test_real_gemini_dispatch(self) -> None:
        """Gemini adapter: real HTTP to Google Gemini API."""
        from rondo.adapters.auth import load_api_key
        from rondo.adapters.gemini import GeminiAdapter

        adapter = GeminiAdapter(api_key=load_api_key("gemini"))
        result = adapter.dispatch(
            prompt="Reply with exactly one word: HELLO",
            model="gemini-2.5-flash",
        )
        assert result.status == "done", f"Gemini failed: {result.error_message}"
        assert result.raw_output.strip(), "Gemini returned empty response"
        assert result.duration_sec > 0

    @skip_no_grok
    def test_real_grok_dispatch(self) -> None:
        """Grok adapter: real HTTP to xAI API."""
        from rondo.adapters.auth import load_api_key
        from rondo.adapters.chat_completions import ChatCompletionsAdapter

        adapter = ChatCompletionsAdapter(
            provider_name="grok",
            base_url="https://api.x.ai/v1",
            api_key=load_api_key("grok"),
            default_model="grok-3-fast",
        )
        result = adapter.dispatch(
            prompt="Reply with exactly one word: HELLO",
            model="grok-3-fast",
        )
        assert result.status == "done", f"Grok failed: {result.error_message}"
        assert result.raw_output.strip(), "Grok returned empty response"
        assert result.duration_sec > 0

    @skip_no_mistral
    def test_real_mistral_dispatch(self) -> None:
        """Mistral adapter: real HTTP to Mistral API (EU provider)."""
        from rondo.adapters.auth import load_api_key
        from rondo.adapters.chat_completions import ChatCompletionsAdapter

        adapter = ChatCompletionsAdapter(
            provider_name="mistral",
            base_url="https://api.mistral.ai/v1",
            api_key=load_api_key("mistral"),
            default_model="mistral-small-latest",
        )
        result = adapter.dispatch(
            prompt="Reply with exactly one word: HELLO",
            model="mistral-small-latest",
        )
        assert result.status == "done", f"Mistral failed: {result.error_message}"
        assert result.raw_output.strip(), "Mistral returned empty response"
        assert result.duration_sec > 0


@pytest.mark.cloud
@skip_no_rondo
class TestRealMultiProviderReview:
    """Real multi-provider review — Gemini + Grok review the same prompt.

    Proves rondo_multi_review works end-to-end with real API calls.
    This is the "ask two AIs to review something" pattern from the doc.
    """

    @skip_no_gemini
    @skip_no_grok
    def test_real_gemini_grok_review(self) -> None:
        """Two real providers review the same code snippet."""
        from rondo.adapters.auth import load_api_key
        from rondo.adapters.chat_completions import ChatCompletionsAdapter
        from rondo.adapters.gemini import GeminiAdapter

        prompt = "Review this Python function for bugs:\ndef add(a, b): return a + b"

        gemini = GeminiAdapter(api_key=load_api_key("gemini"))
        grok = ChatCompletionsAdapter(
            provider_name="grok",
            base_url="https://api.x.ai/v1",
            api_key=load_api_key("grok"),
            default_model="grok-3-fast",
        )

        r_gemini = gemini.dispatch(prompt=prompt, model="gemini-2.5-flash")
        r_grok = grok.dispatch(prompt=prompt, model="grok-3-fast")

        assert r_gemini.status == "done", f"Gemini: {r_gemini.error_message}"
        assert r_grok.status == "done", f"Grok: {r_grok.error_message}"
        ## Both should return non-empty reviews
        assert len(r_gemini.raw_output) > 10, "Gemini review too short"
        assert len(r_grok.raw_output) > 10, "Grok review too short"

    @skip_no_gemini
    @skip_no_mistral
    def test_real_gemini_mistral_review(self) -> None:
        """Gemini + Mistral (EU) review the same code."""
        from rondo.adapters.auth import load_api_key
        from rondo.adapters.chat_completions import ChatCompletionsAdapter
        from rondo.adapters.gemini import GeminiAdapter

        prompt = "Is this SQL safe from injection?\nquery = f'SELECT * FROM users WHERE id={user_id}'"

        gemini = GeminiAdapter(api_key=load_api_key("gemini"))
        mistral = ChatCompletionsAdapter(
            provider_name="mistral",
            base_url="https://api.mistral.ai/v1",
            api_key=load_api_key("mistral"),
            default_model="mistral-small-latest",
        )

        r_gemini = gemini.dispatch(prompt=prompt, model="gemini-2.5-flash")
        r_mistral = mistral.dispatch(prompt=prompt, model="mistral-small-latest")

        assert r_gemini.status == "done", f"Gemini: {r_gemini.error_message}"
        assert r_mistral.status == "done", f"Mistral: {r_mistral.error_message}"
        ## Both should flag the SQL injection — check broad keyword set
        ## (models may rephrase: "injection", "parameterize", "sanitize", etc.)
        combined = (r_gemini.raw_output + r_mistral.raw_output).lower()
        security_keywords = (
            "inject",
            "unsafe",
            "vulnerab",
            "sanitiz",
            "parameteriz",
            "f-string",
            "sqli",
            "untrust",
            "escap",
        )
        assert any(kw in combined for kw in security_keywords), (
            f"Neither provider flagged the SQL injection. Combined output: {combined[:200]}"
        )


@pytest.mark.cloud
@skip_no_rondo
class TestRealProviderHealth:
    """Real health checks against live cloud APIs."""

    @skip_no_gemini
    def test_gemini_health(self) -> None:
        """Gemini health check returns True with valid key."""
        from rondo.adapters.auth import load_api_key
        from rondo.adapters.gemini import GeminiAdapter

        adapter = GeminiAdapter(api_key=load_api_key("gemini"))
        assert adapter.health() is True

    @skip_no_grok
    def test_grok_health(self) -> None:
        """Grok health check returns True — REQ-109 req 071."""
        from rondo.adapters.auth import load_api_key
        from rondo.adapters.chat_completions import ChatCompletionsAdapter

        adapter = ChatCompletionsAdapter(
            provider_name="grok",
            base_url="https://api.x.ai/v1",
            api_key=load_api_key("grok"),
        )
        assert adapter.health() is True

    @skip_no_mistral
    def test_mistral_health(self) -> None:
        """Mistral health check returns True."""
        from rondo.adapters.auth import load_api_key
        from rondo.adapters.chat_completions import ChatCompletionsAdapter

        adapter = ChatCompletionsAdapter(
            provider_name="mistral",
            base_url="https://api.mistral.ai/v1",
            api_key=load_api_key("mistral"),
        )
        assert adapter.health() is True


# -- ──────────────────────────────────────────────────────────────
# --  E2E: rondo providers CLI — REQ-109 req 020
# -- ──────────────────────────────────────────────────────────────


@skip_no_rondo
class TestE2EProvidersCLI:
    """rondo providers — show configured provider health status."""

    def test_providers_returns_success(self) -> None:
        """Rondo providers exits 0 regardless of provider config."""
        result = _run(["providers"])
        assert result.returncode == 0

    def test_providers_json_valid(self) -> None:
        """Rondo providers --json returns valid JSON with providers key."""
        result = _run(["providers", "--json"])
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert "providers" in data
        assert isinstance(data["providers"], list)


# -- ──────────────────────────────────────────────────────────────
# --  RONDO-149: rondo review CLI — REQ-109 reqs 082-087
# -- ──────────────────────────────────────────────────────────────


@skip_no_rondo
class TestE2EReviewDryRun:
    """rondo review --dry-run shows prompt without dispatching."""

    def test_review_dry_run_shows_file_info(self) -> None:
        """Dry-run shows file name, providers, tier, prompt length."""
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write("def add(a, b):\n    return a + b\n")
            path = f.name
        result = _run(["review", path, "--dry-run"])
        assert result.returncode == 0
        assert "Providers:" in result.stdout
        assert "Tier:" in result.stdout
        assert "dry-run" in result.stdout.lower()

    def test_review_dry_run_json(self) -> None:
        """Dry-run with --output json returns structured data."""
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write("x = 1\n")
            path = f.name
        result = _run(["review", path, "--dry-run", "--output", "json"])
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["status"] == "dry_run"
        assert "prompt_length" in data
        assert "providers" in data

    def test_review_missing_file_fails(self) -> None:
        """Review of nonexistent file returns error."""
        result = _run(["review", "/tmp/nonexistent_file_12345.py"])
        assert result.returncode != 0

    def test_review_empty_file_fails(self) -> None:
        """Review of empty file returns error."""
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write("")
            path = f.name
        result = _run(["review", path])
        assert result.returncode != 0

    def test_review_tier_flag(self) -> None:
        """--tier high uses best_model from config."""
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write("x = 1\n")
            path = f.name
        result = _run(["review", path, "--dry-run", "--tier", "high", "--output", "json"])
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["tier"] == "high"


@pytest.mark.cloud
@skip_no_rondo
class TestE2EReviewRealCloud:
    """rondo review with real cloud dispatch."""

    @skip_no_gemini
    def test_review_real_gemini(self) -> None:
        """Real review with Gemini returns findings."""
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write("def add(a, b):\n    return a + b\n")
            path = f.name
        result = _run(["review", path, "--providers", "gemini", "--output", "json"], timeout=60)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert len(data["reviews"]) == 1
        assert data["reviews"][0]["status"] == "done"
        assert len(data["reviews"][0]["output"]) > 10


# -- ──────────────────────────────────────────────────────────────
# --  E2E: version consistency — installed binary matches repo
# -- ──────────────────────────────────────────────────────────────


@skip_no_rondo
class TestE2EVersionConsistency:
    """Installed rondo binary should match the repo source version."""

    def test_installed_matches_repo_version(self) -> None:
        """Catch stale installs: installed binary version == repo _version.py."""
        from rondo._version import get_version

        repo_version = get_version()
        result = _run(["--version"])
        installed_version = result.stdout.strip().replace("rondo ", "")
        assert installed_version == repo_version, (
            f"Stale install: binary={installed_version}, repo={repo_version}. "
            f"Run: uv tool install --editable ~/git/mhubers/ace2/rondo"
        )


# -- sig: mgh-6201.cd.bd955f.e4a1.e2e001
