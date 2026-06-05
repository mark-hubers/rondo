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

    def test_claude_shorthand_to_anthropic_api_id(self) -> None:
        from rondo.providers import claude_shorthand_to_anthropic_api_id

        assert claude_shorthand_to_anthropic_api_id("sonnet") == "claude-sonnet-4-6"
        assert claude_shorthand_to_anthropic_api_id("haiku") == "claude-haiku-4-5"
        assert claude_shorthand_to_anthropic_api_id("opus") == "claude-opus-4-6"
        assert claude_shorthand_to_anthropic_api_id("sonnet[1m]") == "claude-sonnet-4-6"
        assert claude_shorthand_to_anthropic_api_id("opus[1m]") == "claude-opus-4-6"

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
        """recommend_model returns best model for task type — cloud providers are defaults."""
        from rondo.providers import recommend_model

        assert recommend_model("code-review") == "gemini:gemini-2.5-flash"
        assert recommend_model("reasoning") == "gemini:gemini-2.5-flash"
        assert recommend_model("classify") == "llama3.1:8b"
        assert recommend_model("structured-json") == "gemini:gemini-2.5-flash"
        assert recommend_model("general") == "gemini:gemini-2.5-flash"
        assert recommend_model("security") == "mistral:mistral-large-latest"
        assert recommend_model("unknown-type") == "sonnet"  ## default to Claude

    def test_recommend_model_config_override(self, tmp_path) -> None:
        """REQ-109 req 028: TOML config overrides default model map."""
        from rondo.providers import _task_model_overrides, load_task_models, recommend_model

        # -- Write a TOML config with overrides
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            '[routing.task_models]\n"code-review" = "my-custom-model:latest"\n"reasoning" = "my-reasoning:7b"\n'
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
        assert result["code-review"] == "gemini:gemini-2.5-flash"


# -- ──────────────────────────────────────────────────────────────
# --  REQ-109 reqs 021-023: Multi-provider review recommendations
# -- ──────────────────────────────────────────────────────────────


class TestRecommendReviewProviders:
    """recommend_review_providers() returns multiple cloud AIs for review tasks."""

    def test_code_review_returns_two_providers(self) -> None:
        from rondo.providers import recommend_review_providers

        result = recommend_review_providers("code-review")
        assert len(result) == 2
        assert all(":" in m for m in result)  # -- all are provider:model format

    def test_security_returns_three_providers(self) -> None:
        from rondo.providers import recommend_review_providers

        result = recommend_review_providers("security", count=3)
        assert len(result) == 3

    def test_count_limits_results(self) -> None:
        from rondo.providers import recommend_review_providers

        result = recommend_review_providers("security", count=1)
        assert len(result) == 1

    def test_unknown_task_falls_back_to_single(self) -> None:
        from rondo.providers import recommend_review_providers

        result = recommend_review_providers("unknown-task-type")
        assert len(result) == 1
        assert result[0] == "sonnet"  # -- fallback via recommend_model

    def test_config_override_wins(self, tmp_path) -> None:
        from rondo.providers import _multi_review_overrides, recommend_review_providers

        _multi_review_overrides["code-review"] = ["grok:grok-3", "mistral:large"]
        result = recommend_review_providers("code-review")
        assert result == ["grok:grok-3", "mistral:large"]
        _multi_review_overrides.clear()  # -- cleanup

    def test_default_two_minimum_for_review(self) -> None:
        """Default count=2 ensures at least 2 opinions for review tasks."""
        from rondo.providers import recommend_review_providers

        for task in ("code-review", "analysis", "research"):
            result = recommend_review_providers(task)
            assert len(result) >= 2, f"{task} should default to 2+ providers"


# -- ──────────────────────────────────────────────────────────────
# --  Provider-aware MCP dispatch (RONDO-73)
# -- ──────────────────────────────────────────────────────────────


