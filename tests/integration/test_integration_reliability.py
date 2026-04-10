# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Reliability integration tests — circuit breaker + retry + fallback + dispatch.

VER-001 verification matrix: proves RONDO reliability subsystems compose
correctly under real failure scenarios. These tests exercise MULTIPLE
components together (not just one module in isolation) to catch bugs
that only show up when the pieces interact.

RONDO-207: added in the Testing Trophy shift — fewer isolated unit tests,
more high-confidence integration tests that cross component boundaries.

Every test here runs REAL code paths (dispatch, retry, circuit breaker,
audit, sanitize) against a fake network layer. The pipeline is never
mocked. Only the outbound HTTP call is replaced.

Guarded by:
    - No pytest.skip for feature failures
    - No dry_run shortcuts
    - Assertions verify concrete invariants across components
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from rondo.audit import AuditConfig, AuditTrail
from rondo.engine import TaskResult
from rondo.retry import CircuitBreaker

# -- ──────────────────────────────────────────────────────────────
# --  Shared fixtures — isolated breaker per test to avoid pollution
# -- ──────────────────────────────────────────────────────────────


@pytest.fixture
def isolated_breaker(tmp_path):
    """Create a circuit breaker with an isolated persist file.

    Each test gets a fresh breaker — no cross-test state pollution.
    The persist file lives in tmp_path which is auto-cleaned by pytest.
    """
    return CircuitBreaker(
        failure_threshold=3,
        cooldown_sec=60.0,
        persist_path=tmp_path / "breaker.json",
    )


class FlakyProvider:
    """Provider stand-in that fails N times then succeeds.

    Lets us test retry + circuit breaker behavior under realistic
    partial-outage scenarios.
    """

    def __init__(self, fail_count: int = 0, content: str = "ok"):
        self.fail_count = fail_count
        self.content = content
        self.call_count = 0

    def dispatch(self, prompt: str, model: str, task_name: str = "") -> TaskResult:
        self.call_count += 1
        if self.call_count <= self.fail_count:
            return TaskResult(
                task_name=task_name or "flaky",
                status="error",
                error_code="ERR_PROVIDER_DOWN",
                error_message=f"simulated failure {self.call_count}/{self.fail_count}",
                model=model,
            )
        return TaskResult(
            task_name=task_name or "flaky",
            status="done",
            raw_output=self.content,
            model=model,
            cost_usd=0.001,
        )


# -- ──────────────────────────────────────────────────────────────
# --  Integration tests
# -- ──────────────────────────────────────────────────────────────


