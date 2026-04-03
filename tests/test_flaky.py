# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Tests for rondo.flaky — Rondo-REQ-107 task flakiness detection.

VER-001 verification matrix: flip detection, scoring, grouping, thresholds.
"""

import json

from rondo.flaky import (
    DispatchOutcome,
    FlakinessSummary,
    FlakyEngine,
    RootCause,
    compute_flakiness_score,
    detect_flips,
)

# -- ──────────────────────────────────────────────────────────────
# --  REQ-107 req 001 — Track per-task-template results
# -- ──────────────────────────────────────────────────────────────


class TestDispatchOutcome:
    """REQ-107 req 001: track results per task template."""

    def test_outcome_has_required_fields(self):
        """DispatchOutcome has task_name, prompt_hash, model, status, run_at."""
        outcome = DispatchOutcome(
            task_name="review_code",
            prompt_hash="sha256:abc123",
            model="claude-sonnet-4-6",
            status="done",
            confidence=0.95,
            run_at="2026-03-20T03:14:00Z",
        )
        assert outcome.task_name == "review_code"
        assert outcome.prompt_hash == "sha256:abc123"
        assert outcome.model == "claude-sonnet-4-6"
        assert outcome.status == "done"

    def test_outcome_has_confidence(self):
        """DispatchOutcome tracks confidence score."""
        outcome = DispatchOutcome(
            task_name="t", prompt_hash="h", model="m",
            status="done", confidence=0.85, run_at="now",
        )
        assert outcome.confidence == 0.85


# -- ──────────────────────────────────────────────────────────────
# --  REQ-107 req 002 — Group by (task_name + prompt_hash)
# -- ──────────────────────────────────────────────────────────────


class TestGrouping:
    """REQ-107 req 002: group by task_name + prompt_hash for comparison."""

    def test_same_prompt_grouped(self):
        """Same task+prompt_hash are in same group."""
        engine = FlakyEngine()
        engine.add_outcome(DispatchOutcome(
            task_name="review", prompt_hash="sha256:aaa",
            model="m", status="done", confidence=0.9, run_at="2026-03-20T01:00:00Z",
        ))
        engine.add_outcome(DispatchOutcome(
            task_name="review", prompt_hash="sha256:aaa",
            model="m", status="error", confidence=0.3, run_at="2026-03-20T02:00:00Z",
        ))
        groups = engine.get_groups()
        assert len(groups) == 1
        assert len(groups[("review", "sha256:aaa")]) == 2

    def test_different_prompts_separate_groups(self):
        """Different prompt_hash = different group."""
        engine = FlakyEngine()
        engine.add_outcome(DispatchOutcome(
            task_name="review", prompt_hash="sha256:aaa",
            model="m", status="done", confidence=0.9, run_at="2026-03-20T01:00:00Z",
        ))
        engine.add_outcome(DispatchOutcome(
            task_name="review", prompt_hash="sha256:bbb",
            model="m", status="done", confidence=0.9, run_at="2026-03-20T02:00:00Z",
        ))
        groups = engine.get_groups()
        assert len(groups) == 2


# -- ──────────────────────────────────────────────────────────────
# --  REQ-107 req 003 — Flakiness score calculation
# -- ──────────────────────────────────────────────────────────────


class TestFlakinessScore:
    """REQ-107 req 003: flakiness score = flips / total runs."""

    def test_all_same_status_zero_flakiness(self):
        """No flips = 0% flakiness."""
        outcomes = [
            DispatchOutcome(task_name="t", prompt_hash="h", model="m",
                          status="done", confidence=0.9, run_at=f"2026-03-{20+i}T01:00:00Z")
            for i in range(5)
        ]
        score = compute_flakiness_score(outcomes)
        assert score == 0.0

    def test_alternating_status_high_flakiness(self):
        """Alternating done/error = high flakiness."""
        statuses = ["done", "error", "done", "error", "done"]
        outcomes = [
            DispatchOutcome(task_name="t", prompt_hash="h", model="m",
                          status=s, confidence=0.5, run_at=f"2026-03-{20+i}T01:00:00Z")
            for i, s in enumerate(statuses)
        ]
        score = compute_flakiness_score(outcomes)
        # -- 4 flips out of 5 runs = 80%
        assert score > 0.5

    def test_single_run_zero_flakiness(self):
        """Single run can't flip = 0%."""
        outcomes = [
            DispatchOutcome(task_name="t", prompt_hash="h", model="m",
                          status="done", confidence=0.9, run_at="2026-03-20T01:00:00Z"),
        ]
        score = compute_flakiness_score(outcomes)
        assert score == 0.0

    def test_one_flip_among_many(self):
        """One flip in 10 runs = low flakiness."""
        outcomes = [
            DispatchOutcome(task_name="t", prompt_hash="h", model="m",
                          status="done" if i != 5 else "error",
                          confidence=0.9, run_at=f"2026-03-{10+i}T01:00:00Z")
            for i in range(10)
        ]
        score = compute_flakiness_score(outcomes)
        # -- 2 flips (done→error, error→done) out of 10 = 20%
        assert 0.1 <= score <= 0.3


