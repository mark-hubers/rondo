# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Mutation-gate regression: envelope.py public-contract behaviors must be asserted.

VER-001 verification matrix: dispatch result/error envelope normalization.

Quality-checklist item 15 (mutation gate): src/rondo/envelope.py is the PUBLIC
CONTRACT — every MCP/CLI dispatch result flows through normalize_envelope and
downstream consumers (USH) parse these fields. 21 of 44 mutants SURVIVE the
existing envelope test surface; all 21 are REAL: the behaviors are
production-reachable yet completely unasserted, so a regression would ship while
the suite stayed green.

These tests pin the OBSERVABLE outcomes the survivors depend on, mirroring
tests/unit/test_spool_contracts_cursor.py in spirit. They PASS against current
code — their proof is RED-vs-MUTANTS: with them landed, bin/mutate on
envelope.py kills the listed survivors.

Survivor groups covered (A-G):
    A derive_top_level_status — the running/done/partial/error ladder
    B compute_task_counts     — skipped->done, blocked->error groupings
    C _normalize_status (S1)  — error/blank/unknown re-derivation vs healthy keep
    D first-error promotion   — task error fields lifted to top level
    E _normalize_numeric_fields — None/absent coercion + dry_run truthiness
    F build_error_envelope    — zero counts, schema, aliases, help, context merge
    G normalize_envelope      — schema_version defaulting + string coercion
