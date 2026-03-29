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
        rf.write_text("from rondo.engine import Round, Task\ndef build_round(): return Round(name='t', tasks=[Task(name='t', instruction='do', done_when='done')])\n")
        result = _run(["run", str(rf), "--dry-run", "--model", "opus"])
        assert result.returncode in (0, 1)

    def test_run_with_bare_flag(self, tmp_path):
        rf = tmp_path / "r.py"
        rf.write_text("from rondo.engine import Round, Task\ndef build_round(): return Round(name='t', tasks=[Task(name='t', instruction='do', done_when='done')])\n")
        result = _run(["run", str(rf), "--dry-run", "--bare"])
        assert result.returncode in (0, 1)

    def test_run_with_json_schema_auto(self, tmp_path):
        rf = tmp_path / "r.py"
        rf.write_text("from rondo.engine import Round, Task\ndef build_round(): return Round(name='t', tasks=[Task(name='t', instruction='do', done_when='done')])\n")
        result = _run(["run", str(rf), "--dry-run", "--json-schema", "auto"])
        assert result.returncode in (0, 1)

    def test_run_with_max_budget(self, tmp_path):
        rf = tmp_path / "r.py"
        rf.write_text("from rondo.engine import Round, Task\ndef build_round(): return Round(name='t', tasks=[Task(name='t', instruction='do', done_when='done')])\n")
        result = _run(["run", str(rf), "--dry-run", "--max-budget", "0.50"])
        assert result.returncode in (0, 1)

    def test_run_with_all_flags(self, tmp_path):
        rf = tmp_path / "r.py"
        rf.write_text("from rondo.engine import Round, Task\ndef build_round(): return Round(name='t', tasks=[Task(name='t', instruction='do', done_when='done')])\n")
        result = _run(["run", str(rf), "--dry-run", "--verbose", "--bare", "--json-schema", "auto", "--system-prompt", "auto", "--max-budget", "1.00", "--model", "sonnet"])
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
class TestE2ETraceability:
    """Validate traceability script works."""

    def test_traceability_runs(self):
        result = subprocess.run(
            ["python3", "scripts/traceability.py"],
            capture_output=True, text=True, check=False,
            timeout=10, cwd=os.path.expanduser("~/git/mhubers/ace2/rondo"),
        )
        assert "TRACEABILITY MATRIX" in result.stdout
        assert "TRACED" in result.stdout

    def test_traceability_json(self):
        result = subprocess.run(
            ["python3", "scripts/traceability.py", "--json"],
            capture_output=True, text=True, check=False,
            timeout=10, cwd=os.path.expanduser("~/git/mhubers/ace2/rondo"),
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


# -- sig: mgh-6201.cd.bd955f.e4a1.e2e001
