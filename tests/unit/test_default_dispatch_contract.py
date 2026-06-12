# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Unmocked-seam contract test for pipeline._default_dispatch — the production path.

VER-001: Product acceptance / dispatch normalization contract.

WHY THIS EXISTS: the mutation sweep left _default_dispatch's normalization
(reading tasks[0], mapping status/raw_output/cost/error, the timeout default)
as survivors because every OTHER pipeline test injects a fake dispatch via the
`dispatch=` seam and never exercises the REAL one. That is the classic
mocked-seam blind spot. The house rule (CONTRIBUTING.md): a mocked seam gets
ONE unmocked contract test pinning the real shape.

NOT A MOCK of rondo: this stubs ONLY the external OS boundary
`rondo.dispatch._run_subprocess` (so no claude process is forked) and lets the
ENTIRE real chain run — rondo_run_file -> run_round -> dispatch -> envelope
build -> _default_dispatch normalization. The subject under test runs for real;
only the operating-system subprocess is controlled. (See [[feedback-no-mocking-use-di-seam]].)

CACHE TRAP (found while writing this): rondo's idempotency cache keys on
(prompt, model), so reusing a prompt returns a STALE result and falsely passes.
Every case below uses a UNIQUE prompt.
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import patch

import pytest

from rondo.pipeline import _default_dispatch

_OPTS = {"tools": "", "max_turns": 0, "add_dir": "", "timeout": 0}


def _claude_stream(result_json: str, cost: float | None) -> str:
    """Build a claude stream-json stdout: one assistant text event + a result event."""
    assistant = {"type": "assistant", "message": {"content": [{"type": "text", "text": result_json}]}}
    result: dict = {"type": "result", "subtype": "success"}
    if cost is not None:
        result["total_cost_usd"] = cost
    return json.dumps(assistant) + "\n" + json.dumps(result)


@pytest.fixture(autouse=True)
def _allow_in_session(monkeypatch) -> None:
    """Bypass the in-session subprocess footgun guard (documented opt-in) — never touches CLAUDECODE."""
    monkeypatch.setenv("RONDO_ALLOW_IN_SESSION_SUBPROCESS", "1")


def _uniq(text: str) -> str:
    """A unique prompt to defeat the (prompt, model) idempotency cache."""
    return f"{text} {uuid.uuid4().hex}"


def test_default_dispatch_normalizes_a_done_task() -> None:
    """A real done envelope -> status done, raw_output assembled, cost mapped (kills L361/362/363)."""
    stdout = _claude_stream('{"status": "done", "result": "hello world"}', cost=0.0123)
    with patch("rondo.dispatch._run_subprocess") as m:
        m.return_value = (stdout, "", 0, False)
        out = _default_dispatch(_uniq("say hi"), "sonnet", _OPTS)
    assert out["status"] == "done"
    assert out["raw_output"] == '{"status": "done", "result": "hello world"}'
    assert out["cost_usd"] == 0.0123
    assert out["error"] == ""


def test_default_dispatch_maps_an_error_envelope() -> None:
    """A failed dispatch -> status error, the message surfaced (kills L361 done-branch, L364)."""
    with patch("rondo.dispatch._run_subprocess") as m:
        m.return_value = ("", "Credit balance too low", 1, False)
        out = _default_dispatch(_uniq("trigger error"), "sonnet", _OPTS)
    assert out["status"] == "error"
    assert out["raw_output"] == ""
    assert "Credit balance too low" in out["error"]


def test_default_dispatch_cost_defaults_to_zero_when_absent() -> None:
    """A done task with NO cost field -> cost_usd 0.0, not a stray default (kills the L363 `or 0.0`)."""
    stdout = _claude_stream('{"status": "done", "result": "ok"}', cost=None)
    with patch("rondo.dispatch._run_subprocess") as m:
        m.return_value = (stdout, "", 0, False)
        out = _default_dispatch(_uniq("free task"), "sonnet", _OPTS)
    assert out["status"] == "done"
    assert out["cost_usd"] == 0.0


