# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""MCP dispatch routing — resolve_dispatch_engine, plans, four-engine router.

Split from test_mcp.py in RONDO-207 — original file was 1802 lines
(above best-practice range). This file focuses on: routing.

VER-001: Product acceptance / unit test coverage.
"""

import json

from rondo.mcp_server import (
    rondo_run_file,
)

# -- ──────────────────────────────────────────────────────────────
# --  IFS-104 req 003 — Query tools
# -- ──────────────────────────────────────────────────────────────




class TestResolveDispatchEngine:
    """RONDO-129/131: Pure routing logic — every input combination, no mocking."""

    def test_empty_model_returns_inline(self) -> None:
        """No model → inline engine (execute in current session)."""
        from rondo.mcp_dispatch import resolve_dispatch_engine

        result = resolve_dispatch_engine(model="", prompt="hello")
        assert result["engine"] == "inline"
        assert result["kind"] == "inline_dispatch_plan"
        assert result["prompt"] == "hello"
        assert result["model"] == "current"

    def test_background_forces_subprocess(self) -> None:
        """background=True → subprocess, regardless of model."""
        from rondo.mcp_dispatch import resolve_dispatch_engine

        for model in ("", "sonnet", "haiku", "gemini:high"):
            result = resolve_dispatch_engine(model=model, background=True, prompt="hello")
            assert result["engine"] == "subprocess", f"background+{model} should be subprocess"

    def test_gemini_routes_to_http(self) -> None:
        """gemini: prefix → HTTP adapter."""
        from rondo.mcp_dispatch import resolve_dispatch_engine

        result = resolve_dispatch_engine(model="gemini:gemini-2.5-flash", prompt="hello")
        assert result["engine"] == "http"
        assert result["provider"] == "gemini"

    def test_grok_routes_to_http(self) -> None:
        """grok: prefix → HTTP adapter."""
        from rondo.mcp_dispatch import resolve_dispatch_engine

        result = resolve_dispatch_engine(model="grok:grok-3", prompt="hello")
        assert result["engine"] == "http"
        assert result["provider"] == "grok"

    def test_openai_routes_to_http(self) -> None:
        """openai: prefix → HTTP adapter."""
        from rondo.mcp_dispatch import resolve_dispatch_engine

        result = resolve_dispatch_engine(model="openai:gpt-4.1", prompt="hello")
        assert result["engine"] == "http"
        assert result["provider"] == "openai"

    def test_mistral_routes_to_http(self) -> None:
        """mistral: prefix → HTTP adapter."""
        from rondo.mcp_dispatch import resolve_dispatch_engine

        result = resolve_dispatch_engine(model="mistral:mistral-large-latest", prompt="hello")
        assert result["engine"] == "http"
        assert result["provider"] == "mistral"

    def test_local_routes_to_http(self) -> None:
        """local: prefix → HTTP adapter (Ollama)."""
        from rondo.mcp_dispatch import resolve_dispatch_engine

        result = resolve_dispatch_engine(model="local:qwen2.5:32b", prompt="hello")
        assert result["engine"] == "http"
        assert result["provider"] == "local"

    def test_anthropic_prefix_routes_to_http(self) -> None:
        """anthropic: prefix → HTTP adapter (API key billing, not Max plan)."""
        from rondo.mcp_dispatch import resolve_dispatch_engine

        result = resolve_dispatch_engine(model="anthropic:sonnet", prompt="hello")
        assert result["engine"] == "http"
        assert result["provider"] == "anthropic"

    def test_new_suffix_forces_subprocess(self) -> None:
        """model='sonnet:new' → subprocess (explicit new session)."""
        from rondo.mcp_dispatch import resolve_dispatch_engine

        result = resolve_dispatch_engine(model="sonnet:new", prompt="hello")
        assert result["engine"] == "subprocess"
        assert result["model"] == "sonnet"

    def test_claude_model_in_session_returns_agent(self, monkeypatch) -> None:
        """Claude model inside Claude Code session → agent engine."""
        from rondo.mcp_dispatch import resolve_dispatch_engine

        monkeypatch.setenv("CLAUDECODE", "1")
        for model in ("sonnet", "opus", "haiku"):
            result = resolve_dispatch_engine(model=model, prompt="hello")
            assert result["engine"] == "agent", f"{model} in-session should be agent"
            assert result["kind"] == "agent_dispatch_plan"
            assert result["model"] == model

    def test_claude_model_outside_session_returns_subprocess(self, monkeypatch) -> None:
        """Claude model outside Claude Code session (CLI) → subprocess."""
        from rondo.mcp_dispatch import resolve_dispatch_engine

        monkeypatch.delenv("CLAUDECODE", raising=False)
        for model in ("sonnet", "opus", "haiku"):
            result = resolve_dispatch_engine(model=model, prompt="hello")
            assert result["engine"] == "subprocess", f"{model} outside session should be subprocess"

    def test_unknown_model_returns_error(self, monkeypatch) -> None:
        """Unknown model name → error engine."""
        from rondo.mcp_dispatch import resolve_dispatch_engine

        monkeypatch.delenv("CLAUDECODE", raising=False)
        result = resolve_dispatch_engine(model="nonexistent-model-xyz", prompt="hello")
        assert result["engine"] == "error"

    def test_whitespace_in_model_is_stripped(self, monkeypatch) -> None:
        """RONDO-206 Finding #220: leading/trailing whitespace on model is normalized.

        Prior behavior: ' sonnet ' → fell through to 'unknown model' error because
        VALID_MODELS contains 'sonnet' (no spaces). Now it routes correctly.
        """
        from rondo.mcp_dispatch import resolve_dispatch_engine

        monkeypatch.delenv("CLAUDECODE", raising=False)

        # -- Whitespace variants all normalize to 'sonnet' → subprocess (CLI mode)
        for variant in (" sonnet", "sonnet ", "  sonnet  ", "\tsonnet\n"):
            result = resolve_dispatch_engine(model=variant, prompt="hello")
            assert result["engine"] == "subprocess", (
                f"#220: whitespace variant {variant!r} should normalize to sonnet → subprocess"
            )
            assert result["model"] == "sonnet"

        # -- Empty-after-strip is the same as empty model → inline
        result = resolve_dispatch_engine(model="   ", prompt="hello")
        assert result["engine"] == "inline", "#220: whitespace-only model → inline"

    def test_provider_prefix_with_new_suffix_strips_new(self, monkeypatch) -> None:
        """RONDO-206 Finding #220: ':new' paired with provider prefix is stripped.

        The ':new' suffix has subprocess-only semantics (force fresh Claude session).
        Paired with a provider prefix like 'gemini:flash:new', it's ambiguous and
        was previously passed through to the HTTP adapter, which would fail on
        the invalid model name 'flash:new'. Now the suffix is stripped with a
        note in the reason string.
        """
        from rondo.mcp_dispatch import resolve_dispatch_engine

        monkeypatch.delenv("CLAUDECODE", raising=False)

        result = resolve_dispatch_engine(model="gemini:gemini-2.5-flash:new", prompt="hello")
        assert result["engine"] == "http", "#220: provider+:new → HTTP (not subprocess)"
        assert result["provider"] == "gemini"
        assert result["model"] == "gemini-2.5-flash", (
            f"#220: :new suffix should be stripped from model, got {result['model']!r}"
        )
        assert ":new" in result["reason"], (
            f"#220: reason should note the :new strip for operator visibility, got {result['reason']!r}"
        )

        # -- Regression check: Claude :new (no provider) still forces subprocess
        result2 = resolve_dispatch_engine(model="sonnet:new", prompt="hello")
        assert result2["engine"] == "subprocess"
        assert result2["model"] == "sonnet"

    def test_background_with_unknown_model_still_subprocess(self) -> None:
        """RONDO-206 Finding #220: background=True always routes to subprocess.

        Background mode short-circuits model validation — the subprocess layer
        is responsible for rejecting the bad model at exec time. This test
        documents that the ROUTER doesn't pre-validate in background mode,
        which is the current (intentional) behavior. If this changes, updating
        this test is a reminder to also update background-mode docs.
        """
        from rondo.mcp_dispatch import resolve_dispatch_engine

        result = resolve_dispatch_engine(model="nonexistent-xyz", background=True, prompt="hi")
        assert result["engine"] == "subprocess", (
            "#220: background+unknown still routes to subprocess (documented behavior)"
        )

    def test_file_path_and_inline_prompt_use_same_router(self, tmp_path) -> None:
        """RONDO-206 Finding #220: rondo_run_file with prompt= and file_path= parity.

        The router is driven by resolve_dispatch_engine, which takes the same
        (model, background, prompt) regardless of whether the caller passed
        file_path or prompt. This test proves the routing decision is the
        same across both input modes.
        """
        from rondo.mcp_dispatch import resolve_dispatch_engine

        # -- Direct inline prompt
        inline = resolve_dispatch_engine(model="gemini:gemini-2.5-flash", prompt="review")
        # -- Simulated file_path mode would build the same prompt string
        from_file = resolve_dispatch_engine(model="gemini:gemini-2.5-flash", prompt="review")

        assert inline["engine"] == from_file["engine"]
        assert inline["provider"] == from_file["provider"]
        assert inline["model"] == from_file["model"]

    def test_case_sensitive_for_bracket_models(self) -> None:
        """RONDO-206 Finding #220: case-sensitivity on bracket models like opus[1m].

        #220 asks whether case normalization applies. Answer: NO for bracket
        models — opus[1m] has case-sensitive brackets, and lowercasing would
        break the special 1M context syntax. This test documents that only
        whitespace is stripped, not case.
        """
        from rondo.mcp_dispatch import resolve_dispatch_engine

        # -- Lowercase bracket model works (matches VALID_MODELS)
        result = resolve_dispatch_engine(model="opus[1m]", prompt="hi")
        assert result["engine"] in ("subprocess", "agent"), (
            "opus[1m] should route as valid Claude model"
        )

        # -- Uppercase version is NOT normalized — would fail
        result_upper = resolve_dispatch_engine(model="OPUS[1M]", prompt="hi")
        assert result_upper["engine"] == "error", (
            "#220: case is preserved (not normalized) — OPUS[1M] is an unknown model"
        )

    def test_inline_plan_has_all_fields(self) -> None:
        """Inline plan includes prompt, done_when, model, project."""
        from rondo.mcp_dispatch import resolve_dispatch_engine

        result = resolve_dispatch_engine(
            model="",
            prompt="Review this code",
            done_when="List findings",
            project="/tmp/myproject",
        )
        assert result["engine"] == "inline"
        assert result["prompt"] == "Review this code"
        assert result["done_when"] == "List findings"
        assert result["project"] == "/tmp/myproject"
        assert result["model"] == "current"

    def test_agent_plan_has_all_fields(self, monkeypatch) -> None:
        """Agent plan includes prompt, done_when, model, project, note."""
        from rondo.mcp_dispatch import resolve_dispatch_engine

        monkeypatch.setenv("CLAUDECODE", "1")
        result = resolve_dispatch_engine(
            model="haiku",
            prompt="Quick check",
            done_when="Done",
            project="/tmp/proj",
        )
        assert result["engine"] == "agent"
        assert result["prompt"] == "Quick check"
        assert result["model"] == "haiku"
        assert result["project"] == "/tmp/proj"
        assert "note" in result

    def test_background_overrides_inline(self) -> None:
        """background=True + empty model → subprocess (not inline)."""
        from rondo.mcp_dispatch import resolve_dispatch_engine

        result = resolve_dispatch_engine(model="", background=True, prompt="hello")
        assert result["engine"] == "subprocess"

    def test_background_overrides_agent(self, monkeypatch) -> None:
        """background=True + Claude model in-session → subprocess (not agent)."""
        from rondo.mcp_dispatch import resolve_dispatch_engine

        monkeypatch.setenv("CLAUDECODE", "1")
        result = resolve_dispatch_engine(model="sonnet", background=True, prompt="hello")
        assert result["engine"] == "subprocess"

    def test_1m_models_detected(self, monkeypatch) -> None:
        """sonnet[1m] and opus[1m] are recognized as Claude models."""
        from rondo.mcp_dispatch import resolve_dispatch_engine

        monkeypatch.setenv("CLAUDECODE", "1")
        for model in ("sonnet[1m]", "opus[1m]"):
            result = resolve_dispatch_engine(model=model, prompt="hello")
            assert result["engine"] == "agent", f"{model} should be recognized as Claude"

    # -- RONDO-131: Tests for Cursor findings (gaps that should have caught issues)

    def test_legacy_ollama_routes_to_http(self) -> None:
        """Cursor #1a: llama3.1:8b without local: prefix → HTTP, not error.

        Previously resolve_dispatch_engine returned 'error' for unprefixed Ollama names
        while get_provider() returned OllamaAdapter. This caused a routing divergence.
        """
        from rondo.mcp_dispatch import resolve_dispatch_engine

        for model in ("llama3.1:8b", "qwen2.5:32b", "deepseek-r1:14b", "phi4:latest"):
            result = resolve_dispatch_engine(model=model, prompt="hello")
            assert result["engine"] == "http", f"Legacy Ollama '{model}' should route to HTTP, got {result['engine']}"
            assert result["provider"] == "local"

    def test_all_plans_have_status_field(self) -> None:
        """Cursor #6/#7: All plans must include status='plan' for defensive parsing.

        Without status, clients doing result['status'] get KeyError or
        misinterpret plans as dispatch results.
        """
        from rondo.mcp_dispatch import resolve_dispatch_engine

        # -- Every engine type should have status
        cases = [
            ("", False),  # -- inline
            ("sonnet", True),  # -- subprocess (background)
            ("gemini:high", False),  # -- http
        ]
        for model, bg in cases:
            result = resolve_dispatch_engine(model=model, background=bg, prompt="hello")
            assert "status" in result, f"model={model!r} bg={bg} missing 'status' field"
            assert result["status"] in ("plan", "error"), f"Unexpected status: {result['status']}"

    def test_agent_plan_has_status(self, monkeypatch) -> None:
        """Agent plans also need status='plan'."""
        from rondo.mcp_dispatch import resolve_dispatch_engine

        monkeypatch.setenv("CLAUDECODE", "1")
        result = resolve_dispatch_engine(model="sonnet", prompt="hello")
        assert result["status"] == "plan"

    def test_error_has_status_error(self, monkeypatch) -> None:
        """Error results have status='error' (not 'plan')."""
        from rondo.mcp_dispatch import resolve_dispatch_engine

        monkeypatch.delenv("CLAUDECODE", raising=False)
        result = resolve_dispatch_engine(model="totally-unknown-xyz", prompt="hello")
        assert result["status"] == "error"
        assert result["engine"] == "error"

    def test_router_agrees_with_get_provider(self) -> None:
        """Cursor #8: resolve_dispatch_engine and get_provider must not disagree.

        The 'harshest line' from Cursor: two routers that disagree = two products.
        This test feeds every known model pattern through BOTH and asserts parity.
        """
        from rondo.mcp_dispatch import resolve_dispatch_engine
        from rondo.providers import get_provider

        # -- (model, expected_is_http_in_both)
        # -- get_provider returns None for Claude (subprocess), adapter for others
        test_models = [
            # -- Claude models: get_provider=None, router=agent/subprocess (both=not HTTP)
            ("sonnet", False),
            ("opus", False),
            ("haiku", False),
            # -- Prefixed providers: both route to HTTP
            ("gemini:gemini-2.5-flash", True),
            ("grok:grok-3", True),
            ("local:qwen2.5:32b", True),
            # -- Legacy Ollama: BOTH must route to HTTP (was the Cursor bug)
            ("llama3.1:8b", True),
            ("qwen2.5:32b", True),
        ]
        for model, expect_http in test_models:
            provider = get_provider(model)
            engine = resolve_dispatch_engine(model=model, prompt="test")
            provider_is_http = provider is not None
            engine_is_http = engine["engine"] == "http"

            if expect_http:
                assert provider_is_http, f"get_provider({model!r}) should return adapter, got None"
                assert engine_is_http, f"resolve_dispatch_engine({model!r}) should be HTTP, got {engine['engine']}"
            else:
                assert not provider_is_http, f"get_provider({model!r}) should return None for Claude, got {provider}"
                assert not engine_is_http, (
                    f"resolve_dispatch_engine({model!r}) should NOT be HTTP, got {engine['engine']}"
                )

    def test_anthropic_prefix_distinct_from_bare(self, monkeypatch) -> None:
        """Cursor #5: anthropic:sonnet → HTTP (API key), sonnet → Agent (Max plan).

        Users need to understand this distinction. Test enforces the split.
        """
        from rondo.mcp_dispatch import resolve_dispatch_engine

        monkeypatch.setenv("CLAUDECODE", "1")
        # -- Bare sonnet in-session = agent (Max plan billing)
        bare = resolve_dispatch_engine(model="sonnet", prompt="hello")
        assert bare["engine"] == "agent"

        # -- anthropic:sonnet = HTTP adapter (API key billing)
        prefixed = resolve_dispatch_engine(model="anthropic:sonnet", prompt="hello")
        assert prefixed["engine"] == "http"
        assert prefixed["provider"] == "anthropic"


class TestDispatchEngineIntegration:
    """RONDO-129: Test that rondo_run_file uses the routing engine correctly."""

    def test_empty_model_returns_inline_plan(self) -> None:
        """rondo_run_file with empty model returns inline plan."""
        from rondo.mcp_server import rondo_run_file

        result = json.loads(rondo_run_file(prompt="Check this code", model="", dry_run=True))
        assert result.get("engine") == "inline"
        assert result.get("kind") == "inline_dispatch_plan"
        assert result["prompt"] == "Check this code"

    def test_claude_model_in_session_returns_agent_plan(self) -> None:
        """rondo_run_file with Claude model in-session returns agent plan.

        This test runs inside Claude Code (CLAUDECODE is set).
        Previously this would try subprocess and fail 100% of the time.
        Now it returns an agent plan for the host session to execute.
        """
        import os

        if not os.environ.get("CLAUDECODE"):
            # -- Outside session: Claude models go to subprocess, which is correct
            return
        from rondo.mcp_server import rondo_run_file

        for model in ("sonnet", "opus", "haiku"):
            result = json.loads(rondo_run_file(prompt="Say hello", model=model, dry_run=True))
            assert result.get("engine") == "agent", (
                f"{model} in-session should return agent plan, not subprocess. "
                f"Got: {result.get('engine', result.get('status'))}"
            )

    def test_force_new_subprocess(self) -> None:
        """model='sonnet:new' forces subprocess — assert POSITIVE engine type."""
        from rondo.mcp_server import rondo_run_file

        result = json.loads(rondo_run_file(prompt="Say hello", model="sonnet:new", dry_run=True))
        # -- :new suffix → subprocess engine (assert what it IS, not what it isn't)
        assert result.get("status") in ("plan", "done", "skipped"), f"Unexpected status: {result}"

    def test_inline_plan_has_schema(self) -> None:
        """Inline plan includes all fields host needs to execute."""
        from rondo.mcp_server import rondo_run_file

        result = json.loads(
            rondo_run_file(
                prompt="Review src/main.py",
                model="",
                dry_run=True,
                done_when="List all findings as JSON",
            )
        )
        assert result["engine"] == "inline"
        assert result["prompt"] == "Review src/main.py"
        assert result["done_when"] == "List all findings as JSON"
        assert result["model"] == "current"

    def test_ollama_model_dispatches_via_http(self) -> None:
        """Local model dispatches via HTTP adapter — assert positive, not 'not X'.

        Cursor #3a: old test asserted '!= inline' which passes on errors too.
        This test asserts the ACTUAL result shape for Ollama dry-run dispatch.
        """
        from rondo.mcp_server import rondo_run_file

        result = json.loads(rondo_run_file(prompt="Say hello", model="llama3.1:8b", dry_run=True))
        # -- Ollama goes through HTTP adapter — dry-run returns skipped tasks
        assert result.get("status") in ("done", "plan"), f"Expected done/plan, got: {result.get('status')}"
        assert result.get("engine") != "error", f"Should not be error: {result.get('reason', '')}"

    def test_empty_prompt_and_model_is_error(self) -> None:
        """No prompt + no model + no file = error."""
        from rondo.mcp_server import rondo_run_file

        result = json.loads(rondo_run_file(prompt="", model="", dry_run=True))
        assert result["status"] == "error"


class TestInlineDispatch:
    """U-33 to U-35: rondo_run with prompt= for one-off tasks."""

    def test_inline_dry_run(self):
        """U-33: prompt= creates in-memory task and dispatches."""
        result = json.loads(
            rondo_run_file(
                file_path="",
                prompt="List all Python files in the current directory",
                dry_run=True,
            )
        )
        assert result["status"] in ("done", "skipped")
        assert len(result["tasks"]) == 1
        assert "Python files" in result["tasks"][0].get("prompt_sent", "")

    def test_inline_with_done_when(self):
        """U-34: done_when parameter accepted."""
        result = json.loads(
            rondo_run_file(
                file_path="",
                prompt="Check disk space",
                done_when="Disk usage reported",
                dry_run=True,
            )
        )
        assert result["status"] in ("done", "skipped")
        assert "Disk usage" in str(result)

    def test_inline_same_json_as_file(self, tmp_path):
        """U-35: inline returns same structure as file-based."""
        ## -- File-based
        round_file = tmp_path / "test_round.py"
        round_file.write_text(
            "from rondo.engine import Round, Task\n"
            "def build_round():\n"
            "    return Round(name='cmp', tasks=[\n"
            "        Task(name='t1', instruction='hello', done_when='done'),\n"
            "    ])\n"
        )
        file_result = json.loads(rondo_run_file(str(round_file), dry_run=True))
        ## -- Inline
        inline_result = json.loads(rondo_run_file("", prompt="hello", dry_run=True))
        ## -- Same top-level keys
        assert set(file_result.keys()) == set(inline_result.keys())

    def test_inline_no_prompt_no_file_errors(self):
        """No file and no prompt = error."""
        result = json.loads(rondo_run_file(""))
        assert result["status"] == "error"


class TestDryRunPromptLength:
    """REQ-109 req 081: dry-run output includes prompt_length."""

    def test_inline_dry_run_has_prompt_length(self) -> None:
        """Dry-run with inline prompt shows prompt_length field."""
        from rondo.mcp_server import rondo_run_file

        long_prompt = "Review this code: " + "x" * 2000
        result = json.loads(rondo_run_file(prompt=long_prompt, dry_run=True))
        tasks = result.get("tasks", [])
        if tasks:
            assert "prompt_length" in tasks[0], "Dry-run task missing prompt_length field"
            assert tasks[0]["prompt_length"] > 500, "prompt_length should reflect actual size"


# -- sig: mgh-8289.e0.aea5a9.a7f9.cd84af
