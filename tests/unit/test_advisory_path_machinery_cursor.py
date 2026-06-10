# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Regression judges for ROAD-TO-8 item 8.2 — the advisory-dispatch machinery.

VER-001: Product acceptance / regression test coverage.

These are the judges proposed in the Cursor design review
(reports/cursor-reviews/design-review-20260610-item82.md, section 8) for the
ACCEPTED contract. They pin the behavior advisory plans (engine inline|agent)
MUST exhibit at the choke point (mcp_dispatch.py:872-873):

  (1) audit completeness   — one INTENT + one paired advisory OUTCOME per plan
  (2) sanitize boundary    — secret scrubbed in the PERSISTED copy, verbatim in
                              the RETURNED plan
  (3) scope non-ambiguity  — inline/agent = "advisory" with a not_covered set;
                              subprocess = "guarded"
  (4) dispatch_id corr.    — returned plan's dispatch_id == the audit record's
  (5) fail-open + loud      — audit write failure never blocks the plan; logs WARN
  (6) no-caching freshness  — two identical inline dispatches mint fresh
                              execution_token AND dispatch_id; cache stays empty
  (7) no reconcile false+   — reconcile_stuck_intents() finds 0 stuck after an
                              advisory dispatch (INTENT is always paired)
  (8) schema version "3"    — advisory plans carry PLAN_SCHEMA_VERSION "3"
  (9) estimate gate          — tiny max_budget + paid-model agent plan is REFUSED
                              with a budget error envelope; no max_budget → issued

All judges drive the PUBLIC MCP entry (rondo_run_file with a _session, the
host-auto-execute seam used by tests/integration/test_option_c_contract.py and
tests/unit/test_mcp_cursor_reviews.py). RONDO_TEST_DIR is autouse (tests/conftest.py)
so every audit JSONL / prompt file lands under tmp. Advisory paths never dispatch,
so there are NO live AI calls.

The plans-per-minute limiter from the review was DECLINED (scope control) and is
intentionally NOT pinned here.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from pathlib import Path

from rondo.audit import AuditConfig, AuditTrail
from rondo.dispatch_routing import PLAN_SCHEMA_VERSION, _build_subprocess_plan
from rondo.idempotency import compute_idempotency_key, get_cached_result
from rondo.mcp_dispatch import rondo_run_file

# -- the not_covered floor the advisory envelope must declare (contract §3)
_REQUIRED_NOT_COVERED = {
    "budget",
    "circuit_breaker",
    "cost_tracking",
    "result_audit",
    "output_sanitization",
    "idempotency",
}


def _unique_prompt(label: str) -> str:
    """A per-test unique prompt so idempotency keys never collide cross-test."""
    return f"advisory-judge::{label}::{uuid.uuid4().hex[:12]}"


def _run(**kwargs: object) -> str:
    """Drive the public MCP entry with a host session (inline auto-execute seam)."""
    params: dict[str, object] = {
        "dry_run": False,
        "_session": object(),
    }
    params.update(kwargs)
    return rondo_run_file(**params)  # type: ignore[arg-type]


def _run_plan(**kwargs: object) -> dict:
    """Run and parse the returned JSON payload."""
    return json.loads(_run(**kwargs))


def _audit_jsonl_path() -> Path:
    """The audit JSONL the choke point writes to under RONDO_TEST_DIR."""
    return Path(os.environ["RONDO_TEST_DIR"]) / "audit" / "rondo_audit.jsonl"


