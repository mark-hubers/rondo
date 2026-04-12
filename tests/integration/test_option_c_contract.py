# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Integration tests for RONDO-283 Option C contract behavior.

These tests call real ``rondo_run_file`` dispatch paths (no mocks).
Spec reference: VER-001.
"""

from __future__ import annotations

import json
import uuid

from rondo.dispatch_routing import resolve_dispatch_engine
from rondo.mcp_dispatch import rondo_run_file


def _run_json(**kwargs):
    return json.loads(rondo_run_file(**kwargs))


def _unique_prompt(label: str) -> str:
    return f"Return JSON only: {{\"label\":\"{label}\",\"id\":\"{uuid.uuid4().hex[:12]}\"}}"


def test_mcp_claude_model_returns_results_not_plan() -> None:
    result = _run_json(
        prompt=_unique_prompt("option-c-default"),
        model="sonnet",
        execution="",
        dry_run=False,
        _session=object(),
    )
    assert "tasks" in result and isinstance(result["tasks"], list)
    assert result.get("kind") != "inline_dispatch_plan"


def test_plan_only_returns_plan() -> None:
    result = _run_json(
        prompt=_unique_prompt("option-c-plan-only"),
        model="sonnet",
        execution="",
        plan_only=True,
        dry_run=False,
        _session=object(),
    )
    assert result.get("kind") == "inline_dispatch_plan"
    assert result.get("status") == "plan"


def test_explicit_subprocess_bypasses_option_c() -> None:
    result = _run_json(
        prompt=_unique_prompt("option-c-explicit-subprocess"),
        model="sonnet",
        execution="subprocess",
        dry_run=False,
        _session=object(),
    )
    assert "tasks" in result and isinstance(result["tasks"], list)
    assert result.get("kind") != "inline_dispatch_plan"


def test_fallback_on_inline_failure(monkeypatch) -> None:
    monkeypatch.setenv("RONDO_OPTION_C_FORCE_INLINE_FAIL", "1")
    result = _run_json(
        prompt=_unique_prompt("option-c-inline-fallback"),
        model="sonnet",
        execution="inline",
        dry_run=False,
        _session=object(),
    )
    assert "tasks" in result and isinstance(result["tasks"], list)
    warnings = result.get("warnings") or []
    assert any("inline_auto_execute_failed" in str(w) for w in warnings)


def test_http_provider_bypasses_option_c() -> None:
    route = resolve_dispatch_engine(model="gemini:flash", prompt="route-check")
    assert route.get("engine") == "http"
    result = _run_json(
        prompt=_unique_prompt("option-c-http-bypass"),
        model="gemini:flash",
        execution="",
        dry_run=False,
        _session=object(),
    )
    assert result.get("kind") != "inline_dispatch_plan"
    assert "tasks" in result and isinstance(result["tasks"], list)


def test_precedence_plan_only_beats_execution() -> None:
    result = _run_json(
        prompt=_unique_prompt("option-c-precedence"),
        model="sonnet",
        execution="subprocess",
        plan_only=True,
        dry_run=False,
        _session=object(),
    )
    assert result.get("kind") == "inline_dispatch_plan"
    assert result.get("status") == "plan"


# -- sig: mgh-bc0c.f2.fecb75.22ca.0d763a