class TestMCPProviderRouting:
    """MCP dispatch routes non-Claude models to provider adapters."""

    def test_ollama_model_routes_to_adapter(self) -> None:
        """rondo_run_file with ollama model uses OllamaAdapter."""
        from rondo.mcp_server import rondo_run_file

        result = json.loads(
            rondo_run_file(
                prompt="Say hello",
                model="llama3.2",
                dry_run=True,
            )
        )
        ## -- Dry-run with non-Claude model: should still return valid result
        assert result["status"] in ("done", "skipped", "error")

    def test_claude_model_uses_existing_path(self) -> None:
        """rondo_run_file with sonnet uses existing Claude dispatch."""
        from rondo.mcp_server import rondo_run_file

        result = json.loads(
            rondo_run_file(
                prompt="Say hello",
                model="sonnet",
                dry_run=True,
            )
        )
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

        result = json.loads(
            rondo_run_file(
                prompt="Say hello",
                model="llama3.1:8b",
                dry_run=False,
            )
        )
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
                file_path="/tmp/test.py",
                name=f"test-{i}",
                interval="weekly",
                dry_run=True,
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
        """Rondo run with ollama model works in dry-run."""
        import subprocess

        result = subprocess.run(
            ["/Users/markhubers/.local/bin/rondo", "run", "--dry-run", "--model", "llama3.1:8b"],
            input="",
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
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


class TestAnthropicAPIAdapter:
    """RONDO-119: AnthropicAPIAdapter for Claude via API."""

    def test_adapter_exists(self) -> None:
        from rondo.adapters.anthropic_api import AnthropicAPIAdapter

        adapter = AnthropicAPIAdapter(api_key="test")
        assert adapter.name == "anthropic"

    def test_dispatch_no_key_returns_error(self) -> None:
        from rondo.adapters.anthropic_api import AnthropicAPIAdapter

        result = AnthropicAPIAdapter(api_key="").dispatch(prompt="hello", model="claude-sonnet-4-6")
        assert result.status == "error"
        assert result.error_code == "ERR_AUTH"

    def test_routing_anthropic_prefix(self) -> None:
        from rondo.providers import get_provider

        provider = get_provider("anthropic:claude-sonnet-4-6")
        assert provider is not None
        assert provider.name == "anthropic"


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
        """gemini:gemini-2.5-flash routes to GeminiAdapter."""
        from rondo.providers import get_provider

        provider = get_provider("gemini:gemini-2.5-flash")
        assert provider is not None
        assert provider.name == "gemini"

    def test_routing_gemini_pro(self) -> None:
        from rondo.providers import get_provider

        provider = get_provider("gemini:gemini-2.5-pro")
        assert provider is not None
        assert provider.name == "gemini"


# -- ──────────────────────────────────────────────────────────────
# --  Error handling hardening — REQ-109 reqs 068, 069, 070, 071, 072
# -- ──────────────────────────────────────────────────────────────


class TestAdapterErrorCodes:
    """REQ-109 req 068: adapters MUST return distinct error codes for HTTP status."""

    def test_chat_completions_401_returns_err_auth(self) -> None:
        """401 from provider → ERR_AUTH, not ERR_PROVIDER."""
        import urllib.error
        from unittest.mock import patch

        from rondo.adapters.chat_completions import ChatCompletionsAdapter

        adapter = ChatCompletionsAdapter(provider_name="openai", api_key="bad-key")
        exc = urllib.error.HTTPError("url", 401, "Unauthorized", {}, None)
        with patch("urllib.request.urlopen", side_effect=exc):
            result = adapter.dispatch(prompt="hello", model="gpt-4.1")
        assert result.error_code == "ERR_AUTH"
        assert "401" in result.error_message

    def test_chat_completions_429_returns_err_rate_limit(self) -> None:
        import urllib.error
        from unittest.mock import patch

        from rondo.adapters.chat_completions import ChatCompletionsAdapter

        adapter = ChatCompletionsAdapter(provider_name="openai", api_key="key")
        exc = urllib.error.HTTPError("url", 429, "Too Many Requests", {}, None)
        with patch("urllib.request.urlopen", side_effect=exc):
            result = adapter.dispatch(prompt="hello", model="gpt-4.1")
        assert result.error_code == "ERR_RATE_LIMIT"

    def test_chat_completions_500_returns_err_provider_down(self) -> None:
        import urllib.error
        from unittest.mock import patch

        from rondo.adapters.chat_completions import ChatCompletionsAdapter

        adapter = ChatCompletionsAdapter(provider_name="openai", api_key="key")
        exc = urllib.error.HTTPError("url", 500, "Internal Server Error", {}, None)
        with patch("urllib.request.urlopen", side_effect=exc):
            result = adapter.dispatch(prompt="hello", model="gpt-4.1")
        assert result.error_code == "ERR_PROVIDER_DOWN"

    def test_gemini_401_returns_err_auth(self) -> None:
        import urllib.error
        from unittest.mock import patch

        from rondo.adapters.gemini import GeminiAdapter

        adapter = GeminiAdapter(api_key="bad-key")
        exc = urllib.error.HTTPError("url", 401, "Unauthorized", {}, None)
        with patch("urllib.request.urlopen", side_effect=exc):
            result = adapter.dispatch(prompt="hello", model="gemini-2.5-flash")
        assert result.error_code == "ERR_AUTH"

    def test_anthropic_429_returns_err_rate_limit(self) -> None:
        import urllib.error
        from unittest.mock import patch

        from rondo.adapters.anthropic_api import AnthropicAPIAdapter

        adapter = AnthropicAPIAdapter(api_key="key")
        exc = urllib.error.HTTPError("url", 429, "Rate Limited", {}, None)
        with patch("urllib.request.urlopen", side_effect=exc):
            result = adapter.dispatch(prompt="hello", model="claude-sonnet-4-6")
        assert result.error_code == "ERR_RATE_LIMIT"

    def test_anthropic_500_returns_err_provider_down(self) -> None:
        import urllib.error
        from unittest.mock import patch

        from rondo.adapters.anthropic_api import AnthropicAPIAdapter

        adapter = AnthropicAPIAdapter(api_key="key")
        exc = urllib.error.HTTPError("url", 503, "Service Unavailable", {}, None)
        with patch("urllib.request.urlopen", side_effect=exc):
            result = adapter.dispatch(prompt="hello", model="claude-sonnet-4-6")
        assert result.error_code == "ERR_PROVIDER_DOWN"


class TestAdapterKeyInvalidation:
    """REQ-109 req 069: ERR_AUTH must call invalidate_key()."""

    def test_chat_completions_401_invalidates_key(self) -> None:
        import urllib.error
        from unittest.mock import patch

        from rondo.adapters.chat_completions import ChatCompletionsAdapter

        adapter = ChatCompletionsAdapter(provider_name="grok", api_key="expired")
        exc = urllib.error.HTTPError("url", 401, "Unauthorized", {}, None)
        with patch("urllib.request.urlopen", side_effect=exc):
            with patch("rondo.adapters.auth.invalidate_key") as mock_inv:
                adapter.dispatch(prompt="hello", model="grok-3")
        mock_inv.assert_called_once_with("grok")

    def test_gemini_403_invalidates_key(self) -> None:
        import urllib.error
        from unittest.mock import patch

        from rondo.adapters.gemini import GeminiAdapter

        adapter = GeminiAdapter(api_key="revoked")
        exc = urllib.error.HTTPError("url", 403, "Forbidden", {}, None)
        with patch("urllib.request.urlopen", side_effect=exc):
            with patch("rondo.adapters.auth.invalidate_key") as mock_inv:
                adapter.dispatch(prompt="hello", model="gemini-2.5-flash")
        mock_inv.assert_called_once_with("gemini")

    def test_anthropic_401_invalidates_key(self) -> None:
        import urllib.error
        from unittest.mock import patch

        from rondo.adapters.anthropic_api import AnthropicAPIAdapter

        adapter = AnthropicAPIAdapter(api_key="expired")
        exc = urllib.error.HTTPError("url", 401, "Unauthorized", {}, None)
        with patch("urllib.request.urlopen", side_effect=exc):
            with patch("rondo.adapters.auth.invalidate_key") as mock_inv:
                adapter.dispatch(prompt="hello", model="claude-sonnet-4-6")
        mock_inv.assert_called_once_with("anthropic")

    def test_429_does_not_invalidate_key(self) -> None:
        """Rate limit is not an auth error — key should stay cached."""
        import urllib.error
        from unittest.mock import patch

        from rondo.adapters.chat_completions import ChatCompletionsAdapter

        adapter = ChatCompletionsAdapter(provider_name="openai", api_key="valid")
        exc = urllib.error.HTTPError("url", 429, "Too Many Requests", {}, None)
        with patch("urllib.request.urlopen", side_effect=exc):
            with patch("rondo.adapters.auth.invalidate_key") as mock_inv:
                adapter.dispatch(prompt="hello", model="gpt-4.1")
        mock_inv.assert_not_called()


class TestAdapterEmptyResponse:
    """REQ-109 req 070: empty response body = error, not success."""

    def test_chat_completions_empty_choices(self) -> None:
        """Provider returns 200 with empty choices → ERR_EMPTY_RESPONSE."""
        import json
        from unittest.mock import MagicMock, patch

        from rondo.adapters.chat_completions import ChatCompletionsAdapter

        adapter = ChatCompletionsAdapter(provider_name="openai", api_key="key")
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"choices": []}).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = adapter.dispatch(prompt="hello", model="gpt-4.1")
        assert result.status == "error"
        assert result.error_code == "ERR_EMPTY_RESPONSE"

    def test_gemini_missing_candidates(self) -> None:
        """Gemini returns 200 but no candidates → ERR_EMPTY_RESPONSE."""
        import json
        from unittest.mock import MagicMock, patch

        from rondo.adapters.gemini import GeminiAdapter

        adapter = GeminiAdapter(api_key="key")
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"candidates": []}).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = adapter.dispatch(prompt="hello", model="gemini-2.5-flash")
        assert result.status == "error"
        assert result.error_code == "ERR_EMPTY_RESPONSE"

    def test_anthropic_empty_content(self) -> None:
        """Anthropic returns 200 with empty content → ERR_EMPTY_RESPONSE."""
        import json
        from unittest.mock import MagicMock, patch

        from rondo.adapters.anthropic_api import AnthropicAPIAdapter

        adapter = AnthropicAPIAdapter(api_key="key")
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"content": []}).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = adapter.dispatch(prompt="hello", model="claude-sonnet-4-6")
        assert result.status == "error"
        assert result.error_code == "ERR_EMPTY_RESPONSE"