"""

import pytest

from rondo.envelope import (
    ENVELOPE_SCHEMA_VERSION,
    ERROR_HELP_BY_CODE,
    build_error_envelope,
    compute_task_counts,
    derive_top_level_status,
    normalize_envelope,
)


def _task(status: str, **extra: object) -> dict[str, object]:
    """Build a minimal task dict with the given status plus optional fields."""
    return {"status": status, **extra}


# -- ──────────────────────────────────────────────────────────────
# --  A. derive_top_level_status — the running/done/partial/error ladder
# -- ──────────────────────────────────────────────────────────────


class TestDeriveTopLevelStatus:
    """Each rung of the status ladder maps task mixes to one canonical status."""

    @pytest.mark.parametrize(
        ("statuses", "expected"),
        [
            # -- pending ALONE is the only "running" shape.
            (["pending"], "running"),
            (["pending", "pending"], "running"),
            # -- pending mixed with anything else does NOT stay running.
            (["pending", "done"], "done"),
            (["pending", "partial"], "partial"),
            (["pending", "error"], "error"),
            # -- all terminal-success -> done.
            (["done"], "done"),
            (["done", "done"], "done"),
            (["skipped"], "done"),
            (["done", "skipped"], "done"),
            # -- partial present, no error -> partial.
            (["partial"], "partial"),
            (["partial", "done"], "partial"),
            # -- error alongside done/partial is a mixed outcome -> partial.
            (["error", "done"], "partial"),
            (["error", "partial"], "partial"),
            (["blocked", "done"], "partial"),
            # -- error/blocked only -> error.
            (["error"], "error"),
            (["blocked"], "error"),
            (["error", "blocked"], "error"),
            # -- empty list pins the all-zero-counts path -> done.
            ([], "done"),
        ],
    )
    def test_status_ladder(self, statuses: list[str], expected: str) -> None:
        """The derivation ladder yields the exact canonical status per task mix."""
        tasks = [_task(s) for s in statuses]
        assert derive_top_level_status(tasks) == expected

    def test_pending_only_is_running_not_done(self) -> None:
        """Pending-only must be 'running' (kills the has_pending guard mutant)."""
        # -- if the first-rung pending guard degraded, this would fall to 'done'.
        assert derive_top_level_status([_task("pending")]) == "running"

    def test_partial_no_error_takes_partial_rung(self) -> None:
        """has_partial & not has_error returns 'partial' (third-rung specific)."""
        # -- partial+done (no error) only resolves on the `not has_error` rung.
        assert derive_top_level_status([_task("partial"), _task("done")]) == "partial"

    def test_error_with_done_is_partial_not_error(self) -> None:
        """Error mixed with a success degrades to 'partial', never 'error'."""
        assert derive_top_level_status([_task("error"), _task("done")]) == "partial"

    def test_unknown_statuses_count_nowhere_so_empty_is_done(self) -> None:
        """Tasks with unrecognized statuses contribute no counts -> 'done'."""
        # -- mirrors the all-zero-counts fall-through used by an empty list.
        assert derive_top_level_status([_task("weird"), _task("")]) == "done"


# -- ──────────────────────────────────────────────────────────────
# --  B. compute_task_counts — skipped->done, blocked->error groupings
# -- ──────────────────────────────────────────────────────────────


class TestComputeTaskCounts:
    """Counters fold skipped into done and blocked into error; rest map 1:1."""

    def test_done_counts_skipped_too(self) -> None:
        """done_count is done + skipped (kills dropping the `+ skipped` arm)."""
        counts = compute_task_counts([_task("done"), _task("skipped"), _task("done")])
        assert counts["done_count"] == 3

    def test_error_counts_blocked_too(self) -> None:
        """error_count is error + blocked (kills dropping the `+ blocked` arm)."""
        counts = compute_task_counts([_task("error"), _task("blocked")])
        assert counts["error_count"] == 2

    def test_partial_and_pending_counted_directly(self) -> None:
        """partial_count and pending_count tally their own status names."""
        counts = compute_task_counts([_task("partial"), _task("partial"), _task("pending")])
        assert counts["partial_count"] == 2
        assert counts["pending_count"] == 1

    def test_unknown_and_nondict_counted_nowhere(self) -> None:
        """Unknown statuses, missing-status dicts, and non-dicts add to no bucket."""
        counts = compute_task_counts([_task("weird"), {}, "not-a-dict", None])
        assert counts == {
            "done_count": 0,
            "error_count": 0,
            "partial_count": 0,
            "pending_count": 0,
        }


# -- ──────────────────────────────────────────────────────────────
# --  C. _normalize_status (S1) — re-derive error/blank/unknown, keep healthy
# -- ──────────────────────────────────────────────────────────────


class TestNormalizeStatusRule:
    """Top-level status is re-derived for error/blank/unknown, else preserved."""

    def test_error_with_mixed_tasks_is_rederived(self) -> None:
        """status='error' but tasks show done+partial -> re-derived to 'partial'."""
        # -- S1 fix: a task-level mix must not collapse the envelope to 'error'.
        out = normalize_envelope({"status": "error", "tasks": [_task("done"), _task("partial")]})
        assert out["status"] == "partial"

    def test_error_with_no_tasks_stays_error(self) -> None:
        """status='error' with an empty task list is NOT re-derived (the `and tasks` guard)."""
        # -- if `and tasks` were dropped, derive([]) would flip this to 'done'.
        out = normalize_envelope({"status": "error", "tasks": []})
        assert out["status"] == "error"

    def test_blank_status_is_derived(self) -> None:
        """An empty status is replaced by the derived ladder value."""
        out = normalize_envelope({"status": "", "tasks": [_task("done")]})
        assert out["status"] == "done"

    def test_unknown_status_is_derived(self) -> None:
        """Literal 'unknown' status is replaced by the derived ladder value."""
        out = normalize_envelope({"status": "unknown", "tasks": [_task("pending")]})
        assert out["status"] == "running"

    def test_explicit_healthy_status_preserved(self) -> None:
        """A non-error explicit status is preserved even when tasks disagree."""
        # -- 'done' is neither '' / 'unknown' nor 'error', so it is left intact.
        out = normalize_envelope({"status": "done", "tasks": [_task("error")]})
        assert out["status"] == "done"


# -- ──────────────────────────────────────────────────────────────
# --  D. first-error promotion — task error fields lifted to top level
# -- ──────────────────────────────────────────────────────────────


class TestErrorPromotion:
    """Missing top-level error metadata is promoted from the first error task."""

    def test_first_error_task_fields_promoted(self) -> None:
        """An error task's code/message is lifted to the top level with aliases."""
        out = normalize_envelope(
            {
                "tasks": [
                    _task("error", error_code="ERR_TIMEOUT", error_message="too slow"),
                ]
            }
        )
        assert out["status"] == "error"
        assert out["error_code"] == "ERR_TIMEOUT"
        assert out["error_message"] == "too slow"
        # -- backward-compat aliases mirror the canonical fields.
        assert out["error"] == "too slow"
        assert out["code"] == "ERR_TIMEOUT"
        # -- known-code help text comes along for the ride.
        assert out["error_help"] == ERROR_HELP_BY_CODE["ERR_TIMEOUT"]

    def test_promotion_needs_only_one_error_field(self) -> None:
        """A task with ONLY error_message (no error_code) still promotes its message.

        Pins the `error_code or error_message` filter: a degrade to `and` would
        require BOTH fields, so this message-only task would fail to promote and
        the envelope would fall back to the generic 'Dispatch failed' message.
        """
        out = normalize_envelope({"tasks": [_task("error", error_message="only a message")]})
        assert out["error_message"] == "only a message"
        # -- no task error_code present, so the canonical default fills in.
        assert out["error_code"] == "ERR_DISPATCH_EXCEPTION"

    def test_blocked_task_also_promotes(self) -> None:
        """A 'blocked' task counts as an error source for promotion."""
        out = normalize_envelope(
            {
                "tasks": [
                    _task("blocked", error_code="ERR_INVALID_INPUT", error_message="bad"),
                ]
            }
        )
        assert out["error_code"] == "ERR_INVALID_INPUT"
        assert out["error_message"] == "bad"

    def test_existing_top_level_error_code_blocks_promotion(self) -> None:
        """Promotion is SKIPPED when a top-level error_code is already set."""
        out = normalize_envelope(
            {
                "status": "error",
                "error_code": "ERR_TOP",
                "tasks": [
                    _task("error", error_code="ERR_TASK", error_message="ignored"),
                ],
            }
        )
        # -- the pre-existing top-level code wins; the task code is not lifted.
        assert out["error_code"] == "ERR_TOP"

    def test_non_dict_tasks_tolerated_during_promotion(self) -> None:
        """Non-dict task entries are skipped without error during promotion."""
        out = normalize_envelope(
            {
                "tasks": [
                    None,
                    "junk",
                    _task("error", error_code="ERR_FILE_NOT_FOUND", error_message="nope"),
                ]
            }
        )
        assert out["error_code"] == "ERR_FILE_NOT_FOUND"
        assert out["error_message"] == "nope"