# -- ──────────────────────────────────────────────────────────────
# --  REQ-107 req 004 — Flip detection
# -- ──────────────────────────────────────────────────────────────


class TestFlipDetection:
    """REQ-107 req 004: flip = status change between consecutive runs."""

    def test_detect_flip(self):
        """done→error is a flip."""
        outcomes = [
            DispatchOutcome(task_name="t", prompt_hash="h", model="m",
                          status="done", confidence=0.9, run_at="2026-03-20T01:00:00Z"),
            DispatchOutcome(task_name="t", prompt_hash="h", model="m",
                          status="error", confidence=0.1, run_at="2026-03-20T02:00:00Z"),
        ]
        flips = detect_flips(outcomes)
        assert len(flips) == 1

    def test_no_flip_same_status(self):
        """done→done is NOT a flip."""
        outcomes = [
            DispatchOutcome(task_name="t", prompt_hash="h", model="m",
                          status="done", confidence=0.9, run_at="2026-03-20T01:00:00Z"),
            DispatchOutcome(task_name="t", prompt_hash="h", model="m",
                          status="done", confidence=0.8, run_at="2026-03-20T02:00:00Z"),
        ]
        flips = detect_flips(outcomes)
        assert len(flips) == 0

    def test_partial_counts_as_flip(self):
        """done→partial is a flip."""
        outcomes = [
            DispatchOutcome(task_name="t", prompt_hash="h", model="m",
                          status="done", confidence=0.9, run_at="2026-03-20T01:00:00Z"),
            DispatchOutcome(task_name="t", prompt_hash="h", model="m",
                          status="partial", confidence=0.5, run_at="2026-03-20T02:00:00Z"),
        ]
        flips = detect_flips(outcomes)
        assert len(flips) == 1


# -- ──────────────────────────────────────────────────────────────
# --  REQ-107 req 005 — Flakiness threshold
# -- ──────────────────────────────────────────────────────────────


class TestFlakinessThreshold:
    """REQ-107 req 005: flakiness >20% = flagged flaky."""

    def test_above_threshold_flagged(self):
        """Alternating done/error exceeds 20% threshold."""
        engine = FlakyEngine()
        for i, s in enumerate(["done", "error", "done", "error", "done"]):
            engine.add_outcome(DispatchOutcome(
                task_name="unstable", prompt_hash="sha256:abc",
                model="m", status=s, confidence=0.5,
                run_at=f"2026-03-{20+i}T01:00:00Z",
            ))
        flaky = engine.get_flaky_tasks()
        assert len(flaky) == 1
        assert flaky[0].task_name == "unstable"

    def test_below_threshold_not_flagged(self):
        """Stable task not flagged."""
        engine = FlakyEngine()
        for i in range(10):
            engine.add_outcome(DispatchOutcome(
                task_name="stable", prompt_hash="sha256:abc",
                model="m", status="done", confidence=0.9,
                run_at=f"2026-03-{10+i}T01:00:00Z",
            ))
        flaky = engine.get_flaky_tasks()
        assert len(flaky) == 0


# -- ──────────────────────────────────────────────────────────────
# --  REQ-107 req 006 — Root cause categories
# -- ──────────────────────────────────────────────────────────────


class TestRootCause:
    """REQ-107 req 006: root cause categorization."""

    def test_root_cause_enum(self):
        """RootCause has required categories."""
        assert RootCause.PROMPT.value == "PROMPT"
        assert RootCause.MODEL.value == "MODEL"
        assert RootCause.CONTEXT.value == "CONTEXT"
        assert RootCause.TEMPERATURE.value == "TEMPERATURE"
        assert RootCause.UNKNOWN.value == "UNKNOWN"