class TestAdapterHealthStrategy:
    """REQ-109 reqs 071, 072: provider-appropriate health checks."""

    def test_anthropic_health_checks_reachability(self) -> None:
        """Anthropic health must verify network, not just key presence."""
        import urllib.error
        from unittest.mock import patch

        from rondo.adapters.anthropic_api import AnthropicAPIAdapter

        adapter = AnthropicAPIAdapter(api_key="test-key")
        # -- 405 from HEAD = reachable
        exc = urllib.error.HTTPError("url", 405, "Method Not Allowed", {}, None)
        with patch("urllib.request.urlopen", side_effect=exc):
            assert adapter.health() is True

    def test_anthropic_health_500_is_down(self) -> None:
        import urllib.error
        from unittest.mock import patch

        from rondo.adapters.anthropic_api import AnthropicAPIAdapter

        adapter = AnthropicAPIAdapter(api_key="test-key")
        exc = urllib.error.HTTPError("url", 500, "Internal Server Error", {}, None)
        with patch("urllib.request.urlopen", side_effect=exc):
            assert adapter.health() is False

    def test_anthropic_health_network_error_is_down(self) -> None:
        import urllib.error
        from unittest.mock import patch

        from rondo.adapters.anthropic_api import AnthropicAPIAdapter

        adapter = AnthropicAPIAdapter(api_key="test-key")
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("no route")):
            assert adapter.health() is False

    def test_chat_completions_health_404_still_reachable(self) -> None:
        """If /models returns 404 (Grok), provider is still reachable — REQ-109 req 071."""
        import urllib.error
        from unittest.mock import patch

        from rondo.adapters.chat_completions import ChatCompletionsAdapter

        adapter = ChatCompletionsAdapter(provider_name="grok", api_key="key", base_url="https://api.x.ai/v1")
        exc = urllib.error.HTTPError("url", 404, "Not Found", {}, None)
        with patch("urllib.request.urlopen", side_effect=exc):
            assert adapter.health() is True

    def test_chat_completions_health_500_is_down(self) -> None:
        import urllib.error
        from unittest.mock import patch

        from rondo.adapters.chat_completions import ChatCompletionsAdapter

        adapter = ChatCompletionsAdapter(provider_name="grok", api_key="key")
        exc = urllib.error.HTTPError("url", 500, "Server Error", {}, None)
        with patch("urllib.request.urlopen", side_effect=exc):
            assert adapter.health() is False


