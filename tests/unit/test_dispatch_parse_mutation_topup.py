# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Mutation-driven top-ups for dispatch_parse — ROAD-TO-8 8.8 measurement closure.

VER-001: Product acceptance / mutation-adequacy coverage.

LABELED CLAUDE TOP-UP (RONDO-405): the 2026-06-10 measured sweep
(bin/mutate, --timeout-per-mutant 60) scored 31/61 with 30 survivors in five
clusters. These tests exist to KILL specific surviving mutants; the mutation
gate is the mechanical independent referee (RONDO-363's design — it trusts no
author). Survivor clusters targeted:

  1. line 53  _is_result_dict and→or: a non-dict JSON (list) must NOT count
  2. lines 87/92 bare-JSON scanner offsets (+1): malformed-then-valid text
  3. lines 130-153 usage-parsing defaults: empty events pin every 0/0.0/False
  4. line 192 text-block extraction and→or: non-dict blocks skipped, not crashed
  5. lines 219-239 ERROR_RECOVERY is_transient flags: table-driven pin — these
     flags DRIVE retry behavior; a flipped flag changes production behavior

DOCUMENTED EQUIVALENTS (never tautology-tested, house rule): the two line-92
mutants in `idx = max(end, start + 1)` on the SUCCESS-decode path. A
successful raw_decode always consumes at least one character (end > start),
so max() always picks `end` — the `start + 1` arm is a defensive guard that
can never win; mutating it cannot change behavior. Final measured score:
59/61 caught = 100% of non-equivalent mutants (was 31/61 before this suite).
"""

from __future__ import annotations

import json

from rondo.dispatch_parse import (
    ERROR_RECOVERY,
    get_error_recovery,
    parse_task_json,
)


def test_bare_json_list_is_not_a_result() -> None:
    """Kills line-53 and→or: a JSON ARRAY containing 'status' is not a result dict.

    The list must arrive FENCED — the bare scanner only looks for '{', so a
    bare array never reaches _is_result_dict (first sweep taught us that).
    """
    assert parse_task_json('```json\n["status", "passed"]\n```') is None
    assert parse_task_json('```json\n"status"\n```') is None
    assert parse_task_json('["status", "passed"]') is None


def test_bare_scanner_skips_malformed_then_finds_valid() -> None:
    """Kills the line-87/92 offset mutants: '{{' needs exactly start+1 to find the object."""
    assert parse_task_json('{{"status": "ok"}') == {"status": "ok"}
    # -- malformed prefix then a valid result later in the text
    assert parse_task_json('{oops then {"status": "done", "n": 1}') == {"status": "done", "n": 1}


def test_result_event_defaults_all_zero_on_empty_usage() -> None:
    """Kills the lines-130-153 default mutants: empty events pin every numeric default."""
    from rondo.dispatch_parse import parse_stream_json_events

    lines = [
        json.dumps({"type": "rate_limit_event", "rate_limit_info": {}}),
        # -- modelUsage entry WITHOUT contextWindow: pins the .get default
        # -- itself (an empty modelUsage never evaluates it — sweep 2 lesson)
        json.dumps({"type": "result", "usage": {}, "modelUsage": {"m": {}}}),
    ]
    _events, usage = parse_stream_json_events(lines, task_name="t")

    # -- and the EMPTY-modelUsage shape: the loop never runs, so this is the
    # -- only path where the ctx_window INITIALIZER reaches the result
    _events2, usage_empty = parse_stream_json_events(
        [json.dumps({"type": "result", "usage": {}, "modelUsage": {}})], task_name="t2"
    )
    assert usage_empty.context_window == 0

    assert usage.cost_usd == 0.0
    assert usage.input_tokens == 0
    assert usage.output_tokens == 0
    assert usage.cache_read_tokens == 0
    assert usage.cache_create_tokens == 0
    assert usage.duration_ms == 0
    assert usage.duration_api_ms == 0
    assert usage.num_turns == 0
    assert usage.context_window == 0
    assert usage.is_using_overage is False
    assert usage.rate_limit_resets_at == 0


def test_text_extraction_skips_non_dict_blocks() -> None:
    """Kills line-192 and→or: a string entry in content must be SKIPPED, never .get()'d."""
    from rondo.dispatch_parse import _collect_assistant_text

    events = [
        {
            "type": "assistant",
            "message": {"content": ["junk-string-block", {"type": "text", "text": "real text"}]},
        }
    ]
    assert _collect_assistant_text(events) == "real text"


def test_error_recovery_transient_flags_pinned() -> None:
    """Kills the lines-219-239 bool flips: every is_transient flag pinned by value.

    These flags drive retry decisions — a silent flip changes whether a
    failure class is retried. Data is behavior; the table gets a real test.
    """
    expected_transient = {
        "ERR_SUBPROCESS": False,
        "ERR_AUTH": False,
        "ERR_NESTED_SESSION": False,
        "ERR_RATE_LIMIT": True,
        "ERR_TIMEOUT": True,
        "ERR_EMPTY_OUTPUT": True,
        "ERR_COST_CAP": False,
        "ERR_WATCHDOG_TIMEOUT": True,
        "ERR_INTERNAL": False,
        "ERR_MALFORMED_JSON": True,
        "ERR_PROVIDER_DOWN": True,
        "ERR_INVALID_PROFILE": False,
    }
    assert set(ERROR_RECOVERY) == set(expected_transient), "table drifted — update BOTH with rationale"
    for code, want_transient in expected_transient.items():
        message, is_transient = get_error_recovery(code)
        assert is_transient is want_transient, f"{code}: is_transient flipped"
        assert message, f"{code}: empty recovery message"

    # -- unknown code rail
    message, is_transient = get_error_recovery("ERR_NO_SUCH_CODE")
    assert is_transient is False
    assert "preflight" in message


# -- sig: mgh-6201.cd.bd955f.db91.fddd98