# -- ──────────────────────────────────────────────────────────────
# --  E. _normalize_numeric_fields — None/absent coercion + dry_run
# -- ──────────────────────────────────────────────────────────────


class TestNumericFields:
    """Numeric fields coerce None/absent to 0.0; dry_run coerces to bool."""

    @pytest.mark.parametrize("field", ["total_cost_usd", "duration_sec"])
    def test_none_value_coerced_to_zero(self, field: str) -> None:
        """An explicit None numeric value becomes 0.0 (the `or 0.0` guard)."""
        # -- without `or 0.0`, float(None) would raise — pins the coercion.
        out = normalize_envelope({field: None})
        assert out[field] == 0.0

    @pytest.mark.parametrize("field", ["total_cost_usd", "duration_sec"])
    def test_absent_value_defaults_to_zero(self, field: str) -> None:
        """An absent numeric field defaults to 0.0."""
        out = normalize_envelope({})
        assert out[field] == 0.0

    @pytest.mark.parametrize(
        ("field", "given"),
        [
            ("total_cost_usd", 0.42),
            ("total_cost_usd", 5),
            ("duration_sec", 12.5),
            ("duration_sec", 3),
        ],
    )
    def test_real_value_preserved_as_float(self, field: str, given: object) -> None:
        """A real numeric value is preserved and returned as a float."""
        out = normalize_envelope({field: given})
        assert out[field] == float(given)
        assert isinstance(out[field], float)

    @pytest.mark.parametrize(
        ("given", "expected"),
        [
            (True, True),
            (1, True),
            ("yes", True),
            (False, False),
            (None, False),
            (0, False),
        ],
    )
    def test_dry_run_truthiness(self, given: object, expected: bool) -> None:
        """dry_run coerces to bool by truthiness of the supplied value."""
        out = normalize_envelope({"dry_run": given})
        assert out["dry_run"] is expected

    def test_dry_run_absent_defaults_false(self) -> None:
        """An absent dry_run defaults to False."""
        out = normalize_envelope({})
        assert out["dry_run"] is False