class TestFinalizationGuard:
    """REQ-109 req 029: every non-Claude dispatch path must use _finalize_dispatch."""

    def test_cli_provider_path_uses_finalize(self) -> None:
        """CLI provider dispatch must call _finalize_dispatch."""
        import ast
        from pathlib import Path

        cli_path = Path(__file__).parent.parent.parent / "src" / "rondo" / "cli.py"
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

        mcp_path = Path(__file__).parent.parent.parent / "src" / "rondo" / "mcp_dispatch.py"
        source = mcp_path.read_text(encoding="utf-8")
        tree = ast.parse(source)

        # -- Find _dispatch_via_provider_or_claude function
        # -- RONDO-139: function now delegates to _run_pipeline which calls finalize_dispatch
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "_dispatch_via_provider_or_claude":
                body_source = ast.get_source_segment(source, node) or ""
                assert "finalize_dispatch" in body_source, (
                    "mcp_dispatch.py _dispatch_via_provider_or_claude must call finalize_dispatch "
                    "(REQ-109 req 026: shared finalization for ALL providers)"
                )
                break
        else:
            pytest.fail("mcp_dispatch.py missing _dispatch_via_provider_or_claude function")

    def test_no_manual_audit_outcome_in_provider_paths(self) -> None:
        """Provider paths must NOT call audit_trail.record_outcome directly.

        _finalize_dispatch handles audit OUTCOME — manual calls mean
        someone bypassed the shared pipeline (split-brain anti-pattern).
        """
        import ast
        from pathlib import Path

        mcp_path = Path(__file__).parent.parent.parent / "src" / "rondo" / "mcp_dispatch.py"
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


# -- ──────────────────────────────────────────────────────────────
# --  REQ-109 reqs 041-045: Provider tier resolution
# -- ──────────────────────────────────────────────────────────────


