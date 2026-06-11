# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Regression judges for ROAD-TO-8 item R2-6: auth-qualified Claude budget class.

VER-001: Product acceptance / unit test coverage.

AUTHOR: gemini-2.5-pro via rondo_run (Cursor usage-limited; separation of
duties preserved). Transcription note (documented, not silent): the author
wrote _BudgetGate(budget=1.0); the constructor's parameter is `cap` —
re-pointed to _BudgetGate(1.0); Task has `instruction`, not `prompt` — field
name re-pointed. Assertions untouched.

THE RESIDUE (re-score finding #5, review-20260610-184904.md): bare Claude
models collapsed into ONE class "claude" regardless of auth — a free max-auth
$0 sample could blind-admit PAID claude-api tasks. Cross-provider zeroing was
fixed (RONDO-395); this closes the same-prefix different-auth residue.
"""

from __future__ import annotations

from rondo.config import RondoConfig
from rondo.engine import Task
from rondo.parallel import _BudgetGate, _provider_class


def test_provider_class_claude_max() -> None:
    """Bare Claude model + auth='max' derives 'claude-max'. MUST FAIL today ('claude')."""
    config = RondoConfig(auth="max", default_model="sonnet")
    task = Task(name="t", instruction="p", model="")
    cls_name = _provider_class(task, config)
    assert cls_name == "claude-max"


def test_provider_class_claude_api() -> None:
    """Bare Claude model + auth='api' derives 'claude-api'. MUST FAIL today ('claude')."""
    config = RondoConfig(auth="api", default_model="sonnet")
    task = Task(name="t", instruction="p", model="")
    cls_name = _provider_class(task, config)
    assert cls_name == "claude-api"


def test_budget_gate_mixed_auth_isolation() -> None:
    """The gate isolates 'claude-max' and 'claude-api' classes end to end.

    Note: this drives the gate directly with class strings and may PASS today
    since the gate is already class-generic. The kill is in the derivation
    tests above; this pins the end-to-end semantics the split enables.
    """
    gate = _BudgetGate(1.0)

    # -- 1. Free sample for claude-max
    res_max = gate.try_admit("claude-max")
    assert res_max == 0.0  # -- cold-start probe
    gate.settle("claude-max", reserved=0.0, cost=0.0, ok=True)

    # -- 2. claude-api's first admit is ITS OWN probe, not claude-max's 0.0 estimate
    res_api_1 = gate.try_admit("claude-api")
    assert res_api_1 == 0.0
    gate.settle("claude-api", reserved=0.0, cost=0.60, ok=True)

    # -- 3. Second claude-api admit REFUSED (0.60 spent + 0.60 est > 1.0)
    res_api_2 = gate.try_admit("claude-api")
    assert res_api_2 is None

    # -- 4. claude-max still admits at reserve 0.0 (free is genuinely free)
    res_max_2 = gate.try_admit("claude-max")
    assert res_max_2 == 0.0


def test_provider_class_prefix_rail() -> None:
    """Rail: provider-prefixed models keep the prefix as the class, auth-independent."""
    config_max = RondoConfig(auth="max", default_model="sonnet")
    config_api = RondoConfig(auth="api", default_model="sonnet")

    task_gemini = Task(name="t", instruction="p", model="gemini:flash")
    assert _provider_class(task_gemini, config_max) == "gemini"
    assert _provider_class(task_gemini, config_api) == "gemini"

    task_local = Task(name="t", instruction="p", model="local:llama3.1:8b")
    assert _provider_class(task_local, config_max) == "local"
    assert _provider_class(task_local, config_api) == "local"


# -- sig: mgh-6201.cd.bd955f.31ec.5dfa82