# -- ──────────────────────────────────────────────────────────────
# --  F. build_error_envelope — counts, schema, aliases, help, context
# -- ──────────────────────────────────────────────────────────────


class TestBuildErrorEnvelope:
    """build_error_envelope emits a fully-populated canonical error payload."""

    def test_zero_int_counts_and_schema_and_status(self) -> None:
        """All count fields are integer zero; schema='2'; status='error'."""
        env = build_error_envelope(error_code="ERR_TIMEOUT", error_message="boom")
        for key in ("done_count", "error_count", "partial_count", "pending_count"):
            assert env[key] == 0
            assert isinstance(env[key], int)
        assert env["schema_version"] == "2"
        assert env["status"] == "error"
        # -- empty task list is part of the canonical shape.
        assert env["tasks"] == []
        # -- error envelopes are never dry runs (kills the False->True flip).
        assert env["dry_run"] is False

    def test_known_code_gets_specific_help(self) -> None:
        """A known error_code yields its specific ERROR_HELP_BY_CODE entry."""
        env = build_error_envelope(error_code="ERR_TIMEOUT", error_message="boom")
        assert env["error_help"] == ERROR_HELP_BY_CODE["ERR_TIMEOUT"]

    def test_unknown_code_gets_generic_help(self) -> None:
        """An unknown error_code falls back to the generic help string."""
        env = build_error_envelope(error_code="ERR_NOT_REAL", error_message="boom")
        assert env["error_help"] == "Check error_message and task output, then retry with adjusted inputs."

    def test_backward_compat_aliases(self) -> None:
        """The `error` alias mirrors error_message and `code` mirrors error_code."""
        env = build_error_envelope(error_code="ERR_INVALID_INPUT", error_message="bad args")
        assert env["error"] == env["error_message"] == "bad args"
        assert env["code"] == env["error_code"] == "ERR_INVALID_INPUT"

    def test_empty_message_resolves_to_fallback(self) -> None:
        """An empty error_message resolves to the 'Dispatch failed (code)' fallback."""
        env = build_error_envelope(error_code="ERR_TIMEOUT", error_message="")
        assert env["error_message"] == "Dispatch failed (ERR_TIMEOUT)"
        assert env["error"] == "Dispatch failed (ERR_TIMEOUT)"

    def test_context_merges_new_keys_and_overrides_existing(self) -> None:
        """The context dict adds new keys and overrides any existing payload field."""
        env = build_error_envelope(
            error_code="ERR_TIMEOUT",
            error_message="boom",
            context={"dispatch_id": "abc123", "status": "overridden"},
        )
        # -- new key merged in.
        assert env["dispatch_id"] == "abc123"
        # -- context wins over the built-in default.
        assert env["status"] == "overridden"


# -- ──────────────────────────────────────────────────────────────
# --  G. normalize_envelope — schema_version defaulting + coercion
# -- ──────────────────────────────────────────────────────────────


class TestNormalizeSchemaVersion:
    """schema_version defaults to ENVELOPE_SCHEMA_VERSION and is always a string."""

    def test_missing_schema_version_defaults(self) -> None:
        """An absent schema_version is filled with ENVELOPE_SCHEMA_VERSION ('2')."""
        out = normalize_envelope({})
        assert out["schema_version"] == ENVELOPE_SCHEMA_VERSION == "2"

    def test_empty_schema_version_defaults(self) -> None:
        """An empty-string schema_version coerces to the default (the `or` guard)."""
        out = normalize_envelope({"schema_version": ""})
        assert out["schema_version"] == "2"

    def test_existing_schema_version_preserved(self) -> None:
        """A present schema_version is preserved verbatim."""
        out = normalize_envelope({"schema_version": "5"})
        assert out["schema_version"] == "5"

    def test_numeric_schema_version_coerced_to_string(self) -> None:
        """A non-string schema_version is coerced to its string form."""
        out = normalize_envelope({"schema_version": 3})
        assert out["schema_version"] == "3"
        assert isinstance(out["schema_version"], str)


# -- sig: mgh-6201.cd.bd955f.42a4.042609