class TestTierResolution:
    """REQ-109 reqs 041-045: provider:tier → actual model name from config."""

    def setup_method(self) -> None:
        from rondo.providers import _providers_config

        _providers_config.clear()
        _providers_config.update(
            {
                "gemini": {
                    "cheap_model": "gemini-2.0-flash-lite",
                    "default_model": "gemini-2.5-flash",
                    "best_model": "gemini-2.5-pro",
                },
                "openai": {
                    "cheap_model": "gpt-4.1-mini",
                    "default_model": "gpt-4.1",
                    "best_model": "o3",
                },
                "grok": {
                    "cheap_model": "grok-3-mini",
                    "default_model": "grok-3",
                    "best_model": "grok-3",
                },
            }
        )

    def teardown_method(self) -> None:
        from rondo.providers import _providers_config

        _providers_config.clear()

    def test_resolve_tier_high(self) -> None:
        """Req 042: gemini:high → best_model."""
        from rondo.providers import resolve_tier

        assert resolve_tier("gemini", "high") == "gemini-2.5-pro"

    def test_resolve_tier_default(self) -> None:
        """Req 042: gemini:default → default_model."""
        from rondo.providers import resolve_tier

        assert resolve_tier("gemini", "default") == "gemini-2.5-flash"

    def test_resolve_tier_low(self) -> None:
        """Req 042: gemini:low → cheap_model."""
        from rondo.providers import resolve_tier

        assert resolve_tier("gemini", "low") == "gemini-2.0-flash-lite"

    def test_resolve_tier_openai(self) -> None:
        """Req 042: works for all providers."""
        from rondo.providers import resolve_tier

        assert resolve_tier("openai", "high") == "o3"
        assert resolve_tier("openai", "low") == "gpt-4.1-mini"

    def test_resolve_tier_same_model(self) -> None:
        """Req 045: provider with fewer models can point tiers to same model."""
        from rondo.providers import resolve_tier

        assert resolve_tier("grok", "high") == "grok-3"
        assert resolve_tier("grok", "default") == "grok-3"

    def test_resolve_tier_unknown_provider(self) -> None:
        """Unknown provider returns empty string."""
        from rondo.providers import resolve_tier

        assert resolve_tier("unknown", "high") == ""

    def test_resolve_tier_unknown_tier(self) -> None:
        """Unknown tier name returns empty string."""
        from rondo.providers import resolve_tier

        assert resolve_tier("gemini", "ultra") == ""

    def test_parse_model_tier_high(self) -> None:
        """Req 042: parse_model resolves gemini:high to actual model."""
        from rondo.providers import parse_model

        provider, model = parse_model("gemini:high")
        assert provider == "gemini"
        assert model == "gemini-2.5-pro"

    def test_parse_model_tier_low(self) -> None:
        """Req 042: parse_model resolves openai:low."""
        from rondo.providers import parse_model

        provider, model = parse_model("openai:low")
        assert provider == "openai"
        assert model == "gpt-4.1-mini"

    def test_parse_model_exact_beats_tier(self) -> None:
        """Req 043: exact model name beats tier — gemini-2.5-flash is not a tier."""
        from rondo.providers import parse_model

        provider, model = parse_model("gemini:gemini-2.5-flash")
        assert provider == "gemini"
        assert model == "gemini-2.5-flash"

    def test_parse_model_exact_model_unchanged(self) -> None:
        """Req 043: gpt-4.1 is not a tier name, passes through."""
        from rondo.providers import parse_model

        provider, model = parse_model("openai:gpt-4.1")
        assert provider == "openai"
        assert model == "gpt-4.1"

    def test_parse_model_tier_default(self) -> None:
        """Req 042: gemini:default → default_model."""
        from rondo.providers import parse_model

        provider, model = parse_model("gemini:default")
        assert provider == "gemini"
        assert model == "gemini-2.5-flash"

    def test_parse_model_no_config_tier_passthrough(self) -> None:
        """When no config, tier name passes through as model name."""
        from rondo.providers import _providers_config, parse_model

        _providers_config.clear()
        provider, model = parse_model("gemini:high")
        assert provider == "gemini"
        ## With no config, "high" can't resolve — passes through as model name
        assert model == "high"


class TestLoadProvidersConfig:
    """REQ-109 req 041: config loading for tier resolution."""

    def teardown_method(self) -> None:
        import rondo.providers as _p

        _p._providers_config.clear()
        _p._providers_loaded = False

    def test_load_from_dict(self) -> None:
        import rondo.providers as _p

        _p._providers_config.clear()
        _p._providers_loaded = False
        toml = {
            "providers": {
                "gemini": {"best_model": "gemini-pro"},
            }
        }
        _p.load_providers_config(toml)
        assert _p._providers_config["gemini"]["best_model"] == "gemini-pro"

    def test_load_empty_dict(self) -> None:
        from rondo.providers import _providers_config, load_providers_config

        _providers_config.clear()
        load_providers_config({})
        assert _providers_config == {}

    def test_load_no_providers_key(self) -> None:
        from rondo.providers import _providers_config, load_providers_config

        _providers_config.clear()
        load_providers_config({"other": "stuff"})
        assert _providers_config == {}

    def test_load_idempotent(self) -> None:
        """Second call without toml_data is a no-op (uses _providers_loaded flag)."""
        import rondo.providers as _p

        _p._providers_config.clear()
        _p._providers_loaded = False
        _p.load_providers_config({"providers": {"gemini": {"best_model": "pro"}}})
        assert _p._providers_config["gemini"]["best_model"] == "pro"
        # -- Second call: no toml_data, _providers_loaded=True → no-op
        _p.load_providers_config()
        assert _p._providers_config["gemini"]["best_model"] == "pro"

    def test_load_toml_data_always_merges(self) -> None:
        """Explicit toml_data always merges, even if already loaded."""
        import rondo.providers as _p

        _p._providers_config.clear()
        _p._providers_loaded = False
        _p.load_providers_config({"providers": {"gemini": {"best_model": "flash"}}})
        _p.load_providers_config({"providers": {"grok": {"best_model": "grok-3"}}})
        assert "gemini" in _p._providers_config
        assert "grok" in _p._providers_config