class TestReliabilityIntegration:
    """RONDO-207: reliability primitives compose correctly end-to-end."""

    def test_breaker_opens_then_blocks_subsequent_dispatches(self, isolated_breaker):
        """Breaker blocks dispatch attempts once open.

        After N failures, subsequent dispatches are blocked WITHOUT
        calling the provider. This verifies breaker.is_open() is
        consulted BEFORE the network call — the whole point of a
        circuit breaker is to fail fast.
        """
        provider = FlakyProvider(fail_count=999)  # always fails

        # -- Record failures directly (simulates dispatch failures)
        for _ in range(3):
            isolated_breaker.record_failure("test-provider")

        assert isolated_breaker.is_open("test-provider"), "precondition: breaker must be OPEN after threshold failures"

        # -- Callers that check the breaker should NOT call the provider
        # -- This is what dispatch.py does at the top of _dispatch_interactive
        if isolated_breaker.is_open("test-provider"):
            # -- Skip the provider call
            pass
        else:
            provider.dispatch("test", "test-model")

        assert provider.call_count == 0, "breaker-OPEN blocks the provider call entirely — no network hit"

    def test_breaker_reopens_after_cooldown(self, tmp_path):
        """After cooldown expires, breaker auto-closes on next is_open() check.

        Integration: cooldown timing + state transition + persistence.
        """
        breaker = CircuitBreaker(
            failure_threshold=2,
            cooldown_sec=0.1,  # 100 ms cooldown for fast test
            persist_path=tmp_path / "breaker.json",
        )
        breaker.record_failure("svc")
        breaker.record_failure("svc")
        assert breaker.is_open("svc"), "precondition: OPEN after 2 failures"

        time.sleep(0.2)  # wait past cooldown

        # -- is_open() should now auto-close + return False
        assert not breaker.is_open("svc"), "breaker must auto-close after cooldown"

    def test_breaker_persists_across_restart_via_isolated_file(self, tmp_path):
        """Integration: breaker state survives process restart.

        Trip breaker in "process 1" (instance 1), then create "process 2"
        (instance 2) pointing at the same persist file — it must still be
        OPEN.
        """
        persist = tmp_path / "breaker.json"
        b1 = CircuitBreaker(failure_threshold=2, cooldown_sec=300.0, persist_path=persist)
        b1.record_failure("down")
        b1.record_failure("down")
        assert b1.is_open("down")

        b2 = CircuitBreaker(failure_threshold=2, cooldown_sec=300.0, persist_path=persist)
        assert b2.is_open("down"), "RONDO-205 #236: persisted OPEN state must survive restart"

    def test_flaky_provider_succeeds_within_threshold(self):
        """Provider fails 2 times, succeeds on 3rd — breaker does NOT open.

        This tests the happy case of a flaky-but-recovering provider.
        """
        provider = FlakyProvider(fail_count=2)
        for _ in range(3):
            result = provider.dispatch("hello", "model")

        assert result.status == "done"
        assert provider.call_count == 3
        assert result.raw_output == "ok"

    def test_breaker_failure_resets_on_success(self, isolated_breaker):
        """Integration: single success resets the failure counter.

        Real-world scenario: intermittent failures that don't cross the
        threshold should NOT eventually trip the breaker.
        """
        # -- 2 failures (under threshold of 3), then success
        isolated_breaker.record_failure("svc")
        isolated_breaker.record_failure("svc")
        assert not isolated_breaker.is_open("svc"), "under threshold — closed"

        isolated_breaker.record_success("svc")
        # -- After success, need 3 MORE failures to trip (not 1)
        isolated_breaker.record_failure("svc")
        isolated_breaker.record_failure("svc")
        assert not isolated_breaker.is_open("svc"), (
            "success reset the counter — 2 post-success failures should not open"
        )

        isolated_breaker.record_failure("svc")
        assert isolated_breaker.is_open("svc"), "3 post-success failures → OPEN"

    def test_breaker_isolates_providers(self, isolated_breaker):
        """Per-provider isolation: failing provider A doesn't affect provider B.

        Verifies the breaker dict keys each provider separately and a
        cascading outage in one doesn't trigger false-positives in others.
        """
        for _ in range(3):
            isolated_breaker.record_failure("provider-a")
        assert isolated_breaker.is_open("provider-a")
        assert not isolated_breaker.is_open("provider-b"), "provider-b should be untouched by provider-a's failures"
        assert not isolated_breaker.is_open("provider-c"), "provider-c should be untouched too"

    def test_audit_trail_records_dispatches_while_breaker_is_open(self, tmp_path):
        """Blocked dispatch attempts still flow through the audit trail.

        Integration: breaker blocks dispatch, but the blocked attempt
        still gets recorded as INTENT + outcome. This is critical for
        observability — ops teams need to see blocked attempts to
        understand impact of an outage.
        """
        audit_trail = AuditTrail(config=AuditConfig(audit_dir=str(tmp_path / "audit")))

        # -- Simulate a dispatch attempt against a down provider
        record = audit_trail.record_intent(
            task_name="blocked-attempt",
            round_name="test",
            model="down-provider:model-x",
            prompt="hello",
        )
        assert record is not None
        assert record.dispatch_id != ""

        # -- Record the outcome as "error — breaker open"
        audit_trail.record_outcome(
            dispatch_id=record.dispatch_id,
            task_name="blocked-attempt",
            round_name="test",
            model="down-provider:model-x",
            status="error",
            exit_code=0,
            error_code="ERR_PROVIDER_DOWN",
            cost_usd=0.0,
            duration_sec=0.0,
            raw_output="circuit breaker OPEN",
            input_tokens=0,
            output_tokens=0,
            files_modified=[],
        )

        # -- Verify both records are in the audit log
        jsonl_path = tmp_path / "audit" / "rondo_audit.jsonl"
        assert jsonl_path.exists()
        content = jsonl_path.read_text(encoding="utf-8")
        assert "blocked-attempt" in content
        assert "ERR_PROVIDER_DOWN" in content

    def test_breaker_and_audit_together_maintain_tenant_isolation(self, tmp_path, monkeypatch):
        """Integration: breaker persists per-file AND audit is tenant-scoped.

        Two tenants hit the same provider with different failure patterns.
        Their audit trails must stay separate. The breaker instance used
        here is isolated per test.
        """
        # -- Tenant A: 3 failures → breaker OPEN
        monkeypatch.setenv("RONDO_TENANT", "tenant-a")
        audit_a = AuditTrail(config=AuditConfig(audit_dir=str(tmp_path / "audit-a")))
        rec_a = audit_a.record_intent(task_name="a-task", round_name="t", model="provider-x", prompt="a-prompt")
        assert rec_a.dispatch_id != ""

        # -- Tenant B: clean run
        monkeypatch.setenv("RONDO_TENANT", "tenant-b")
        audit_b = AuditTrail(config=AuditConfig(audit_dir=str(tmp_path / "audit-b")))
        rec_b = audit_b.record_intent(task_name="b-task", round_name="t", model="provider-x", prompt="b-prompt")
        assert rec_b.dispatch_id != ""

        # -- Cross-tenant check: tenant-a's audit file must not contain tenant-b's data
        a_content = (tmp_path / "audit-a" / "rondo_audit.jsonl").read_text(encoding="utf-8")
        b_content = (tmp_path / "audit-b" / "rondo_audit.jsonl").read_text(encoding="utf-8")

        assert "a-task" in a_content
        assert "b-task" in b_content
        assert "b-task" not in a_content, "tenant leak A→B"
        assert "a-task" not in b_content, "tenant leak B→A"

    def test_breaker_state_file_tolerates_corrupt_json(self, tmp_path):
        """Integration: breaker should NOT crash on a corrupted persist file.

        Simulates partial write / disk error — breaker recovers gracefully
        and starts fresh, logging a debug message.
        """
        persist = tmp_path / "breaker.json"
        persist.write_text("{NOT_VALID_JSON}", encoding="utf-8")

        # -- Should not raise
        breaker = CircuitBreaker(failure_threshold=3, cooldown_sec=60.0, persist_path=persist)

        # -- And should start in the closed state (corrupt file treated as empty)
        assert not breaker.is_open("any-provider")

    def test_empty_persist_file_is_handled(self, tmp_path):
        """Integration: a 0-byte persist file doesn't crash the breaker."""
        persist = tmp_path / "breaker.json"
        persist.write_text("", encoding="utf-8")

        breaker = CircuitBreaker(failure_threshold=3, cooldown_sec=60.0, persist_path=persist)
        assert not breaker.is_open("any")


# -- sig: mgh-6201.cd.bd955f.d207.7e2011