def _read_audit_records() -> list[dict]:
    """Parse every JSONL audit record written so far (empty if none)."""
    path = _audit_jsonl_path()
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def test_1_audit_completeness_intent_plus_advisory_outcome() -> None:
    """One inline AND one agent dispatch each write one INTENT + one paired OUTCOME.

    OUTCOME status=='advisory', exit_code==0, error_code is None. Pins §1.
    """
    inline = _run_plan(prompt=_unique_prompt("audit-inline"), model="", execution="inline")
    agent = _run_plan(prompt=_unique_prompt("audit-agent"), model="sonnet", execution="agent")

    assert "dispatch_id" in inline, "inline advisory plan must carry a dispatch_id"
    assert "dispatch_id" in agent, "agent advisory plan must carry a dispatch_id"

    records = _read_audit_records()
    for plan in (inline, agent):
        did = plan["dispatch_id"]
        mine = [r for r in records if r.get("dispatch_id") == did]
        intents = [r for r in mine if r.get("status") == "INTENT"]
        outcomes = [r for r in mine if r.get("status") == "advisory"]
        assert len(intents) == 1, f"expected exactly 1 INTENT for {did}, got {len(intents)}"
        assert len(outcomes) == 1, f"expected exactly 1 advisory OUTCOME for {did}, got {len(outcomes)}"
        outcome = outcomes[0]
        assert outcome["exit_code"] == 0
        assert outcome["error_code"] is None


def test_2_sanitize_boundary_both_directions() -> None:
    """Secret is REDACTED in the persisted prompt file, VERBATIM in the returned plan.

    Pins §2: sanitize-on-persist-only; the authorized caller keeps the raw prompt.
    """
    secret = "AKIAIOSFODNN7EXAMPLE"  # -- AWS access-key shape; sanitize redacts it
    prompt = f"{_unique_prompt('sanitize')} key={secret}"
    plan = _run_plan(prompt=prompt, model="", execution="inline")

    # -- RETURNED plan keeps the prompt verbatim (host is the authorized caller)
    assert secret in plan["prompt"], "returned plan must preserve the raw prompt verbatim"

    # -- PERSISTED copy must be scrubbed
    assert "dispatch_id" in plan, "advisory plan must carry a dispatch_id to locate its prompt file"
    prompt_file = _audit_jsonl_path().parent / f"{plan['dispatch_id']}.prompt.txt"
    assert prompt_file.exists(), "advisory INTENT must persist a prompt file"
    persisted = prompt_file.read_text()
    assert secret not in persisted, "secret must be scrubbed from the persisted prompt"
    assert "[REDACTED" in persisted, "scrubbed prompt should carry a [REDACTED:...] marker"


def test_3_scope_non_ambiguity_advisory_vs_guarded() -> None:
    """inline/agent plans declare guarantees_scope='advisory'; subprocess='guarded'.

    Advisory not_covered must be a superset of the agreed floor. Pins §3.
    """
    inline = _run_plan(prompt=_unique_prompt("scope-inline"), model="", execution="inline")
    agent = _run_plan(prompt=_unique_prompt("scope-agent"), model="sonnet", execution="agent")

    for plan in (inline, agent):
        assert plan.get("guarantees_scope") == "advisory", f"advisory plan scope was {plan.get('guarantees_scope')!r}"
        not_covered = set(plan.get("not_covered") or [])
        missing = _REQUIRED_NOT_COVERED - not_covered
        assert not missing, f"advisory not_covered missing {missing}"

    # -- subprocess plans must be present-and-explicit too (no ambiguous absence)
    subprocess_plan = _build_subprocess_plan(model="sonnet", reason="scope-check")
    assert subprocess_plan.get("guarantees_scope") == "guarded"
    assert subprocess_plan.get("guarantees_scope") != "advisory"


def test_4_dispatch_id_correlation_plan_matches_audit() -> None:
    """The returned plan's dispatch_id equals its INTENT and OUTCOME records. Pins §6/§4."""
    plan = _run_plan(prompt=_unique_prompt("correlation"), model="", execution="inline")
    assert "dispatch_id" in plan, "advisory plan must carry a dispatch_id"
    did = plan["dispatch_id"]

    records = _read_audit_records()
    statuses = {r.get("status") for r in records if r.get("dispatch_id") == did}
    assert "INTENT" in statuses, "no INTENT record correlated to the plan's dispatch_id"
    assert "advisory" in statuses, "no advisory OUTCOME correlated to the plan's dispatch_id"