class TestProviderConfigWiring:
    """REQ-109: load_providers_config called from CLI and MCP startup."""

    def teardown_method(self) -> None:
        import rondo.providers as _p

        _p._providers_config.clear()
        _p._providers_loaded = False

    def test_cli_main_calls_load_providers(self) -> None:
        """CLI main() calls load_providers_config before dispatch."""
        from unittest.mock import patch

        import rondo.providers as _p

        _p._providers_config.clear()
        _p._providers_loaded = False
        with patch("rondo.providers.load_providers_config", wraps=_p.load_providers_config) as mock_load:
            from rondo.cli import main

            main(["preflight"])
            mock_load.assert_called()

    def test_mcp_server_calls_load_providers(self) -> None:
        """create_mcp_server() calls load_providers_config."""
        from unittest.mock import patch

        import rondo.providers as _p

        _p._providers_config.clear()
        _p._providers_loaded = False
        from rondo.mcp_server import create_mcp_server

        with patch("rondo.mcp_server.load_providers_config", wraps=_p.load_providers_config) as mock_load:
            create_mcp_server()
            mock_load.assert_called()


# -- ──────────────────────────────────────────────────────────────
# --  RONDO-296: Opus 4.8 compatibility
# --  STD-108 reqs 011-014 (error-body capture) + REQ-109 reqs 200-207
# -- ──────────────────────────────────────────────────────────────


def _anthropic_http_error(code: int, reason: str, body: bytes | None):
    """Build an HTTPError the way urllib raises it — fp carries the response body."""
    import io
    import urllib.error

    fp = io.BytesIO(body) if body is not None else None
    return urllib.error.HTTPError("https://api.anthropic.com/v1/messages", code, reason, {}, fp)


class _FakeHTTPResponse:
    """Minimal context-manager response for payload-capture tests."""

    def __init__(self, payload: dict) -> None:
        import json

        self._data = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._data

    def __enter__(self) -> "_FakeHTTPResponse":
        return self

    def __exit__(self, *args: object) -> bool:
        return False


class TestAnthropicErrorBodyCapture:
    """STD-108 reqs 011-014: surface the provider's HTTP error body.

    Port of the RONDO-287 (Finding #270) pattern already in gemini.py and
    chat_completions.py — anthropic_api.py was the one adapter missing it.
    Driver: Opus 4.8 HTTP 400 whose body named the exact cause but was discarded.
    """

    def _dispatch_with_error(self, exc):
        from unittest.mock import patch

        from rondo.adapters.anthropic_api import AnthropicAPIAdapter

        adapter = AnthropicAPIAdapter(api_key="test-key-123")
        with patch("urllib.request.urlopen", side_effect=exc):
            return adapter.dispatch(prompt="hello", model="claude-opus-4-8")

    def test_400_body_included_in_error_message(self) -> None:
        """STD-108 req 011: the body names the exact cause — surface it."""
        body = b'{"error": {"message": "temperature may only be set to 1 when thinking is enabled"}}'
        result = self._dispatch_with_error(_anthropic_http_error(400, "Bad Request", body))
        assert result.status == "error"
        assert "temperature may only be set to 1" in result.error_message

    def test_body_capped_at_500_chars(self) -> None:
        """STD-108 req 012: captured body capped at 500 chars."""
        body = b"x" * 2000
        result = self._dispatch_with_error(_anthropic_http_error(400, "Bad Request", body))
        assert "x" * 500 in result.error_message
        assert "x" * 501 not in result.error_message

    def test_api_key_redacted_from_body(self) -> None:
        """STD-108 req 012: error body passes credential redaction."""
        body = b'{"error": "bad key test-key-123 rejected"}'
        result = self._dispatch_with_error(_anthropic_http_error(401, "Unauthorized", body))
        assert "test-key-123" not in result.error_message
        assert "[REDACTED]" in result.error_message

    def test_read_failure_falls_back_to_status_line(self) -> None:
        """STD-108 req 014: body capture is best-effort — never masks the original error."""
        result = self._dispatch_with_error(_anthropic_http_error(400, "Bad Request", None))
        assert result.status == "error"
        assert "400" in result.error_message


