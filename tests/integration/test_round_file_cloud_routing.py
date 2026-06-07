# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Round-file cloud-model routing — RONDO-342 (VER-001).

THE BUG THIS PINS (found via usher-syndrome's 80-vote cloud panel):
`rondo run <roundfile>` could not dispatch cloud models. A round whose
tasks carry provider models (gemini:high, grok:high, ...) died with
"Invalid model 'grok:high'. Valid: ['haiku','opus',...]" — every task,
0/N done.

ROOT CAUSE: the round runner (run_sequential / run_parallel) sent every
task to dispatch_task() → resolve_model(), which validates against a
CLAUDE-ONLY set and raises before any provider routing. The inline path
(`rondo "x" --model gemini:...`) and the MCP path (rondo_run_file) route
cloud models correctly via get_provider_with_fallback — but the
round-file path never did. Two dispatch front-doors, only one wired.

WHY IT HID: every cloud test in the suite goes through rondo_run_file.
ZERO tests exercised run_round() with a cloud-model round file. A test
gap hid a routing gap. This file is that missing gap.

DESIGN NOTE — these tests must NOT mock dispatch_task: mocking it is
exactly what let the bug survive (the mock never validates the model).
They use dry_run=True so the REAL router runs, free, no dispatch. This
is the unmocked contract test the seam was missing (CONTRIBUTING rule 5).
"""

from __future__ import annotations

from rondo.config import RondoConfig
from rondo.engine import Round, Task
from rondo.runner import run_round

CLOUD_MODELS = ["gemini:gemini-2.5-flash", "grok:grok-3", "openai:gpt-4.1", "mistral:mistral-large-latest"]


def _errors(result) -> str:
    """All error text from a RoundResult, joined for substring checks."""
    parts = [result.summary or ""]
    for tr in result.task_results:
        parts.append(tr.error_message or "")
        parts.append(tr.error_code or "")
    return " ".join(parts)


class TestRoundFileCloudRouting:
    """run_round() must route per-task cloud models to providers, not reject them."""

    def test_cloud_model_round_not_rejected_as_invalid(self) -> None:
        """A round with a cloud-model task must NOT die with 'Invalid model'."""
        rnd = Round(
            name="cloud-panel",
            tasks=[Task(name="vote", instruction="Adjudicate signal X", done_when="done", model="grok:grok-3")],
        )
        result = run_round(rnd, config=RondoConfig(workers=1, dry_run=True))
        assert "Invalid model" not in _errors(result), (
            f"round-file cloud routing regressed (RONDO-342): {_errors(result)}"
        )
        assert result.status != "error", f"cloud-model round errored: {_errors(result)}"

    def test_each_cloud_provider_routes_in_a_round(self) -> None:
        """Every supported provider prefix routes through run_round (dry-run)."""
        for model in CLOUD_MODELS:
            rnd = Round(
                name=f"panel-{model}",
                tasks=[Task(name="vote", instruction="x", done_when="done", model=model)],
            )
            result = run_round(rnd, config=RondoConfig(workers=1, dry_run=True))
            assert "Invalid model" not in _errors(result), f"{model} rejected by round runner: {_errors(result)}"
            assert result.status != "error", f"{model} errored in round: {_errors(result)}"

    def test_usher_panel_shape_mixed_providers(self) -> None:
        """The real USH shape: many tasks, different providers per task, one round."""
        tasks = [
            Task(name=f"sig{i}--{model.split(':')[0]}", instruction="adjudicate", done_when="done", model=model)
            for i, model in enumerate(CLOUD_MODELS * 3)
        ]
        rnd = Round(name="ush-80-vote", tasks=tasks)
        result = run_round(rnd, config=RondoConfig(workers=1, dry_run=True))
        assert "Invalid model" not in _errors(result), f"mixed-provider panel regressed: {_errors(result)}"
        assert result.status != "error", f"mixed-provider panel errored: {_errors(result)}"
        # -- every task previewed, none rejected
        assert len(result.task_results) == len(tasks)

    def test_parallel_round_also_routes_cloud(self) -> None:
        """The parallel runner (workers>1) must route cloud too — same seam."""
        tasks = [
            Task(name=f"v{i}", instruction="x", done_when="done", model="gemini:gemini-2.5-flash") for i in range(4)
        ]
        rnd = Round(name="parallel-cloud", tasks=tasks)
        result = run_round(rnd, config=RondoConfig(workers=4, dry_run=True))
        assert "Invalid model" not in _errors(result), f"parallel cloud routing regressed: {_errors(result)}"
        assert result.status != "error", f"parallel cloud round errored: {_errors(result)}"

    def test_claude_model_round_still_works(self) -> None:
        """Regression guard: Claude-model rounds keep working unchanged."""
        rnd = Round(
            name="claude-round",
            tasks=[Task(name="t", instruction="x", done_when="done", model="sonnet")],
        )
        result = run_round(rnd, config=RondoConfig(workers=1, dry_run=True))
        assert result.status != "error", f"claude-model round broke: {_errors(result)}"


def _write_round(tmp_path, model: str) -> str:
    """Write a one-task round file with the given model; return its path."""
    content = (
        "from rondo.engine import Round, Task\n\n"
        "def build_round():\n"
        f'    return Round(name="r", tasks=[Task(name="t", instruction="x", done_when="d", model="{model}")])\n'
    )
    p = tmp_path / "round.py"
    p.write_text(content, encoding="utf-8")
    return str(p)


class TestCloudRoundInsideClaudeCode:
    """RONDO-344: preflight's nested-session guard must be MODEL-AWARE.

    PROOF-B failure (USH live panel, 2026-06-07): the cloud-only 80-vote
    round was hard-blocked by preflight RED 'CLAUDECODE env var is set'.
    The nested-session hazard is REAL — but only for tasks that spawn a
    claude subprocess. A cloud-only round makes HTTP calls; blocking it
    inside Claude Code protects nothing and broke the documented USH flow.

    Guard preserved where it matters: Claude-bound rounds still go RED.
    """

    def test_cloud_only_round_runs_inside_claude_code(self, tmp_path, monkeypatch) -> None:
        """A cloud-only round must pass preflight even with CLAUDECODE set."""
        from unittest.mock import patch as _patch

        from rondo.cli import EXIT_SUCCESS, main
        from rondo.engine import RoundResult

        monkeypatch.setenv("CLAUDECODE", "1")
        done = RoundResult(round_name="r", status="done")
        with _patch("rondo.cli._dispatch_with_provider", return_value=done):
            exit_code = main(["run", _write_round(tmp_path, "gemini:gemini-2.5-flash")])
        assert exit_code == EXIT_SUCCESS, (
            "cloud-only round blocked inside Claude Code (RONDO-344 regression) — "
            "nested-session guard fired on a round with zero claude subprocesses"
        )

    def test_claude_round_still_blocked_inside_claude_code(self, tmp_path, monkeypatch) -> None:
        """The guard KEEPS protecting Claude-bound rounds — never weaken it."""
        from rondo.cli import EXIT_FAILURE, main

        monkeypatch.setenv("CLAUDECODE", "1")
        exit_code = main(["run", _write_round(tmp_path, "sonnet")])
        assert exit_code == EXIT_FAILURE, "claude-bound round must STILL be preflight-blocked in-session"

    def test_mixed_round_is_blocked_inside_claude_code(self, tmp_path, monkeypatch) -> None:
        """One claude-bound task is enough to keep the hard guard."""
        from rondo.cli import EXIT_FAILURE, main

        content = (
            "from rondo.engine import Round, Task\n\n"
            "def build_round():\n"
            "    return Round(name='r', tasks=["
            "Task(name='a', instruction='x', done_when='d', model='gemini:gemini-2.5-flash'), "
            "Task(name='b', instruction='x', done_when='d', model='sonnet')])\n"
        )
        p = tmp_path / "mixed.py"
        p.write_text(content, encoding="utf-8")
        monkeypatch.setenv("CLAUDECODE", "1")
        exit_code = main(["run", str(p)])
        assert exit_code == EXIT_FAILURE, "mixed round has a claude-bound task — guard must hold"


# -- sig: mgh-6201.cd.bd955f.6f1d.9d8f32
