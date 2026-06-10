# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Unit tests for inline plan _host_instruction + execution_token — RONDO-294.

VER-001: Product acceptance / unit test coverage.

RONDO-294 adds two additive fields to every inline_dispatch_plan:
    1. `_host_instruction` — natural-language prompt telling the AI to execute
       the plan rather than dump it. Defense in depth: works even WITHOUT
       Caliber hooks rewriting the plan.
    2. `execution_token` — unique per-plan `[RONDO-EXEC:<hex>]` token. Caliber's
       Stop hook uses this to verify the SPECIFIC plan was executed
       (replaces pollution-prone global `[RONDO-EXECUTED]` token).

Schema bumped to "2". Additive changes — consumers on schema "1" ignore
unknown keys, so this is backward compatible.

These tests cover:
    1. _build_inline_plan emits _host_instruction + execution_token
    2. execution_token is unique per call (not a constant)
    3. execution_token matches the [RONDO-EXEC:<8-hex>] format
    4. _host_instruction tells the AI to execute + respond naturally
    5. Schema version bumped to "2"
    6. Other plan builders (_build_agent_plan, _build_subprocess_plan) are
       NOT affected (only inline plans get the host contract fields)
"""

from __future__ import annotations

import re

from rondo.dispatch_routing import (
    PLAN_SCHEMA_VERSION,
    _build_agent_plan,
    _build_inline_plan,
    _build_subprocess_plan,
    _make_execution_token,
)


class TestInlinePlanHostContract:
    """_build_inline_plan now emits host execution contract fields."""

    def test_inline_plan_has_host_instruction_field(self) -> None:
        plan = _build_inline_plan(prompt="review this", done_when="done", project="")
        assert "_host_instruction" in plan
        assert isinstance(plan["_host_instruction"], str)
        assert len(plan["_host_instruction"]) > 50, "host instruction too short"

    def test_host_instruction_says_execute_not_dump(self) -> None:
        plan = _build_inline_plan(prompt="p", done_when="d", project="")
        instruction = plan["_host_instruction"].lower()
        assert "execute" in instruction, f"host instruction missing 'execute': {plan['_host_instruction']!r}"
        ## Must tell AI NOT to show JSON
        assert "not" in instruction and "json" in instruction

    def test_host_instruction_mentions_execution_token(self) -> None:
        plan = _build_inline_plan(prompt="p", done_when="d", project="")
        assert "execution_token" in plan["_host_instruction"]

    def test_inline_plan_has_execution_token_field(self) -> None:
        plan = _build_inline_plan(prompt="p", done_when="d", project="")
        assert "execution_token" in plan
        assert isinstance(plan["execution_token"], str)

    def test_execution_token_matches_format(self) -> None:
        plan = _build_inline_plan(prompt="p", done_when="d", project="")
        token = plan["execution_token"]
        ## Format: [RONDO-EXEC:<8-hex>]
        assert re.match(r"^\[RONDO-EXEC:[0-9a-f]{8}\]$", token), f"bad token format: {token!r}"

    def test_execution_token_is_unique_per_plan(self) -> None:
        p1 = _build_inline_plan(prompt="p", done_when="d", project="")
        p2 = _build_inline_plan(prompt="p", done_when="d", project="")
        p3 = _build_inline_plan(prompt="p", done_when="d", project="")
        tokens = {p1["execution_token"], p2["execution_token"], p3["execution_token"]}
        ## 3 plans should produce 3 different tokens (8 hex = 2^32 combinations,
        ## collision probability negligible)
        assert len(tokens) == 3, f"tokens collided: {tokens}"

    def test_schema_version_bumped_for_host_fields(self) -> None:
        """The version pin tracks the CURRENT schema — bump-on-any-addition.

        RONDO-294 bumped 1->2 for the host fields; RONDO-394 (8.2) bumped
        2->3 for guarantees_scope/not_covered/dispatch_id correlation.
        """
        plan = _build_inline_plan(prompt="p", done_when="d", project="")
        assert plan["schema_version"] == "3"
        assert PLAN_SCHEMA_VERSION == "3"

    def test_inline_plan_preserves_existing_fields(self) -> None:
        """RONDO-294 is additive — no existing field was removed."""
        plan = _build_inline_plan(prompt="review", done_when="stop", project="proj-a")
        ## All pre-RONDO-294 fields still present
        assert plan["engine"] == "inline"
        assert plan["status"] == "plan"
        assert plan["kind"] == "inline_dispatch_plan"
        assert plan["prompt"] == "review"
        assert plan["done_when"] == "stop"
        assert plan["model"] == "current"
        assert plan["project"] == "proj-a"
        assert "reason" in plan


class TestOtherPlansUnaffected:
    """Only inline plans get the host contract fields — agent/subprocess do not."""

    def test_agent_plan_has_no_host_instruction(self) -> None:
        plan = _build_agent_plan(prompt="p", done_when="d", project="", model="sonnet")
        assert "_host_instruction" not in plan

    def test_agent_plan_has_no_execution_token(self) -> None:
        plan = _build_agent_plan(prompt="p", done_when="d", project="", model="sonnet")
        assert "execution_token" not in plan

    def test_subprocess_plan_has_no_host_instruction(self) -> None:
        plan = _build_subprocess_plan(model="sonnet", reason="test")
        assert "_host_instruction" not in plan

    def test_subprocess_plan_has_no_execution_token(self) -> None:
        plan = _build_subprocess_plan(model="sonnet", reason="test")
        assert "execution_token" not in plan


class TestMakeExecutionToken:
    """The token generator itself."""

    def test_token_format_parseable(self) -> None:
        token = _make_execution_token()
        assert token.startswith("[RONDO-EXEC:")
        assert token.endswith("]")

    def test_token_hex_length_is_8(self) -> None:
        token = _make_execution_token()
        ## Extract the hex part
        match = re.match(r"^\[RONDO-EXEC:([0-9a-f]+)\]$", token)
        assert match is not None
        hex_part = match.group(1)
        assert len(hex_part) == 8

    def test_tokens_collide_very_rarely(self) -> None:
        """Generate 1000 tokens — expect zero duplicates (2^32 space)."""
        tokens = {_make_execution_token() for _ in range(1000)}
        assert len(tokens) == 1000, f"unexpected collisions: {1000 - len(tokens)}"


# -- sig: mgh-6201.cd.bd955f.d294.f4b294
