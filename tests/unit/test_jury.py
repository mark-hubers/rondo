# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Cross-vendor jury — the thesis feature, made first-class (RONDO-431).

VER-001: Product acceptance / cross-vendor adversarial review.

The moat: the model that WROTE the artifact does NOT certify it; DIFFERENT vendors
do, and disagreement is surfaced. controlled_review_loop.py hand-wired this; this
module makes it a reusable, testable capability.

Hermetic: every test drives jury_review with an INJECTED dispatch (the same
first-class seam the pipeline uses — DI, not a mock of rondo). The verdict channel
is the smart-return `passed` field, normalized across vendors.

TDD: written RED before rondo.jury exists.
"""

from __future__ import annotations

from rondo.jury import jury_review


def _juror(passed: bool, why: str = "") -> dict:
    """A juror dispatch reply carrying a smart-return passed verdict."""
    import json

    return {
        "status": "done",
        "raw_output": json.dumps({"passed": passed, "result": why or ("ok" if passed else "flaw")}),
    }


def test_unanimous_pass_is_accepted() -> None:
    """All reached jurors pass -> accepted, no disagreement."""

    def dispatch(prompt, model):
        return _juror(True, f"{model} ok")

    out = jury_review("code", "is it correct?", jurors=["gemini:high", "grok:grok-4.3"], dispatch=dispatch)
    assert out["accepted"] is True
    assert out["reached"] == 2
    assert out["agree"] == 2
    assert out["disagreement"] == []


def test_one_objection_blocks_and_is_surfaced() -> None:
    """A single juror objecting -> NOT accepted, and the objector is surfaced."""

    def dispatch(prompt, model):
        return _juror(model != "grok:grok-4.3", "looks wrong" if model == "grok:grok-4.3" else "ok")

    out = jury_review("code", "is it correct?", jurors=["gemini:high", "grok:grok-4.3"], dispatch=dispatch)
    assert out["accepted"] is False
    assert any(d["model"] == "grok:grok-4.3" and d["passed"] is False for d in out["disagreement"])


def test_unreachable_juror_is_inconclusive_not_a_no_vote() -> None:
    """A juror that errors/can't be parsed is INCONCLUSIVE (not counted), never a silent no."""

    def dispatch(prompt, model):
        if model == "down:model":
            return {"status": "error", "raw_output": ""}
        return _juror(True)

    out = jury_review("code", "ok?", jurors=["gemini:high", "down:model"], dispatch=dispatch)
    assert out["reached"] == 1  # -- only the reachable juror counts
    assert out["accepted"] is True  # -- the one reached juror passed; >=1 reached + unanimous


def test_all_unreachable_is_not_accepted() -> None:
    """No juror reachable -> not accepted (can't certify on zero verdicts)."""

    def dispatch(prompt, model):
        return {"status": "error", "raw_output": ""}

    out = jury_review("code", "ok?", jurors=["a:x", "b:y"], dispatch=dispatch)
    assert out["reached"] == 0
    assert out["accepted"] is False


def test_verdict_uses_passed_channel_not_a_custom_key() -> None:
    """A juror returning {passed:false} (no 'correct' key) is read correctly as an objection."""

    def dispatch(prompt, model):
        import json

        return {"status": "done", "raw_output": json.dumps({"passed": False, "result": "bug on empty input"})}

    out = jury_review("code", "ok?", jurors=["gemini:high"], dispatch=dispatch)
    assert out["accepted"] is False
    assert out["disagreement"][0]["why"] == "bug on empty input"


def test_each_juror_gets_the_artifact_and_question() -> None:
    """The artifact + question reach each juror's prompt (so they review the real thing)."""
    seen = []

    def dispatch(prompt, model):
        seen.append(prompt)
        return _juror(True)

    jury_review("def add(a,b): return a+b", "does add() sum its args?", jurors=["m:1"], dispatch=dispatch)
    assert "def add(a,b): return a+b" in seen[0]
    assert "does add() sum its args?" in seen[0]


# ── per-verdict shape (kills the _one_verdict inconclusive branches) ──


def test_unreachable_verdict_carries_reached_false() -> None:
    """An errored juror's verdict has reached=False, passed=False, the model name (kills L47/L50)."""

    def dispatch(prompt, model):
        return {"status": "error", "raw_output": ""}

    out = jury_review("c", "q", jurors=["m:x"], dispatch=dispatch)
    v = out["verdicts"][0]
    assert v["reached"] is False and v["passed"] is False and v["model"] == "m:x"


def test_valid_json_without_passed_key_is_inconclusive() -> None:
    """Valid JSON lacking the 'passed' key -> inconclusive, not a vote (kills the L49 'or' arm)."""
    import json

    def dispatch(prompt, model):
        return {"status": "done", "raw_output": json.dumps({"result": "no verdict here"})}

    out = jury_review("c", "q", jurors=["m:x"], dispatch=dispatch)
    assert out["reached"] == 0
    v = out["verdicts"][0]
    assert v["why"] == "no parseable verdict"
    assert v["reached"] is False and v["passed"] is False  # -- inconclusive reports passed=False, not a stray True


# ── _default_dispatch: unmocked-seam contract test (kills L63/64/65 — the production path) ──


def test_default_dispatch_normalizes_a_real_envelope(monkeypatch) -> None:
    """jury._default_dispatch runs the REAL chain (only the OS subprocess stubbed), not a mock.

    Same house-rule unmocked-seam pattern as test_default_dispatch_contract.py:
    stub rondo.dispatch._run_subprocess, let rondo_run_file build a real envelope,
    assert jury normalizes status + raw_output. dry_run=False (L63) is implied —
    a dry-run mutant would yield a plan, not a done task.
    """
    import json
    import uuid
    from unittest.mock import patch

    from rondo.jury import _default_dispatch

    monkeypatch.setenv("RONDO_ALLOW_IN_SESSION_SUBPROCESS", "1")
    assistant = {"type": "assistant", "message": {"content": [{"type": "text", "text": '{"passed": true}'}]}}
    result = {"type": "result", "subtype": "success", "total_cost_usd": 0.0}
    stdout = json.dumps(assistant) + "\n" + json.dumps(result)
    with patch("rondo.dispatch._run_subprocess") as m:
        m.return_value = (stdout, "", 0, False)
        out = _default_dispatch(f"jury probe {uuid.uuid4().hex}", "sonnet")
    assert out["status"] == "done"
    assert out["raw_output"] == '{"passed": true}'


# -- sig: mgh-6201.cd.bd955f.34e7.38dee9
