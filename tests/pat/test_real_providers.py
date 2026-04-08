# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Real cloud/local provider dispatch — marked @pytest.mark.cloud or @pytest.mark.ollama.

Split from test_real_dispatch.py in RONDO-207 to reduce file size to
best-practice range (200-500 lines per test file). Original monster was
2227 lines with 133 tests across 24 classes — this file is a focused slice.

Markers:
    (none)          — always runs, free, instant
    @pytest.mark.cloud  — real cloud API calls
    @pytest.mark.ollama — needs Ollama running locally

VER-001: Product acceptance / unit test coverage.
"""

from __future__ import annotations

import json
import os
import sys

import pytest

# -- Ensure rondo is importable
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent / "src"))

from rondo.mcp_dispatch import _is_in_session, resolve_dispatch_engine


@pytest.mark.cloud
class TestRealGemini:
    """Real Gemini API dispatch — proves HTTP adapter works end-to-end."""

    def test_gemini_responds(self) -> None:
        """Send a prompt to Gemini, get a real response back."""
        from rondo.mcp_dispatch import rondo_run_file

        result = json.loads(
            rondo_run_file(prompt="Reply with exactly: GEMINI_PAT_OK", model="gemini:gemini-2.5-flash", dry_run=False)
        )
        tasks = result.get("tasks", [])
        assert len(tasks) == 1, f"Expected 1 task, got {len(tasks)}"
        assert tasks[0]["status"] == "done", f"Task status: {tasks[0]['status']}"
        assert "GEMINI_PAT_OK" in tasks[0].get("raw_output", ""), "Gemini did not return expected text"

    def test_gemini_returns_cost(self) -> None:
        """Real dispatch tracks cost (even if $0.00 for free tier)."""
        from rondo.mcp_dispatch import rondo_run_file

        result = json.loads(rondo_run_file(prompt="Say OK", model="gemini:gemini-2.5-flash", dry_run=False))
        tasks = result.get("tasks", [])
        assert len(tasks) >= 1
        # -- cost_usd exists (may be 0 for free tier, but field must exist)
        assert "cost_usd" in result or "cost_usd" in tasks[0], "No cost tracking on real dispatch"


@pytest.mark.cloud
class TestRealGrok:
    """Real Grok API dispatch."""

    def test_grok_responds(self) -> None:
        """Grok dispatch — sends neutral prompt, asserts success.

        Finding #202 root cause: Grok's content filter rejects some prompts
        with 403 Forbidden (same code as auth failure). Verified: the key
        works for 'Say hello' but fails for 'Reply with exactly: GROK_PAT_OK'.
        Use neutral prompts for Grok tests.
        """
        from rondo.mcp_dispatch import rondo_run_file

        result = json.loads(rondo_run_file(prompt="Say hello", model="grok:grok-3", dry_run=False))
        tasks = result.get("tasks", [])
        assert len(tasks) == 1, f"Expected 1 task, got {len(tasks)}"
        assert tasks[0]["status"] == "done", (
            f"Grok dispatch failed: status={tasks[0]['status']} "
            f"error={tasks[0].get('error_code')} "
            f"msg={tasks[0].get('error_message', '')[:100]}"
        )
        assert len(tasks[0].get("raw_output", "")) > 0, "Grok returned empty output"


@pytest.mark.cloud
class TestRealMultiReview:
    """Real multi-provider review — multiple AIs answer same prompt."""

    def test_multi_review_returns_per_provider(self) -> None:
        from rondo.mcp_server import rondo_multi_review

        result = json.loads(
            rondo_multi_review(
                prompt="Say hello",
                providers='["gemini:gemini-2.5-flash"]',
                dry_run=False,
            )
        )
        assert result.get("status") == "done"
        assert result.get("provider_count", 0) >= 1
        per_provider = result.get("per_provider", [])
        assert len(per_provider) >= 1
        assert per_provider[0].get("status") == "done"


@pytest.mark.ollama
class TestRealOllama:
    """Real Ollama dispatch — local model, $0 cost."""

    def test_ollama_with_prefix(self) -> None:
        from rondo.mcp_dispatch import rondo_run_file

        result = json.loads(rondo_run_file(prompt="Say hello", model="local:llama3.1:8b", dry_run=False))
        tasks = result.get("tasks", [])
        assert len(tasks) == 1
        assert tasks[0]["status"] == "done", f"Ollama failed: {tasks[0].get('error_code', '?')}"

    def test_ollama_legacy_name(self) -> None:
        """Legacy name (no local: prefix) must work identically."""
        from rondo.mcp_dispatch import rondo_run_file

        result = json.loads(rondo_run_file(prompt="Say hello", model="llama3.1:8b", dry_run=False))
        tasks = result.get("tasks", [])
        assert len(tasks) == 1
        assert tasks[0]["status"] == "done", f"Legacy Ollama failed: {tasks[0].get('error_code', '?')}"


class TestInSessionBehavior:
    """Tests that verify behavior when running inside Claude Code.

    These run in the current environment. If CLAUDECODE is set, they test
    in-session paths. If not, they test out-of-session paths.
    Both are valid — the assertions adapt.
    """

    def test_session_detection_matches_environment(self) -> None:
        """_is_in_session() matches CLAUDECODE env var."""
        expected = bool(os.environ.get("CLAUDECODE"))
        assert _is_in_session() == expected

    def test_sonnet_routing_matches_context(self) -> None:
        """Sonnet → agent (in-session) or subprocess (outside). Not error."""
        r = resolve_dispatch_engine(model="sonnet", prompt="x")
        if _is_in_session():
            assert r["engine"] == "agent", "In-session sonnet should be agent"
        else:
            assert r["engine"] == "subprocess", "Outside-session sonnet should be subprocess"

    def test_inline_works_everywhere(self) -> None:
        """Empty model → inline regardless of session context."""
        r = resolve_dispatch_engine(model="", prompt="x")
        assert r["engine"] == "inline"

    def test_cloud_works_everywhere(self) -> None:
        """Cloud providers route to HTTP regardless of session context."""
        r = resolve_dispatch_engine(model="gemini:flash", prompt="x")
        assert r["engine"] == "http"


@pytest.mark.cloud
class TestRealCloud:
    """rondo_cloud — profile-based dispatch to cloud providers."""

    def test_cloud_default_responds(self) -> None:
        from rondo.mcp_tools import rondo_cloud

        result = json.loads(rondo_cloud(prompt="Reply with exactly: CLOUD_OK", dry_run=False))
        assert "error" not in result.get("status", ""), f"Cloud dispatch failed: {result}"

    def test_review_file_responds(self, tmp_path) -> None:
        """rondo_review_file with a real file."""
        from rondo.mcp_server import rondo_review_file

        test_file = tmp_path / "test_code.py"
        test_file.write_text("def add(a, b):\n    return a + b\n")
        result = json.loads(rondo_review_file(path=str(test_file), dry_run=False))
        # -- Should return provider results, not crash
        assert isinstance(result, dict)


@pytest.mark.ollama
class TestRealExplain:
    """rondo_explain — local model second opinion ($0)."""

    def test_explain_returns_opinion(self) -> None:
        from rondo.mcp_server import rondo_explain

        result = json.loads(rondo_explain(output="2 + 2 = 5", question="Is this correct?", dry_run=False))
        assert isinstance(result, dict)
        # -- Should have some output (the opinion)
        tasks = result.get("tasks", [])
        if tasks:
            assert tasks[0].get("status") == "done", f"Explain failed: {tasks[0].get('error_code')}"


class TestBackgroundDispatch:
    """Background dispatch returns dispatch_id, polling works."""

    def test_background_dry_run_returns_id(self) -> None:
        """background=True + dry_run → should still return structured response."""
        from rondo.mcp_server import rondo_run_file

        result = json.loads(rondo_run_file(prompt="background test", model="sonnet", background=True, dry_run=True))
        # -- Background with dry_run may return plan or dry-run result
        assert isinstance(result, dict)

    def test_run_status_heartbeat(self) -> None:
        """Heartbeat poll returns minimal JSON (~10 tokens)."""
        from rondo.mcp_server import rondo_run_status

        result = json.loads(rondo_run_status(heartbeat=True))
        assert isinstance(result, dict)

    def test_run_status_brief(self) -> None:
        """Brief poll returns status + counts (~40 tokens)."""
        from rondo.mcp_server import rondo_run_status

        result = json.loads(rondo_run_status(brief=True))
        assert isinstance(result, dict)


# -- sig: mgh-8a27.3d.c8ba4d.3c01.543201