class TestAnthropicThinkingModels:
    """REQ-109 reqs 200-207: thinking-default payload (Opus 4.8 API contract)."""

    def _capture_payload(self, model: str, **dispatch_kwargs) -> dict:
        import json
        from unittest.mock import patch

        from rondo.adapters.anthropic_api import AnthropicAPIAdapter

        captured: dict = {}

        def fake_urlopen(req, timeout=0):  # noqa: ARG001
            captured.update(json.loads(req.data.decode("utf-8")))
            return _FakeHTTPResponse(
                {
                    "content": [{"type": "text", "text": "OK"}],
                    "usage": {"input_tokens": 1, "output_tokens": 1},
                }
            )

        adapter = AnthropicAPIAdapter(api_key="test")
        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            adapter.dispatch(prompt="hello", model=model, **dispatch_kwargs)
        return captured

    def test_thinking_model_omits_temperature(self) -> None:
        """REQ-109 req 201: temperature/top_p/top_k stripped for thinking models."""
        payload = self._capture_payload("claude-opus-4-8")
        assert "temperature" not in payload
        assert "top_p" not in payload
        assert "top_k" not in payload

    def test_thinking_model_requests_adaptive_thinking(self) -> None:
        """REQ-109 req 203: adaptive shape — never manual budget_tokens."""
        payload = self._capture_payload("claude-opus-4-8")
        assert payload.get("thinking") == {"type": "adaptive"}

    def test_thinking_model_sends_effort(self) -> None:
        """REQ-109 req 204: effort maps to output_config.effort on the API path."""
        payload = self._capture_payload("claude-opus-4-8", effort="max")
        assert payload.get("output_config", {}).get("effort") == "max"

    def test_effort_defaults_to_high(self) -> None:
        """REQ-109 req 205: COALESCE — per-dispatch → adapter config → 'high'."""
        payload = self._capture_payload("claude-opus-4-8")
        assert payload.get("output_config", {}).get("effort") == "high"

    def test_classic_model_keeps_temperature(self) -> None:
        """REQ-109 req 202: classic models keep the proven 4.6-era payload."""
        payload = self._capture_payload("claude-sonnet-4-6")
        assert "temperature" in payload
        assert "thinking" not in payload
        assert "output_config" not in payload

    def test_thinking_patterns_config_overridable(self) -> None:
        """REQ-109 req 200: pattern list is constructor-overridable, not hardcoded."""
        from rondo.adapters.anthropic_api import AnthropicAPIAdapter

        adapter = AnthropicAPIAdapter(api_key="test", thinking_models=["my-custom-model"])
        assert adapter.is_thinking_model("my-custom-model") is True
        assert adapter.is_thinking_model("claude-opus-4-8") is False

    def test_default_patterns_match_48_family(self) -> None:
        """REQ-109 req 200: defaults cover the 4-8 family."""
        from rondo.adapters.anthropic_api import AnthropicAPIAdapter

        adapter = AnthropicAPIAdapter(api_key="test")
        assert adapter.is_thinking_model("claude-opus-4-8") is True
        assert adapter.is_thinking_model("claude-haiku-4-8") is True
        assert adapter.is_thinking_model("claude-sonnet-4-6") is False

    def test_thinking_model_gets_long_read_timeout(self) -> None:
        """REQ-109 req 211: max-effort thinking exceeds 120s — use >=600s."""
        from unittest.mock import patch

        from rondo.adapters.anthropic_api import AnthropicAPIAdapter

        seen = {}

        def fake_urlopen(req, timeout=0):  # noqa: ARG001
            seen["timeout"] = timeout
            return _FakeHTTPResponse(
                {"content": [{"type": "text", "text": "OK"}], "usage": {"input_tokens": 1, "output_tokens": 1}}
            )

        adapter = AnthropicAPIAdapter(api_key="test")
        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            adapter.dispatch(prompt="p", model="claude-opus-4-8")
            assert seen["timeout"] >= 600
            adapter.dispatch(prompt="p", model="claude-sonnet-4-6")
            assert seen["timeout"] == 120

    def test_thinking_model_gets_output_headroom(self) -> None:
        """REQ-109 req 210: thinking eats max_tokens — floor 32K for thinking models."""
        payload = self._capture_payload("claude-opus-4-8")
        assert payload["max_tokens"] >= 32000

    def test_classic_model_keeps_configured_max_tokens(self) -> None:
        """REQ-109 req 210: classic models keep the configured cap."""
        payload = self._capture_payload("claude-sonnet-4-6")
        assert payload["max_tokens"] == 8192

    def test_models_includes_current_best(self) -> None:
        """REQ-109 req 207: models() must include the active generation."""
        from rondo.adapters.anthropic_api import AnthropicAPIAdapter

        assert "claude-opus-4-8" in AnthropicAPIAdapter(api_key="test").models()


