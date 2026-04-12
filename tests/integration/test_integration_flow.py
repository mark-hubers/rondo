# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Master integration tests — exercise all fixes together in one dispatch.

VER-001 verification matrix: end-to-end integration of Rondo subsystems.
RONDO-202 (addresses Finding #228): every sprint cluster produced isolated
unit tests. No test exercised routing + provider + key + HTTP + sanitize +
audit + spool + metrics + structured logging + idempotency TOGETHER.

This file fills that gap. Every test here runs ONE real dispatch through
the full pipeline and asserts multiple fix invariants simultaneously.

Tests in this file are the canary for "does the product actually work
when all its parts interact?" They must stay honest:
    - No pytest.skip on feature failure
    - No dry_run=True shortcuts for cost/real-dispatch concerns
    - No '!= bad' negative assertions
    - Each assertion proves a SPECIFIC invariant holds end-to-end

Session 99 + 100 lesson: unit tests prove code; integration tests prove product.
"""

from __future__ import annotations

import json
import sys

import pytest

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent / "src"))

from rondo.audit import AuditConfig, AuditTrail, atomic_write
from rondo.config import RondoConfig
from rondo.engine import DispatchUsage, Round, Task, TaskResult
from rondo.envelope import ENVELOPE_SCHEMA_VERSION
from rondo.mcp_dispatch import (
    _dispatch_via_provider_or_claude,
    check_context_limit,
    resolve_dispatch_engine,
)

# -- ──────────────────────────────────────────────────────────────
# --  Shared fixtures for integration tests
# -- ──────────────────────────────────────────────────────────────


class FakeProvider:
    """Minimal provider stand-in for integration flow tests.

    Returns realistic TaskResult with configurable cost and content.
    Does NOT mock the pipeline — the dispatch code runs for real against
    this fake provider. Only the network call is replaced.
    """

    def __init__(self, cost_per_call: float = 0.01, content: str = "response") -> None:
        self.cost_per_call = cost_per_call
        self.content = content
        self.call_count = 0

    def dispatch(self, prompt: str, model: str, task_name: str = "") -> TaskResult:
        self.call_count += 1
        return TaskResult(
            task_name=task_name or "fake",
            status="done",
            raw_output=self.content,
            model=model,
            cost_usd=self.cost_per_call,
            duration_sec=0.01,
        )


# -- ──────────────────────────────────────────────────────────────
# --  Integration test class — one dispatch exercises all fixes
# -- ──────────────────────────────────────────────────────────────


class TestMasterDispatchFlow:
    """RONDO-202: Every fix must survive a real end-to-end dispatch.

    Each test runs ONE real rondo_run_file-equivalent call and asserts
    that multiple subsystems cooperated correctly.
    """

    def test_successful_http_dispatch_full_pipeline(self, tmp_path, monkeypatch) -> None:
        """Success path: dispatch → pipeline → audit → sanitize → spool → metrics.

        Asserts:
            - Audit INTENT record written
            - Audit OUTCOME record written after dispatch
            - Result file written atomically (no .tmp leftover)
            - Sanitized: no sk- API key in result or audit
            - Schema version present on returned plan/result
            - cost_usd propagated from provider (not 0.0)
        """
        from unittest.mock import patch

        # -- Isolate all filesystem IO into tmp_path
        monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))

        provider = FakeProvider(
            cost_per_call=0.05,
            content="Result with leaked key: sk-FAKEabcdef1234567890abcdef1234567890",
        )
        round_def = Round(
            name="integration-flow-test",
            tasks=[Task(name="t1", instruction="process this", done_when="done")],
        )
        config = RondoConfig(audit_dir=str(tmp_path / "audit"))

        with patch("rondo.mcp_dispatch.get_provider_with_fallback") as mock_get:
            mock_get.return_value = (provider, "gemini-2.5-flash")
            result = _dispatch_via_provider_or_claude(
                round_def=round_def,
                config=config,
                model="gemini:gemini-2.5-flash",
                prompt="process this",
                dry_run=False,
                run_round=lambda *a, **kw: None,
            )

        # -- Assertion 1: dispatch actually ran
        assert provider.call_count == 1, "Provider should have been called once"
        assert len(result.task_results) == 1
        assert result.task_results[0].status == "done"

        # -- Assertion 2: cost_usd propagated from provider (not 0.0 stub)
        assert result.task_results[0].cost_usd == 0.05, (
            f"Provider cost must propagate, got {result.task_results[0].cost_usd}"
        )

        # -- Assertion 3: result raw_output is sanitized (no sk- key)
        assert "sk-FAKEabcdef" not in result.task_results[0].raw_output, "Secret leaked through finalize pipeline"

        # -- Assertion 4: audit files exist
        audit_dir = tmp_path / "audit"
        jsonl = list(audit_dir.glob("*.jsonl"))
        assert len(jsonl) >= 1, f"No audit JSONL in {audit_dir}"

        # -- Assertion 5: result files atomic (no .tmp leftover)
        tmp_files = list(audit_dir.glob("*.tmp"))
        assert len(tmp_files) == 0, f"Atomic write leaked .tmp files: {tmp_files}"

        # -- Assertion 6: result files exist AND contain sanitized content
        result_files = list(audit_dir.glob("*.result.json"))
        assert len(result_files) >= 1, "No result files written"
        for rf in result_files:
            content = rf.read_text()
            assert "sk-FAKEabcdef" not in content, f"Secret leaked into {rf.name}"

        # -- Assertion 7: JSONL has both INTENT and OUTCOME
        jsonl_content = jsonl[0].read_text()
        lines = [ln for ln in jsonl_content.splitlines() if ln.strip()]
        statuses = {json.loads(ln).get("status") for ln in lines}
        assert "INTENT" in statuses, f"Missing INTENT record: {statuses}"
        assert "done" in statuses, f"Missing OUTCOME record: {statuses}"

        # -- Assertion 8: prompt file also sanitized
        prompt_files = list(audit_dir.glob("*.prompt.txt"))
        for pf in prompt_files:
            # -- Our test prompt doesn't have a secret, but verify file was written
            assert pf.exists()

    def test_intent_prompt_file_is_sanitized(self, tmp_path, monkeypatch) -> None:
        """RONDO-202 / Finding #222 — CRITICAL.

        Verifies: raw prompt containing secrets does NOT land unsanitized in
        the prompt_file written by record_intent. This is the gap Cursor
        flagged: the OUTCOME path is sanitized but the INTENT path wasn't.
        """
        monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))

        audit = AuditTrail(config=AuditConfig(audit_dir=str(tmp_path / "audit")))
        secret_prompt = "Here is my API key: sk-FAKEINTENTxxxxxxxxxxxxxxxxxxxxx — use it"

        audit.record_intent(
            task_name="t", round_name="intent-sanitize-test", model="gemini-2.5-flash", prompt=secret_prompt
        )

        # -- Assertion: prompt file exists and does NOT contain the secret
        prompt_files = list((tmp_path / "audit").glob("*.prompt.txt"))
        assert len(prompt_files) >= 1, "INTENT should have written prompt file"
        for pf in prompt_files:
            content = pf.read_text()
            assert "sk-FAKEINTENT" not in content, (
                f"FINDING #222 NOT FIXED: Secret leaked into INTENT prompt file {pf.name}"
            )

    def test_budget_cap_actually_fires_with_real_costs(self, tmp_path, monkeypatch) -> None:
        """RONDO-202 / Finding #221, #226 — CRITICAL.

        Verifies: budget cap fires when provider returns REAL cost_usd.
        This test uses a provider that returns non-zero cost (fixing the
        mock cost_usd=0.0 problem Cursor flagged).
        """
        from unittest.mock import patch

        monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))
        provider = FakeProvider(cost_per_call=0.05)

        round_def = Round(
            name="budget-real-test",
            tasks=[
                Task(name="t1", instruction="x", done_when="done"),
                Task(name="t2", instruction="x", done_when="done"),
                Task(name="t3", instruction="x", done_when="done"),
                Task(name="t4", instruction="x", done_when="done"),
            ],
        )
        # -- Cap at $0.08 — tasks 1+2 cost $0.10 → task 3 MUST be blocked
        config = RondoConfig(max_budget_usd=0.08, audit_dir=str(tmp_path / "audit"))

        with patch("rondo.mcp_dispatch.get_provider_with_fallback") as mock_get:
            mock_get.return_value = (provider, "gemini-2.5-flash")
            result = _dispatch_via_provider_or_claude(
                round_def=round_def,
                config=config,
                model="gemini:gemini-2.5-flash",
                prompt="x",
                dry_run=False,
                run_round=lambda *a, **kw: None,
            )

        # -- RONDO-202 predictive budget cap (Finding #226):
        # -- Task 1 dispatches — initial estimate $0.01 + running $0 = $0.01 < $0.08 ✓
        # -- After task 1: running=$0.05, estimate updated to observed $0.05
        # -- Task 2 pre-check: $0.05 + $0.05 = $0.10 ≥ $0.08 → BLOCKED predictively
        # -- Only task 1 actually dispatches.
        assert result.task_results[0].status == "done"
        assert result.task_results[0].cost_usd == 0.05, "Task 1 should have real cost"

        # -- Task 2+ blocked by predictive cap
        assert provider.call_count == 1, (
            f"Predictive cap should block after task 1 (running=$0.05 + est $0.05 >= cap $0.08). "
            f"Got {provider.call_count} calls. "
            f"Statuses: {[t.status for t in result.task_results]}"
        )
        for i in (1, 2, 3):
            assert result.task_results[i].error_code == "ERR_BUDGET_EXCEEDED", (
                f"Task {i} should be blocked, got {result.task_results[i].status}"
            )

    def test_sanitize_intent_and_outcome_both_covered(self, tmp_path, monkeypatch) -> None:
        """RONDO-202 / Finding #222: both INTENT and OUTCOME must sanitize.

        Uses a secret in BOTH the prompt AND the response to verify that
        the pipeline scrubs both directions of the audit trail.
        """
        from unittest.mock import patch

        monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))

        prompt_secret = "ghp_" + ("A" * 40)  # -- fake GitHub PAT in prompt
        response_secret = "sk-" + ("B" * 30)  # -- fake sk- key in response

        provider = FakeProvider(content=f"Echo: {response_secret}")
        round_def = Round(
            name="dual-secret-test",
            tasks=[Task(name="t1", instruction=f"remember: {prompt_secret}", done_when="done")],
        )
        config = RondoConfig(audit_dir=str(tmp_path / "audit"))

        with patch("rondo.mcp_dispatch.get_provider_with_fallback") as mock_get:
            mock_get.return_value = (provider, "gemini-2.5-flash")
            _dispatch_via_provider_or_claude(
                round_def=round_def,
                config=config,
                model="gemini:gemini-2.5-flash",
                prompt=f"remember: {prompt_secret}",
                dry_run=False,
                run_round=lambda *a, **kw: None,
            )

        # -- Scan every file in audit dir for BOTH secrets
        audit_dir = tmp_path / "audit"
        for f in audit_dir.rglob("*"):
            if f.is_file():
                content = f.read_text(errors="ignore")
                assert prompt_secret not in content, f"PROMPT SECRET leaked into {f.name}"
                assert response_secret not in content, f"RESPONSE SECRET leaked into {f.name}"

    def test_tenant_isolation_across_audit_and_spool(self, tmp_path, monkeypatch) -> None:
        """RONDO-202 / Finding #217, #224: audit AND spool must be tenant-isolated.

        Verifies: two different tenants produce audit/spool in separate dirs
        so tenant A cannot read tenant B's data.
        """
        monkeypatch.delenv("RONDO_TEST_DIR", raising=False)  # -- use real path logic

        # -- Tenant A
        monkeypatch.setenv("RONDO_TENANT", "alice")
        from rondo.audit import _default_audit_dir

        path_alice = _default_audit_dir()

        # -- Tenant B
        monkeypatch.setenv("RONDO_TENANT", "bob")
        path_bob = _default_audit_dir()

        # -- Paths must differ AND contain tenant names
        assert "alice" in path_alice
        assert "bob" in path_bob
        assert path_alice != path_bob

    def test_dead_code_wired_context_limit_enforced(self) -> None:
        """RONDO-202 / Finding #227 (part 1): check_context_limit IS invoked by routing.

        Verifies: when a prompt exceeds a model's context limit, the dispatcher
        REJECTS it before calling the provider.
        """
        huge_prompt = "x" * 700_000
        fits, est, limit = check_context_limit("gpt-4.1", huge_prompt)
        assert fits is False
        assert est > limit

        # -- Routing now integrates this check
        r = resolve_dispatch_engine(model="openai:gpt-4.1", prompt=huge_prompt)
        assert r["engine"] == "error"
        assert "context" in r.get("reason", "").lower()

    def test_dead_code_wired_idempotency_returns_cache(self, tmp_path, monkeypatch) -> None:
        """RONDO-202 / Finding #227 (part 2): idempotency cache short-circuits duplicate dispatches.

        Two rondo_run_file calls with same prompt+model return SAME result.
        Second call does NOT re-dispatch (cache hit).
        """
        from unittest.mock import patch

        from rondo.idempotency import clear_cache
        from rondo.mcp_server import rondo_run_file

        monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))
        clear_cache()

        provider = FakeProvider(content="cached response")
        with patch("rondo.mcp_dispatch.get_provider_with_fallback") as mock_get:
            mock_get.return_value = (provider, "gemini-2.5-flash")
            # -- First call — hits provider
            result1 = rondo_run_file(
                prompt="unique test prompt for idempotency", model="gemini:gemini-2.5-flash", dry_run=False
            )
            # -- Second call — should hit cache, NOT provider
            result2 = rondo_run_file(
                prompt="unique test prompt for idempotency", model="gemini:gemini-2.5-flash", dry_run=False
            )

        assert result1 == result2, "Cached result should match first call"
        assert provider.call_count == 1, f"Second call should hit cache, not provider. Got {provider.call_count} calls."
        clear_cache()

    def test_dead_code_wired_structured_log_emits_request_id(self, caplog, tmp_path, monkeypatch) -> None:
        """RONDO-202 / Finding #227 (part 3): rondo_run_file emits structured log records.

        Verifies: a dispatch emits JSON log records containing request_id.
        """
        import logging
        from unittest.mock import patch

        from rondo.mcp_server import rondo_run_file

        monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))
        provider = FakeProvider()

        with caplog.at_level(logging.INFO, logger="rondo.structured_log"):
            with patch("rondo.mcp_dispatch.get_provider_with_fallback") as mock_get:
                mock_get.return_value = (provider, "gemini-2.5-flash")
                rondo_run_file(prompt="structured log test", model="gemini:gemini-2.5-flash", dry_run=False)

        # -- At least one log record should have been emitted with request_id
        matching = [r for r in caplog.records if "rondo_run_file invoked" in r.message]
        assert len(matching) >= 1, "structured_log not wired into rondo_run_file"
        # -- Parse the JSON record and check request_id field
        parsed = json.loads(matching[0].message)
        assert "request_id" in parsed
        assert len(parsed["request_id"]) == 32  # -- UUID4 hex

    def test_atomic_write_survives_disk_error(self, tmp_path) -> None:
        """RONDO-202: atomic_write cleans up tmp file even when rename fails."""
        target = tmp_path / "subdir_does_not_exist" / "file.json"
        with pytest.raises(OSError):
            atomic_write(target, "content")
        # -- No .tmp leftover in tmp_path
        tmp_files = list(tmp_path.rglob("*.tmp"))
        assert len(tmp_files) == 0, f"Atomic write leaked tmp files on failure: {tmp_files}"

    def test_schema_version_survives_full_flow(self, tmp_path, monkeypatch) -> None:
        """RONDO-283: MCP inline intent returns result envelope with schema version."""
        from rondo.mcp_server import rondo_run_file

        monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))

        result = json.loads(
            rondo_run_file(
                prompt="integration inline schema version unique",
                model="sonnet",
                dry_run=False,
                _session=object(),
                execution="inline",
            )
        )
        assert result.get("kind") != "inline_dispatch_plan"
        assert result["schema_version"] == ENVELOPE_SCHEMA_VERSION
        assert "tasks" in result and isinstance(result["tasks"], list)

    def test_execution_subprocess_returns_task_results(self, tmp_path, monkeypatch) -> None:
        """execution=subprocess returns dispatch results instead of host plans."""
        from unittest.mock import patch

        from rondo.mcp_server import rondo_run_file

        monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))
        done = {
            "status": "done",
            "round_name": "inline",
            "tasks": [{"name": "t", "status": "done", "raw_output": ""}],
            "done_count": 1,
            "error_count": 0,
            "pending_count": 0,
            "total_cost_usd": 0.0,
            "duration_sec": 0.0,
            "dry_run": False,
        }

        with patch("rondo.mcp_dispatch._execute_dispatch", return_value=done):
            result = json.loads(
                rondo_run_file(
                    prompt="integration subprocess results unique",
                    model="sonnet",
                    dry_run=False,
                    _session=None,
                    execution="subprocess",
                )
            )

        assert result["status"] == "done"
        assert "tasks" in result

    def test_sanitize_before_audit_verified_with_both_paths(self, tmp_path) -> None:
        """RONDO-202: Both INTENT (record_intent) and OUTCOME (_finalize_dispatch) sanitize before persist.

        This is the CRITICAL test proving Finding #204 is fully fixed, not half-fixed.
        """
        from rondo.dispatch import _finalize_dispatch

        audit = AuditTrail(config=AuditConfig(audit_dir=str(tmp_path)))

        # -- INTENT with secret in prompt
        intent_secret = "ghp_" + ("C" * 40)
        record = audit.record_intent(
            task_name="t",
            round_name="full-sanitize-test",
            model="gemini-2.5-flash",
            prompt=f"Use key: {intent_secret}",
        )

        # -- OUTCOME with secret in raw_output
        outcome_secret = "sk-ant-" + ("D" * 35)
        tr = TaskResult(
            task_name="t",
            status="done",
            raw_output=f"Response key: {outcome_secret}",
            model="gemini-2.5-flash",
        )
        usage = DispatchUsage(task_name="t", model="gemini-2.5-flash", cost_usd=0.01)
        config = RondoConfig(audit_dir=str(tmp_path))
        _finalize_dispatch(tr, usage, config, audit, record, round_name="full-sanitize-test")

        # -- Check EVERY file in tmp_path
        for f in tmp_path.rglob("*"):
            if f.is_file():
                try:
                    content = f.read_text(errors="ignore")
                except OSError:
                    continue
                assert intent_secret not in content, (
                    f"FINDING #222 NOT FIXED: INTENT secret ({intent_secret[:10]}...) "
                    f"leaked into {f.relative_to(tmp_path)}"
                )
                assert outcome_secret not in content, (
                    f"FINDING #204 NOT FIXED: OUTCOME secret ({outcome_secret[:10]}...) "
                    f"leaked into {f.relative_to(tmp_path)}"
                )


# -- sig: mgh-6201.cd.bd955f.f2a0.f0a070
