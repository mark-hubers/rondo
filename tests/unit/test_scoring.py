# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Tests for rondo.scoring — provider quality scoring from history.

REQ-111 reqs 442-445, REQ-109 (Adaptive Provider Scoring) reqs 300-324.
VER-001: Product acceptance / unit test coverage.
"""

from __future__ import annotations

import json
import time

from rondo.scoring import (
    compute_provider_scores,
    load_scores_cache,
    save_scores_cache,
)


class TestComputeProviderScores:
    """REQ-111 req 442: compute scores from audit data."""

    def test_empty_audit_dir(self, tmp_path) -> None:
        """No audit files → empty scores."""
        scores = compute_provider_scores(str(tmp_path))
        assert scores == {}

    def test_not_enough_samples(self, tmp_path) -> None:
        """Below MIN_SAMPLE_COUNT → provider excluded."""
        _write_outcomes(tmp_path, "gemini:flash", count=5, status="done")
        scores = compute_provider_scores(str(tmp_path))
        assert "gemini:flash" not in scores

    def test_basic_scoring(self, tmp_path) -> None:
        """10+ outcomes → provider gets a score."""
        _write_outcomes(tmp_path, "gemini:flash", count=15, status="done")
        scores = compute_provider_scores(str(tmp_path))
        assert "gemini:flash" in scores
        score = scores["gemini:flash"]
        assert score["sample_count"] == 15
        assert score["success_rate"] == 1.0
        assert score["score"] > 0.0

    def test_mixed_success_failure(self, tmp_path) -> None:
        """Mix of done + error → success_rate < 1.0."""
        _write_outcomes(tmp_path, "grok:grok-3", count=8, status="done")
        _write_outcomes(tmp_path, "grok:grok-3", count=4, status="error")
        scores = compute_provider_scores(str(tmp_path))
        score = scores["grok:grok-3"]
        assert score["success_rate"] < 1.0
        assert score["done_count"] == 8
        assert score["error_count"] == 4

    def test_json_quality_tracked(self, tmp_path) -> None:
        """json_valid and fields_complete are tracked."""
        outcomes = []
        for i in range(12):
            outcomes.append(
                {
                    "model": "gemini:flash",
                    "status": "done",
                    "completed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "cost_usd": 0.003,
                    "duration_sec": 2.0,
                    "json_valid": i < 10,  # -- 10/12 valid
                    "fields_complete": i < 8,  # -- 8/12 complete
                }
            )
        jsonl = tmp_path / "audit.jsonl"
        jsonl.write_text("\n".join(json.dumps(o) for o in outcomes))

        scores = compute_provider_scores(str(tmp_path))
        score = scores["gemini:flash"]
        assert score["json_success_rate"] is not None
        assert 0.8 <= score["json_success_rate"] <= 0.85

    def test_multiple_providers(self, tmp_path) -> None:
        """Multiple providers scored independently."""
        _write_outcomes(tmp_path, "gemini:flash", count=12, status="done", cost=0.003)
        _write_outcomes(tmp_path, "grok:grok-3", count=11, status="done", cost=0.008)
        scores = compute_provider_scores(str(tmp_path))
        assert len(scores) == 2
        assert scores["gemini:flash"]["avg_cost_usd"] < scores["grok:grok-3"]["avg_cost_usd"]


class TestScoresCache:
    """REQ-111 req 443: cache provider scores."""

    def test_save_and_load(self, tmp_path) -> None:
        """Save scores, load them back."""
        scores = {"gemini:flash": {"score": 0.87, "sample_count": 50}}
        save_scores_cache(scores, str(tmp_path))
        loaded = load_scores_cache(str(tmp_path))
        assert "gemini:flash" in loaded
        assert loaded["gemini:flash"]["score"] == 0.87

    def test_load_missing_cache(self, tmp_path) -> None:
        """Missing cache → empty dict."""
        loaded = load_scores_cache(str(tmp_path / "nonexistent"))
        assert loaded == {}

    def test_cache_file_created(self, tmp_path) -> None:
        """Cache file is created in the right location."""
        save_scores_cache({"test": {"score": 0.5}}, str(tmp_path))
        assert (tmp_path / "provider_scores.json").is_file()


def _write_outcomes(audit_dir, model: str, count: int, status: str = "done", cost: float = 0.003) -> None:
    """Helper: write N outcome records to a JSONL file."""
    jsonl = audit_dir / "audit.jsonl"
    existing = jsonl.read_text() if jsonl.exists() else ""
    lines = []
    for _ in range(count):
        lines.append(
            json.dumps(
                {
                    "model": model,
                    "status": status,
                    "completed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "cost_usd": cost,
                    "duration_sec": 2.5,
                }
            )
        )
    jsonl.write_text(existing + "\n".join(lines) + "\n")


# -- sig: mgh-6201.cd.bd955f.5c0e.e35e50