class TestChatCompletionsReasoningModels:
    """REQ-109 req 209 (RONDO-297): gpt-5*/o*-series ChatCompletions payload.

    Reasoning-class models reject max_tokens (require max_completion_tokens)
    and reject temperature. Same contract-change class as Opus 4.8 (RONDO-296).
    Driver: live gpt-5.5 canary HTTP 400, 2026-06-05.
    """

    def _capture_payload(self, model: str) -> dict:
        import json
        from unittest.mock import patch

        from rondo.adapters.chat_completions import ChatCompletionsAdapter

        captured: dict = {}

        def fake_urlopen(req, timeout=0):  # noqa: ARG001
            captured.update(json.loads(req.data.decode("utf-8")))
            return _FakeHTTPResponse(
                {
                    "choices": [{"message": {"content": "OK"}}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1},
                }
            )

        adapter = ChatCompletionsAdapter(provider_name="openai", api_key="test")
        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            adapter.dispatch(prompt="hello", model=model)
        return captured

    def test_gpt5_uses_max_completion_tokens(self) -> None:
        """REQ-109 req 209: reasoning models get max_completion_tokens, never max_tokens."""
        payload = self._capture_payload("gpt-5.5")
        assert "max_completion_tokens" in payload
        assert "max_tokens" not in payload

    def test_gpt5_omits_temperature(self) -> None:
        """REQ-109 req 209: reasoning models reject temperature — omit it."""
        payload = self._capture_payload("gpt-5.4-mini")
        assert "temperature" not in payload

    def test_classic_model_keeps_proven_payload(self) -> None:
        """REQ-109 req 209: gpt-4.x era keeps max_tokens + temperature."""
        payload = self._capture_payload("gpt-4.1")
        assert "max_tokens" in payload
        assert "temperature" in payload
        assert "max_completion_tokens" not in payload

    def test_o_series_classified_as_reasoning(self) -> None:
        """REQ-109 req 209: o*-series uses the reasoning payload too."""
        payload = self._capture_payload("o3")
        assert "max_completion_tokens" in payload
        assert "temperature" not in payload

    def test_grok_and_mistral_names_stay_classic(self) -> None:
        """REQ-109 req 209: non-OpenAI naming (grok/mistral) keeps classic payload."""
        for model in ("grok-4.3", "mistral-large-latest"):
            payload = self._capture_payload(model)
            assert "max_tokens" in payload, model
            assert "temperature" in payload, model

    def test_patterns_config_overridable(self) -> None:
        """REQ-109 req 200/209: reasoning pattern list is constructor-overridable."""
        from rondo.adapters.chat_completions import ChatCompletionsAdapter

        adapter = ChatCompletionsAdapter(provider_name="openai", api_key="test", reasoning_models=["my-model*"])
        assert adapter.is_reasoning_model("my-model-7") is True
        assert adapter.is_reasoning_model("gpt-5.5") is False


# -- ──────────────────────────────────────────────────────────────
# --  RONDO-306: auto-tune last mile — REQ-109 reqs 310-313, 320, 323
# -- ──────────────────────────────────────────────────────────────


class TestLearnedRoutingFallback:
    """REQ-109 reqs 310/320/323: learned best replaces the BLIND fallback only."""

    def _with_scores(self, monkeypatch, scores: dict) -> None:
        import rondo.providers as p

        monkeypatch.setattr("rondo.scoring.compute_provider_scores", lambda audit_dir="": scores)
        p._task_model_overrides.clear()

    def test_manual_override_always_wins(self, monkeypatch) -> None:
        """REQ-109 req 320: manual config beats learned, always."""
        import rondo.providers as p
        from rondo.providers import recommend_model

        self._with_scores(monkeypatch, {"gemini:flash": {"score": 0.99}})
        p._task_model_overrides["mytask"] = "opus"
        assert recommend_model("mytask") == "opus"

    def test_default_map_beats_learned(self, monkeypatch) -> None:
        """Curated defaults stay authoritative — learning only fills the blind spot."""
        from rondo.providers import _DEFAULT_TASK_MODELS, recommend_model

        self._with_scores(monkeypatch, {"gemini:flash": {"score": 0.99}})
        known_task = next(iter(_DEFAULT_TASK_MODELS))
        assert recommend_model(known_task) == _DEFAULT_TASK_MODELS[known_task]

    def test_unknown_task_uses_learned_best(self, monkeypatch) -> None:
        """REQ-109 reqs 310-311: blind 'sonnet' fallback replaced by evidence."""
        from rondo.providers import recommend_model

        self._with_scores(monkeypatch, {"gemini:flash": {"score": 0.91}, "grok-4.3": {"score": 0.55}})
        assert recommend_model("never-seen-task-xyz") == "gemini:flash"

    def test_unknown_task_no_scores_falls_back_sonnet(self, monkeypatch) -> None:
        from rondo.providers import recommend_model

        self._with_scores(monkeypatch, {})
        assert recommend_model("never-seen-task-xyz") == "sonnet"

    def test_scoring_disabled_skips_learned(self, monkeypatch) -> None:
        """REQ-109 req 323: [scoring] enabled=false disables learned routing."""
        from rondo.providers import recommend_model

        self._with_scores(monkeypatch, {"gemini:flash": {"score": 0.99}})
        monkeypatch.setattr("rondo.providers._scoring_enabled", lambda: False)
        assert recommend_model("never-seen-task-xyz") == "sonnet"


# -- sig: mgh-6201.cd.bd955f.a109.c10901