# -- ──────────────────────────────────────────────────────────────
# --  REQ-107 req 010 — Per-model flakiness
# -- ──────────────────────────────────────────────────────────────


class TestPerModelFlakiness:
    """REQ-107 req 010: track which models are flakier."""

    def test_model_flakiness_stats(self):
        """Engine reports per-model flakiness breakdown."""
        engine = FlakyEngine()
        # -- Sonnet is flaky
        for i, s in enumerate(["done", "error", "done", "error"]):
            engine.add_outcome(DispatchOutcome(
                task_name="t", prompt_hash="sha256:same",
                model="claude-sonnet-4-6", status=s, confidence=0.5,
                run_at=f"2026-03-{20+i}T01:00:00Z",
            ))
        # -- Haiku is stable
        for i in range(4):
            engine.add_outcome(DispatchOutcome(
                task_name="t", prompt_hash="sha256:same",
                model="claude-haiku-4-5", status="done", confidence=0.9,
                run_at=f"2026-03-{20+i}T02:00:00Z",
            ))
        stats = engine.get_model_stats()
        assert stats["claude-sonnet-4-6"]["flakiness"] > stats["claude-haiku-4-5"]["flakiness"]


# -- ──────────────────────────────────────────────────────────────
# --  REQ-107 req 011 — Confidence variance
# -- ──────────────────────────────────────────────────────────────


class TestConfidenceVariance:
    """REQ-107 req 011: high confidence variance = unstable task definition."""

    def test_high_variance_detected(self):
        """Confidence range 0.3-0.9 flagged as unstable."""
        engine = FlakyEngine()
        for conf in [0.3, 0.9, 0.4, 0.8, 0.5]:
            engine.add_outcome(DispatchOutcome(
                task_name="unstable", prompt_hash="sha256:abc",
                model="m", status="done", confidence=conf,
                run_at="2026-03-20T01:00:00Z",
            ))
        summary = engine.get_summary("unstable", "sha256:abc")
        assert summary.confidence_variance > 0.03

    def test_low_variance_stable(self):
        """Confidence range 0.88-0.92 is stable."""
        engine = FlakyEngine()
        for conf in [0.88, 0.90, 0.91, 0.89, 0.92]:
            engine.add_outcome(DispatchOutcome(
                task_name="stable", prompt_hash="sha256:abc",
                model="m", status="done", confidence=conf,
                run_at="2026-03-20T01:00:00Z",
            ))
        summary = engine.get_summary("stable", "sha256:abc")
        assert summary.confidence_variance < 0.01


# -- ──────────────────────────────────────────────────────────────
# --  Edge cases
# -- ──────────────────────────────────────────────────────────────


class TestFlakyEdgeCases:
    """Edge cases for flakiness detection."""

    def test_empty_engine(self):
        """No outcomes = no flaky tasks."""
        engine = FlakyEngine()
        assert engine.get_flaky_tasks() == []

    def test_to_json(self):
        """FlakinessSummary serializes to JSON."""
        summary = FlakinessSummary(
            task_name="t", prompt_hash="h", flakiness_score=0.25,
            total_runs=10, flip_count=2, root_cause=RootCause.UNKNOWN,
            confidence_variance=0.05,
        )
        data = json.loads(json.dumps(summary.to_dict()))
        assert data["flakiness_score"] == 0.25
        assert data["root_cause"] == "UNKNOWN"

    def test_outcomes_sorted_by_time(self):
        """Outcomes sorted chronologically for correct flip detection."""
        engine = FlakyEngine()
        # -- Add out of order
        engine.add_outcome(DispatchOutcome(
            task_name="t", prompt_hash="sha256:a",
            model="m", status="error", confidence=0.1,
            run_at="2026-03-22T01:00:00Z",
        ))
        engine.add_outcome(DispatchOutcome(
            task_name="t", prompt_hash="sha256:a",
            model="m", status="done", confidence=0.9,
            run_at="2026-03-20T01:00:00Z",
        ))
        engine.add_outcome(DispatchOutcome(
            task_name="t", prompt_hash="sha256:a",
            model="m", status="done", confidence=0.9,
            run_at="2026-03-21T01:00:00Z",
        ))
        groups = engine.get_groups()
        outcomes = groups[("t", "sha256:a")]
        # -- Should be sorted: 20, 21, 22
        assert outcomes[0].run_at < outcomes[1].run_at < outcomes[2].run_at


# -- sig: mgh-6201.cd.bd955f.f1a3.94a3b4
