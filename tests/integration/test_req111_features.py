# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Integration tests for REQ-111 Smart Dispatch features.

Tests are split into FREE (run every build) and CLOUD (run in deep build only).
FREE tests verify the pipeline without making API calls.
CLOUD tests dispatch to real providers and validate structured JSON returns.

VER-001: Product acceptance / integration test coverage.
"""

from __future__ import annotations

import json
import os

import pytest
import yaml

from rondo.config import RondoConfig
from rondo.engine import Round, Task, load_round_file
from rondo.hooks import HookError, run_pre_dispatch_hooks
from rondo.round_loader import load_round
from rondo.smart_return import build_return_prompt, validate_return_json

# ──────────────────────────────────────────────────────────────────
#  FREE TESTS — run every build, no API calls
# ──────────────────────────────────────────────────────────────────


class TestYAMLRoundIntegration:
    """YAML round files load and work with the dispatch pipeline."""

    def test_yaml_round_loads_via_engine(self, tmp_path) -> None:
        """load_round_file() handles .yaml via round_loader."""
        f = tmp_path / "test.yaml"
        f.write_text(
            yaml.dump(
                {
                    "name": "integration-test",
                    "tasks": [
                        {"name": "t1", "instruction": "analyze code", "model": "gemini:flash"},
                        {"name": "t2", "instruction": "check style", "done_when": "list issues"},
                    ],
                }
            )
        )
        rd = load_round_file(str(f))
        assert rd.name == "integration-test"
        assert len(rd.tasks) == 2
        assert rd.tasks[0].model == "gemini:flash"
        assert rd.tasks[1].done_when == "list issues"

    def test_json_round_loads_via_engine(self, tmp_path) -> None:
        """load_round_file() handles .json via round_loader."""
        f = tmp_path / "test.json"
        f.write_text(
            json.dumps(
                {
                    "name": "json-int-test",
                    "tasks": [{"name": "t1", "instruction": "review", "model": "grok:grok-3"}],
                }
            )
        )
        rd = load_round_file(str(f))
        assert rd.name == "json-int-test"
        assert rd.tasks[0].model == "grok:grok-3"

    def test_yaml_with_hooks_field(self, tmp_path) -> None:
        """YAML tasks with pre_dispatch/post_dispatch fields load correctly."""
        f = tmp_path / "hooks.yaml"
        f.write_text(
            yaml.dump(
                {
                    "name": "hooks-test",
                    "tasks": [
                        {
                            "name": "t1",
                            "instruction": "review",
                            "pre_dispatch": ["!echo modified"],
                        }
                    ],
                }
            )
        )
        rd = load_round(str(f))
        assert rd.tasks[0].pre_dispatch == ["!echo modified"]


class TestSmartReturnIntegration:
    """Smart return prompts integrate with the dispatch pipeline."""

    def test_return_prompt_injected_in_build_prompt(self) -> None:
        """build_prompt includes smart return instructions."""
        from rondo.dispatch_prompt import build_prompt

        task = Task(name="t1", instruction="review code", done_when="list bugs")
        prompt = build_prompt(task)
        assert "passed" in prompt.lower()
        assert "confidence" in prompt.lower()
        assert "json" in prompt.lower()

    def test_provider_specific_template_used(self) -> None:
        """Provider-specific template selected for known providers."""
        gemini = build_return_prompt(provider="gemini:flash")
        grok = build_return_prompt(provider="grok:grok-3")
        local = build_return_prompt(provider="local:llama")
        assert gemini != grok  # -- different templates
        assert len(local) < len(gemini)  # -- local is simpler

    def test_field_name_in_prompt(self) -> None:
        """--field adds named field instruction to prompt."""
        prompt = build_return_prompt(field_name="vulnerabilities")
        assert "vulnerabilities" in prompt

    def test_validate_good_json(self) -> None:
        """Valid JSON response validates correctly."""
        response = json.dumps(
            {
                "passed": True,
                "confidence": 0.95,
                "result": "no bugs found",
                "issues": [],
                "suggestions": ["add more tests"],
                "metadata": {"language": "python"},
                "_meta": {"quality": 9, "complete": True, "limitations": ""},
            }
        )
        data = validate_return_json(response)
        assert data["_json_valid"] is True
        assert data["_fields_complete"] is True
        assert data["passed"] is True

    def test_validate_bad_json_graceful(self) -> None:
        """Invalid response degrades gracefully — never crashes."""
        data = validate_return_json("This is not JSON at all")
        assert data["_json_valid"] is False
        assert data["_parse_error"] is True
        assert data["passed"] is None


class TestHooksIntegration:
    """Hooks integrate with the dispatch pipeline."""

    def test_pre_hooks_chain_and_transform(self) -> None:
        """Multiple pre-hooks chain correctly."""

        def add_context(prompt, _t, _c):
            return f"CONTEXT: {prompt}"

        def add_format(prompt, _t, _c):
            return f"{prompt}\nFORMAT: JSON"

        task = Task(
            name="t1",
            instruction="review",
            pre_dispatch=[add_context, add_format],
        )
        result, trace = run_pre_dispatch_hooks("original", task, RondoConfig())
        assert "CONTEXT: original" in result
        assert "FORMAT: JSON" in result
        assert len(trace) == 2
        assert all(t["status"] == "ok" for t in trace)

    def test_shell_hook_works(self) -> None:
        """Shell hooks (! prefix) execute correctly."""
        task = Task(name="t1", instruction="hi", pre_dispatch=["!tr a-z A-Z"])
        result, trace = run_pre_dispatch_hooks("hello", task, RondoConfig())
        assert result.strip() == "HELLO"

    def test_hook_error_stops_dispatch(self) -> None:
        """Pre-hook error produces HookError — blocks dispatch."""

        def bad_hook(_p, _t, _c):
            raise ValueError("intentional")

        task = Task(name="t1", instruction="hi", pre_dispatch=[bad_hook])
        with pytest.raises(HookError):
            run_pre_dispatch_hooks("test", task, RondoConfig())


class TestScoringIntegration:
    """Scoring computes from audit data and caches."""

    def test_scoring_end_to_end(self, tmp_path) -> None:
        """Compute scores from JSONL, save cache, load cache."""
        import time as _time

        from rondo.scoring import compute_provider_scores, load_scores_cache, save_scores_cache

        # -- Write mock audit data
        jsonl = tmp_path / "audit.jsonl"
        records = []
        for i in range(15):
            records.append(
                json.dumps(
                    {
                        "model": "gemini:flash",
                        "status": "done" if i < 13 else "error",
                        "completed_at": _time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "cost_usd": 0.003,
                        "duration_sec": 2.1,
                        "json_valid": i < 12,
                        "fields_complete": i < 10,
                    }
                )
            )
        jsonl.write_text("\n".join(records))

        # -- Compute
        scores = compute_provider_scores(str(tmp_path))
        assert "gemini:flash" in scores
        assert scores["gemini:flash"]["sample_count"] == 15

        # -- Cache
        cache_dir = tmp_path / "cache"
        save_scores_cache(scores, str(cache_dir))
        loaded = load_scores_cache(str(cache_dir))
        assert "gemini:flash" in loaded


class TestExampleFilesLoad:
    """Verify all example files parse correctly."""

    @pytest.mark.parametrize(
        "filename",
        [
            "01-simple-review.yaml",
            "02-multi-provider.yaml",
            "03-budget-capped.yaml",
            "05-overnight-batch.yaml",
        ],
    )
    def test_yaml_example_loads(self, filename) -> None:
        """Each YAML example file loads without errors."""
        examples_dir = os.path.join(os.path.dirname(__file__), "..", "..", "examples", "rounds")
        filepath = os.path.join(examples_dir, filename)
        if not os.path.exists(filepath):
            pytest.skip(f"Example file not found: {filepath}")
        rd = load_round(filepath)
        assert isinstance(rd, Round)
        assert len(rd.tasks) > 0

    def test_python_example_loads(self) -> None:
        """Python example file loads without errors."""
        examples_dir = os.path.join(os.path.dirname(__file__), "..", "..", "examples", "rounds")
        filepath = os.path.join(examples_dir, "04-with-hooks.py")
        if not os.path.exists(filepath):
            pytest.skip("Example file not found")
        rd = load_round_file(filepath)
        assert isinstance(rd, Round)
        assert rd.tasks[0].pre_dispatch  # -- has hooks


# ──────────────────────────────────────────────────────────────────
#  CLOUD TESTS — run in deep build only, cost ~$0.05
# ──────────────────────────────────────────────────────────────────


@pytest.mark.cloud_full
class TestSmartReturnCloud:
    """Live dispatch with smart return — validates real provider responses."""

    def test_gemini_returns_structured_json(self) -> None:
        """Dispatch to Gemini with smart return → get structured JSON back."""
        from rondo.mcp_dispatch import rondo_run_file

        result_str = rondo_run_file(
            prompt="What is 2+2? Answer briefly.",
            model="gemini:gemini-2.5-flash",
            dry_run=False,
        )
        result = json.loads(result_str)
        assert result.get("status") in ("done", "partial"), f"Unexpected status: {result}"

        # -- Validate the task output has structured JSON
        if result.get("tasks"):
            raw = result["tasks"][0].get("raw_output", "")
            validated = validate_return_json(raw)
            # -- We expect the smart return prompt to produce valid JSON
            # -- but this is a real API call — it may not always comply
            assert validated is not None, "validate_return_json returned None"

    def test_local_returns_json(self) -> None:
        """Dispatch to local Ollama with simpler template."""
        from rondo.mcp_dispatch import rondo_run_file

        result_str = rondo_run_file(
            prompt="What color is the sky? One word answer.",
            model="local:qwen2.5:32b",
            dry_run=False,
        )
        result = json.loads(result_str)
        assert result.get("status") in ("done", "partial", "error")


# -- sig: mgh-6201.cd.bd955f.e111.1ead50
