# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Unit tests for shared envelope normalization helpers.

VER-001: Product acceptance / unit test coverage.
"""

from rondo.envelope import build_error_envelope, derive_top_level_status, normalize_envelope


class TestEnvelopeStatusDerivation:
    """Status derivation rules for task-status combinations."""

    def test_done_only_maps_to_done(self) -> None:
        tasks = [{"status": "done"}, {"status": "skipped"}]
        assert derive_top_level_status(tasks) == "done"

    def test_partial_only_maps_to_partial(self) -> None:
        tasks = [{"status": "partial"}]
        assert derive_top_level_status(tasks) == "partial"

    def test_done_plus_partial_maps_to_partial(self) -> None:
        tasks = [{"status": "done"}, {"status": "partial"}]
        assert derive_top_level_status(tasks) == "partial"

    def test_done_plus_error_maps_to_partial(self) -> None:
        tasks = [{"status": "done"}, {"status": "error"}]
        assert derive_top_level_status(tasks) == "partial"

    def test_error_only_maps_to_error(self) -> None:
        tasks = [{"status": "error"}, {"status": "blocked"}]
        assert derive_top_level_status(tasks) == "error"


class TestEnvelopeNormalization:
    """Normalized envelope contains canonical keys and fixed semantics."""

    def test_normalize_overrides_top_error_when_partial_task_exists(self) -> None:
        payload = {"status": "error", "tasks": [{"name": "t1", "status": "partial", "raw_output": "x"}]}
        out = normalize_envelope(payload)
        assert out["status"] == "partial"
        assert out["partial_count"] == 1
        assert out["error_count"] == 0

    def test_build_error_envelope_has_code_and_message(self) -> None:
        out = build_error_envelope(error_code="ERR_INVALID_INPUT", error_message="bad input")
        assert out["status"] == "error"
        assert out["error_code"] == "ERR_INVALID_INPUT"
        assert out["error_message"] == "bad input"
        assert "error_help" in out and out["error_help"]
        assert out["error"] == "bad input"
        assert out["code"] == "ERR_INVALID_INPUT"

    def test_build_error_envelope_fills_missing_message(self) -> None:
        out = build_error_envelope(error_code="ERR_TIMEOUT", error_message="")
        assert out["error_message"] == "Dispatch failed (ERR_TIMEOUT)"
        assert "Increase timeout_sec" in out["error_help"]

    def test_normalize_promotes_task_error_fields(self) -> None:
        payload = {
            "status": "error",
            "tasks": [
                {
                    "name": "t1",
                    "status": "error",
                    "error_code": "ERR_TIMEOUT",
                    "error_message": "Task timed out after 10s",
                }
            ],
        }
        out = normalize_envelope(payload)
        assert out["error_code"] == "ERR_TIMEOUT"
        assert out["error_message"] == "Task timed out after 10s"
        assert "Increase timeout_sec" in out["error_help"]


# -- sig: mgh-6201.cd.bd955f.f0d0.e27402