def test_default_dispatch_passes_timeout_default_300() -> None:
    """Opts timeout=0 -> the real call uses the 300s default (kills the L355 `or 300`).

    Asserted at the OS boundary: _run_subprocess receives timeout_seconds=300.
    """
    captured = {}

    def fake_run(*args, **kwargs):
        captured["timeout"] = kwargs.get("timeout_seconds", args[2] if len(args) > 2 else None)
        return (_claude_stream('{"status": "done", "result": "ok"}', cost=0.0), "", 0, False)

    with patch("rondo.dispatch._run_subprocess", side_effect=fake_run):
        _default_dispatch(_uniq("timeout check"), "sonnet", {"tools": "", "max_turns": 0, "add_dir": "", "timeout": 0})
    # -- timeout=0 in opts must become the 300s production default by the time it hits the OS call
    assert captured["timeout"] == 300


def test_default_dispatch_tolerates_none_opts() -> None:
    """opts=None must not crash — it defaults to an empty dict (kills the L346 `opts or {}`)."""
    stdout = _claude_stream('{"status": "done", "result": "ok"}', cost=0.0)
    with patch("rondo.dispatch._run_subprocess") as m:
        m.return_value = (stdout, "", 0, False)
        out = _default_dispatch(_uniq("none opts"), "sonnet", None)
    assert out["status"] == "done"


def test_default_dispatch_marshals_opts_into_claude_argv() -> None:
    """tools/max_turns/add_dir flow to the real claude argv (kills the L352/353/354 `or` defaults).

    A boolop mutant (`x or ''` -> `x and ''`) would blank these, so the argv would
    LOSE the values — asserting them present at the OS boundary kills those mutants.
    """
    captured = {}

    def fake_run(*args, **kwargs):
        captured["argv"] = list(args[0]) if args else []
        return (_claude_stream('{"status": "done", "result": "ok"}', cost=0.0), "", 0, False)

    with patch("rondo.dispatch._run_subprocess", side_effect=fake_run):
        _default_dispatch(
            _uniq("argv flow"),
            "sonnet",
            {"tools": "Read,Write", "max_turns": 7, "add_dir": "/tmp/rondo-x", "timeout": 0},
        )
    argv = captured["argv"]
    assert "--allowedTools" in argv and "Read,Write" in argv
    assert "--max-turns" in argv and "7" in argv
    assert "--add-dir" in argv and "/tmp/rondo-x" in argv


def test_default_dispatch_timeout_default_when_key_absent() -> None:
    """Opts with NO timeout key still becomes 300s (kills the L355 get-default `0`)."""
    captured = {}

    def fake_run(*args, **kwargs):
        captured["timeout"] = kwargs.get("timeout_seconds", args[2] if len(args) > 2 else None)
        return (_claude_stream('{"status": "done", "result": "ok"}', cost=0.0), "", 0, False)

    with patch("rondo.dispatch._run_subprocess", side_effect=fake_run):
        _default_dispatch(_uniq("no timeout key"), "sonnet", {"tools": "", "max_turns": 0, "add_dir": ""})
    assert captured["timeout"] == 300


def _argv_max_turns(opts: dict) -> str:
    """Run _default_dispatch with `opts` and return the --max-turns value in the real argv."""
    captured = {}

    def fake_run(*args, **kwargs):
        captured["argv"] = list(args[0])
        return (_claude_stream('{"status": "done", "result": "ok"}', cost=0.0), "", 0, False)

    with patch("rondo.dispatch._run_subprocess", side_effect=fake_run):
        _default_dispatch(_uniq("max-turns probe"), "sonnet", opts)
    argv = captured["argv"]
    return argv[argv.index("--max-turns") + 1]


def test_max_turns_zero_falls_through_to_default() -> None:
    """max_turns=0 -> the production default 5 reaches the argv (kills the L353 `or 0` fallback)."""
    # -- a `0 or 1` mutant would pass 1 through instead of letting the default apply
    assert _argv_max_turns({"tools": "", "max_turns": 0, "add_dir": "", "timeout": 0}) == "5"


def test_max_turns_absent_uses_get_default_zero() -> None:
    """No max_turns key -> get-default 0 -> default 5 in argv (kills the L353 get-default `0`)."""
    # -- a get-default of 1 would pass 1 through instead of 0->default 5
    assert _argv_max_turns({"tools": "", "add_dir": "", "timeout": 0}) == "5"


# -- sig: mgh-6201.cd.bd955f.de47.b83632
