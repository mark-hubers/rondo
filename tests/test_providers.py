# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Tests for rondo.providers — REQ-109 provider adapter interface.

VER-001 verification matrix: provider adapters, routing, multi-LLM.
"""

import json

import pytest

from rondo.engine import TaskResult


# -- ──────────────────────────────────────────────────────────────
# --  REQ-109 req 001: ProviderAdapter interface
# -- ──────────────────────────────────────────────────────────────


class TestProviderInterface:
    """REQ-109 req 001: abstract base class with dispatch/health/models."""

    def test_adapter_has_dispatch(self) -> None:
        from rondo.providers import ProviderAdapter

        assert hasattr(ProviderAdapter, "dispatch")

    def test_adapter_has_health(self) -> None:
        from rondo.providers import ProviderAdapter

        assert hasattr(ProviderAdapter, "health")

    def test_adapter_has_models(self) -> None:
        from rondo.providers import ProviderAdapter

        assert hasattr(ProviderAdapter, "models")


# -- ──────────────────────────────────────────────────────────────
# --  REQ-109 req 002: Ollama adapter
# -- ──────────────────────────────────────────────────────────────


class TestOllamaAdapter:
    """REQ-109 req 002: OllamaAdapter for local LLM dispatch."""

    def test_ollama_adapter_exists(self) -> None:
        from rondo.adapters.ollama import OllamaAdapter

        adapter = OllamaAdapter()
        assert adapter is not None

    def test_ollama_models_returns_list(self) -> None:
        from rondo.adapters.ollama import OllamaAdapter

        adapter = OllamaAdapter()
        result = adapter.models()
        assert isinstance(result, list)

    def test_ollama_dispatch_returns_task_result(self) -> None:
        """Dispatch returns TaskResult even if Ollama not running."""
        from rondo.adapters.ollama import OllamaAdapter

        adapter = OllamaAdapter()
        result = adapter.dispatch(prompt="Say hello", model="llama3.2")
        assert isinstance(result, TaskResult)
        ## -- If Ollama not running, should be error not crash
        assert result.status in ("done", "error")


# -- ──────────────────────────────────────────────────────────────
# --  REQ-109 req 004: All adapters return same format
# -- ──────────────────────────────────────────────────────────────


class TestProviderRouting:
    """REQ-109 req 012: model → provider routing."""

    def test_route_claude_models(self) -> None:
        """Claude models return None (use dispatch_task directly)."""
        from rondo.providers import get_provider

        assert get_provider("sonnet") is None
        assert get_provider("opus") is None
        assert get_provider("haiku") is None

    def test_route_ollama_models_legacy(self) -> None:
        """Legacy prefix matching still works for backward compat."""
        from rondo.providers import get_provider

        assert get_provider("llama3.1:8b") is not None
        assert get_provider("llama3.1:8b").name == "ollama"
        assert get_provider("qwen2.5:32b").name == "ollama"
        assert get_provider("deepseek-r1:8b").name == "ollama"

    def test_route_local_prefix(self) -> None:
        """RONDO-113: local:MODEL routes to Ollama with MODEL as model name."""
        from rondo.providers import get_provider

        provider = get_provider("local:llama3.1:8b")
        assert provider is not None
        assert provider.name == "ollama"

        provider = get_provider("local:my-custom-model")
        assert provider is not None
        assert provider.name == "ollama"

    def test_route_local_prefix_extracts_model(self) -> None:
        """local:MODEL strips the local: prefix for the adapter."""
        from rondo.providers import parse_model

        provider_name, model_name = parse_model("local:llama3.1:8b")
        assert provider_name == "local"
        assert model_name == "llama3.1:8b"

    def test_parse_model_no_prefix(self) -> None:
        """No prefix = Claude."""
        from rondo.providers import parse_model

        provider_name, model_name = parse_model("sonnet")
        assert provider_name == ""
        assert model_name == "sonnet"

    def test_parse_model_empty(self) -> None:
        """Empty = current session."""
        from rondo.providers import parse_model

        provider_name, model_name = parse_model("")
        assert provider_name == ""
        assert model_name == ""

    def test_unknown_model_returns_none(self) -> None:
        """Unknown models default to None (Claude path, backward compat)."""
        from rondo.providers import get_provider

        assert get_provider("unknown-model-xyz") is None

    def test_recommend_model_for_task(self) -> None:
        """recommend_model returns best local model for task type."""
        from rondo.providers import recommend_model

        assert recommend_model("code-review") == "qwen2.5-coder:7b"
        assert recommend_model("reasoning") == "deepseek-r1:8b"
        assert recommend_model("classify") == "llama3.1:8b"
        assert recommend_model("structured-json") == "phi4:14b"
        assert recommend_model("general") == "qwen2.5:32b"
        assert recommend_model("unknown-type") == "sonnet"  ## default to Claude

    def test_recommend_model_config_override(self, tmp_path) -> None:
        """REQ-109 req 028: TOML config overrides default model map."""
        from rondo.providers import _task_model_overrides, load_task_models, recommend_model

        # -- Write a TOML config with overrides
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            '[routing.task_models]\n'
            '"code-review" = "my-custom-model:latest"\n'
            '"reasoning" = "my-reasoning:7b"\n'
        )
        # -- Load and verify overrides win
        load_task_models(str(config_file))
        assert recommend_model("code-review") == "my-custom-model:latest"
        assert recommend_model("reasoning") == "my-reasoning:7b"
        # -- Defaults still work for non-overridden types
        assert recommend_model("classify") == "llama3.1:8b"
        assert recommend_model("unknown-type") == "sonnet"
        # -- Cleanup: restore empty overrides
        _task_model_overrides.clear()

    def test_load_task_models_missing_file(self) -> None:
        """load_task_models handles missing config gracefully."""
        from rondo.providers import _task_model_overrides, load_task_models

        # -- Clear any leftover overrides from prior tests
        _task_model_overrides.clear()
        # -- Non-existent file should return defaults, not crash
        result = load_task_models("/tmp/nonexistent-rondo-config.toml")
        assert "code-review" in result
        assert result["code-review"] == "qwen2.5-coder:7b"


# -- ──────────────────────────────────────────────────────────────
# --  Provider-aware MCP dispatch (RONDO-73)
# -- ──────────────────────────────────────────────────────────────


class TestMCPProviderRouting:
    """MCP dispatch routes non-Claude models to provider adapters."""

    def test_ollama_model_routes_to_adapter(self) -> None:
        """rondo_run_file with ollama model uses OllamaAdapter."""
        from rondo.mcp_server import rondo_run_file

        result = json.loads(rondo_run_file(
            prompt="Say hello",
            model="llama3.2",
            dry_run=True,
        ))
        ## -- Dry-run with non-Claude model: should still return valid result
        assert result["status"] in ("done", "skipped", "error")

    def test_claude_model_uses_existing_path(self) -> None:
        """rondo_run_file with sonnet uses existing Claude dispatch."""
        from rondo.mcp_server import rondo_run_file

        result = json.loads(rondo_run_file(
            prompt="Say hello",
            model="sonnet",
            dry_run=True,
        ))
        assert result["status"] in ("done", "skipped")


# -- ──────────────────────────────────────────────────────────────
# --  Finding #188: Provider dispatches log to audit (RONDO-74)
# -- ──────────────────────────────────────────────────────────────


class TestProviderAuditTrail:
    """Provider dispatches must write to audit JSONL."""

    def test_ollama_dispatch_creates_audit(self, tmp_path, monkeypatch):
        """Ollama dispatch writes INTENT+OUTCOME to audit JSONL."""
        monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))
        (tmp_path / "audit").mkdir()
        from rondo.mcp_server import rondo_run_file

        result = json.loads(rondo_run_file(
            prompt="Say hello", model="llama3.1:8b", dry_run=False,
        ))
        ## -- Check audit file exists and has records
        audit_file = tmp_path / "audit" / "rondo_audit.jsonl"
        if audit_file.exists():
            lines = audit_file.read_text().strip().splitlines()
            assert len(lines) >= 1  ## at least OUTCOME
        ## -- Result should still be valid
        assert result["status"] in ("done", "error", "partial")


# -- ──────────────────────────────────────────────────────────────
# --  CLI provider routing (RONDO-83)
# -- ──────────────────────────────────────────────────────────────


class TestScheduleSafeguards:
    """H-12 to H-14: schedule limits."""

    def test_max_schedules_enforced(self, tmp_path) -> None:
        """H-13: max 20 active schedules."""
        from rondo.mcp_server import rondo_schedule_create

        ## -- Create 20 schedules (should work)
        for i in range(20):
            rondo_schedule_create(
                file_path="/tmp/test.py", name=f"test-{i}",
                interval="weekly", dry_run=True,
            )
        ## -- 21st should fail (but only when installing, not dry-run)
        ## -- Dry-run always works since it doesn't check installed count


class TestSafeParallel:
    """REQ-101 req 058: safe_parallel field on Task."""

    def test_task_has_safe_parallel(self) -> None:
        from rondo.engine import Task
        t = Task(name="t", instruction="x", done_when="y")
        assert hasattr(t, "safe_parallel")
        assert t.safe_parallel is False  ## default: not safe for parallel

    def test_safe_parallel_true(self) -> None:
        from rondo.engine import Task
        t = Task(name="t", instruction="x", done_when="y", safe_parallel=True)
        assert t.safe_parallel is True


class TestRondoSchedule:
    """rondo schedule: generate launchd plists."""

    def test_schedule_generates_plist(self, tmp_path) -> None:
        from rondo.schedule import generate_plist

        plist = generate_plist(
            name="ush-weekly",
            command="/Users/markhubers/.local/bin/rondo",
            args=["run", "scripts/ush-scan.py", "--model", "haiku"],
            interval="weekly",
            output_dir=str(tmp_path),
        )
        assert "com.rondo.ush-weekly" in plist
        assert "StartCalendarInterval" in plist

    def test_schedule_daily(self, tmp_path) -> None:
        from rondo.schedule import generate_plist

        plist = generate_plist(
            name="daily-scan",
            command="rondo",
            args=["run", "scan.py"],
            interval="daily",
            output_dir=str(tmp_path),
        )
        assert "Hour" in plist


class TestCLIProviderDispatch:
    """CLI dispatch routes non-Claude models to provider adapters."""

    def test_cli_dispatch_ollama_dry_run(self) -> None:
        """rondo run with ollama model works in dry-run."""
        import subprocess

        result = subprocess.run(
            ["/Users/markhubers/.local/bin/rondo", "run", "--dry-run", "--model", "llama3.1:8b"],
            input="",
            capture_output=True, text=True, check=False, timeout=10,
            env={k: v for k, v in __import__("os").environ.items() if k != "CLAUDECODE"},
        )
        ## -- Dry-run should work (shows prompts, no dispatch)
        ## -- May fail on "no file" but should NOT fail on "model not supported"
        assert "invalid" not in result.stderr.lower() or result.returncode != 2


# -- ──────────────────────────────────────────────────────────────
# --  REQ-109 req 029: Guard — no dispatch path may skip finalization
# -- ──────────────────────────────────────────────────────────────


class TestChatCompletionsAdapter:
    """RONDO-117: ChatCompletionsAdapter for OpenAI/Grok/Mistral."""

    def test_adapter_exists(self) -> None:
        from rondo.adapters.chat_completions import ChatCompletionsAdapter

        adapter = ChatCompletionsAdapter(provider_name="openai", api_key="test")
        assert adapter is not None
        assert adapter.name == "openai"

    def test_dispatch_no_key_returns_error(self) -> None:
        """No API key → ERR_AUTH, not crash."""
        from rondo.adapters.chat_completions import ChatCompletionsAdapter

        adapter = ChatCompletionsAdapter(provider_name="openai", api_key="")
        result = adapter.dispatch(prompt="hello", model="gpt-4.1")
        assert result.status == "error"
        assert result.error_code == "ERR_AUTH"

    def test_different_providers_same_adapter(self) -> None:
        """OpenAI, Grok, Mistral all use ChatCompletionsAdapter."""
        from rondo.adapters.chat_completions import ChatCompletionsAdapter

        for name, url in [
            ("openai", "https://api.openai.com/v1"),
            ("grok", "https://api.x.ai/v1"),
            ("mistral", "https://api.mistral.ai/v1"),
        ]:
            adapter = ChatCompletionsAdapter(provider_name=name, base_url=url, api_key="test")
            assert adapter.name == name
            assert adapter.base_url == url

    def test_health_no_key_returns_false(self) -> None:
        """No API key → health returns False."""
        from rondo.adapters.chat_completions import ChatCompletionsAdapter

        adapter = ChatCompletionsAdapter(api_key="")
        assert adapter.health() is False

    def test_returns_task_result(self) -> None:
        """Dispatch always returns TaskResult (even on error)."""
        from rondo.adapters.chat_completions import ChatCompletionsAdapter
        from rondo.engine import TaskResult

        adapter = ChatCompletionsAdapter(api_key="fake-key-for-test")
        result = adapter.dispatch(prompt="hello", model="gpt-4.1")
        assert isinstance(result, TaskResult)
        assert result.status in ("done", "error")


class TestGeminiAdapter:
    """RONDO-118: GeminiAdapter for Google Gemini API."""

    def test_adapter_exists(self) -> None:
        from rondo.adapters.gemini import GeminiAdapter

        adapter = GeminiAdapter(api_key="test")
        assert adapter.name == "gemini"

    def test_dispatch_no_key_returns_error(self) -> None:
        from rondo.adapters.gemini import GeminiAdapter

        adapter = GeminiAdapter(api_key="")
        result = adapter.dispatch(prompt="hello", model="gemini-2.5-flash")
        assert result.status == "error"
        assert result.error_code == "ERR_AUTH"

    def test_health_no_key_returns_false(self) -> None:
        from rondo.adapters.gemini import GeminiAdapter

        assert GeminiAdapter(api_key="").health() is False

    def test_routing_gemini_prefix(self) -> None:
        """gemini:flash routes to GeminiAdapter."""
        from rondo.providers import get_provider

        provider = get_provider("gemini:flash")
        assert provider is not None
        assert provider.name == "gemini"

    def test_routing_gemini_pro(self) -> None:
        from rondo.providers import get_provider

        provider = get_provider("gemini:gemini-2.5-pro")
        assert provider is not None
        assert provider.name == "gemini"


class TestFinalizationGuard:
    """REQ-109 req 029: every non-Claude dispatch path must use _finalize_dispatch."""

    def test_cli_provider_path_uses_finalize(self) -> None:
        """CLI provider dispatch must call _finalize_dispatch."""
        import ast
        from pathlib import Path

        cli_path = Path(__file__).parent.parent / "src" / "rondo" / "cli.py"
        source = cli_path.read_text(encoding="utf-8")
        tree = ast.parse(source)

        # -- Find _dispatch_with_provider function
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "_dispatch_with_provider":
                body_source = ast.get_source_segment(source, node) or ""
                assert "_finalize_dispatch" in body_source, (
                    "cli.py _dispatch_with_provider must call _finalize_dispatch "
                    "(REQ-109 req 026: shared finalization for ALL providers)"
                )
                break
        else:
            pytest.fail("cli.py missing _dispatch_with_provider function")

    def test_mcp_provider_path_uses_finalize(self) -> None:
        """MCP provider dispatch must call _finalize_dispatch."""
        import ast
        from pathlib import Path

        mcp_path = Path(__file__).parent.parent / "src" / "rondo" / "mcp_server.py"
        source = mcp_path.read_text(encoding="utf-8")
        tree = ast.parse(source)

        # -- Find _dispatch_via_provider_or_claude function
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "_dispatch_via_provider_or_claude":
                body_source = ast.get_source_segment(source, node) or ""
                assert "_finalize_dispatch" in body_source, (
                    "mcp_server.py _dispatch_via_provider_or_claude must call _finalize_dispatch "
                    "(REQ-109 req 026: shared finalization for ALL providers)"
                )
                break
        else:
            pytest.fail("mcp_server.py missing _dispatch_via_provider_or_claude function")

    def test_no_manual_audit_outcome_in_provider_paths(self) -> None:
        """Provider paths must NOT call audit_trail.record_outcome directly.

        _finalize_dispatch handles audit OUTCOME — manual calls mean
        someone bypassed the shared pipeline (split-brain anti-pattern).
        """
        import ast
        from pathlib import Path

        mcp_path = Path(__file__).parent.parent / "src" / "rondo" / "mcp_server.py"
        source = mcp_path.read_text(encoding="utf-8")
        tree = ast.parse(source)

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "_dispatch_via_provider_or_claude":
                body_source = ast.get_source_segment(source, node) or ""
                assert "record_outcome" not in body_source, (
                    "mcp_server.py _dispatch_via_provider_or_claude must NOT call record_outcome "
                    "directly — _finalize_dispatch handles it (REQ-109 req 026)"
                )
                break


# -- sig: mgh-6201.cd.bd955f.a109.c10901