def test_5_fail_open_and_loud_on_audit_write_failure(monkeypatch, caplog) -> None:
    """Audit write failure never blocks the plan return AND a WARNING/ERROR is logged.

    Pins §5: fail-open + loud (the house pattern).
    """

    def _boom(*_args: object, **_kwargs: object):
        raise RuntimeError("simulated audit write failure")

    monkeypatch.setattr(AuditTrail, "record_intent", _boom, raising=True)
    monkeypatch.setattr(AuditTrail, "record_outcome", _boom, raising=True)

    prompt = _unique_prompt("fail-open")
    with caplog.at_level(logging.WARNING):
        plan = _run_plan(prompt=prompt, model="", execution="inline")

    # -- plan still returned intact
    assert plan["engine"] == "inline"
    assert plan["prompt"] == prompt

    # -- and it was LOUD about the audit failure
    loud = [r for r in caplog.records if r.levelno >= logging.WARNING and "audit" in r.getMessage().lower()]
    assert loud, "expected a WARNING/ERROR log about the failed advisory audit write"


def test_6_no_caching_freshness_per_dispatch() -> None:
    """Two identical inline dispatches mint fresh execution_token AND dispatch_id.

    The idempotency cache is never populated for advisory plans. Pins §7.
    """
    prompt = _unique_prompt("no-cache")
    first = _run_plan(prompt=prompt, model="", execution="inline")
    second = _run_plan(prompt=prompt, model="", execution="inline")

    assert first["execution_token"] != second["execution_token"], "execution_token must be fresh per dispatch"
    assert "dispatch_id" in first and "dispatch_id" in second, "advisory plans must carry dispatch_id"
    assert first["dispatch_id"] != second["dispatch_id"], "dispatch_id must be fresh per dispatch"

    key = compute_idempotency_key(prompt, "", "inline")
    assert get_cached_result(key) is None, "advisory plans must never be cached"


def test_7_no_reconcile_false_positive() -> None:
    """After an advisory dispatch, reconcile_stuck_intents() finds 0 stuck. Pins §1 completeness."""
    _run_plan(prompt=_unique_prompt("reconcile"), model="", execution="inline")

    records = _read_audit_records()
    intent_count = sum(1 for r in records if r.get("status") == "INTENT")
    assert intent_count >= 1, "advisory dispatch must have written an INTENT to reconcile against"

    trail = AuditTrail(config=AuditConfig(), auto_reconcile=False)
    # -- stuck_after_sec=0 disables the in-flight grace window: any unpaired
    # -- INTENT WOULD be marked stuck. A paired advisory OUTCOME yields 0.
    stuck = trail.reconcile_stuck_intents(stuck_after_sec=0)
    assert stuck == 0, f"advisory INTENT must be paired (got {stuck} stuck)"


def test_8_schema_version_three_on_advisory_plans() -> None:
    """Advisory plans declare PLAN_SCHEMA_VERSION '3'. Pins §3 version bump."""
    inline = _run_plan(prompt=_unique_prompt("schema-inline"), model="", execution="inline")
    agent = _run_plan(prompt=_unique_prompt("schema-agent"), model="sonnet", execution="agent")

    assert PLAN_SCHEMA_VERSION == "3"
    assert inline["schema_version"] == "3"
    assert agent["schema_version"] == "3"


def test_9_estimate_gated_budget_at_issuance() -> None:
    """Tiny max_budget + paid-model agent plan is REFUSED; no max_budget → issued. Pins §4."""
    prompt = _unique_prompt("budget")

    refused = _run_plan(prompt=prompt, model="sonnet", execution="agent", max_budget=0.000001)
    assert refused.get("status") == "error", "tiny max_budget must refuse to issue the plan"
    blob = json.dumps(refused).lower()
    assert "budget" in blob, "refusal must be a budget error envelope"

    # -- no max_budget declared → no gate → plan issued (declared, not faked)
    issued = _run_plan(prompt=_unique_prompt("budget-ungated"), model="sonnet", execution="agent")
    assert issued.get("engine") == "agent"
    assert issued.get("status") != "error"


# -- sig: mgh-6201.cd.bd955f.8151.e7ddc3
