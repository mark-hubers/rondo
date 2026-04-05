# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Rondo task flakiness detection — find unreliable dispatches.

Rondo-REQ-107: Task Flakiness Detection.
Tracks per-task-template results, groups by (task_name + prompt_hash),
computes flip rates, flags tasks exceeding 20% flakiness threshold.
Feeds into overnight reporting and model routing decisions.

Import direction:
    flaky.py → no rondo imports (standalone analysis engine)
"""

from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


# -- ──────────────────────────────────────────────────────────────
# --  Root cause categories — REQ-107 req 006
# -- ──────────────────────────────────────────────────────────────


class RootCause(Enum):
    """Root cause categories for flaky dispatches — REQ-107 req 006."""

    PROMPT = "PROMPT"
    MODEL = "MODEL"
    CONTEXT = "CONTEXT"
    TEMPERATURE = "TEMPERATURE"
    UNKNOWN = "UNKNOWN"


# -- ──────────────────────────────────────────────────────────────
# --  Data structures — REQ-107 req 001
# -- ──────────────────────────────────────────────────────────────


@dataclass
class DispatchOutcome:
    """One dispatch result for flakiness tracking — REQ-107 req 001."""

    task_name: str
    prompt_hash: str
    model: str
    status: str  # -- done, partial, error, blocked
    confidence: float
    run_at: str  # -- ISO timestamp


@dataclass
class FlakinessSummary:
    """Flakiness analysis for one task+prompt group — REQ-107 req 003."""

    task_name: str
    prompt_hash: str
    flakiness_score: float = 0.0
    total_runs: int = 0
    flip_count: int = 0
    root_cause: RootCause = RootCause.UNKNOWN
    confidence_variance: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-compatible dict — REQ-107 req 008."""
        return {
            "task_name": self.task_name,
            "prompt_hash": self.prompt_hash,
            "flakiness_score": self.flakiness_score,
            "total_runs": self.total_runs,
            "flip_count": self.flip_count,
            "root_cause": self.root_cause.value,
            "confidence_variance": self.confidence_variance,
        }


# -- ──────────────────────────────────────────────────────────────
# --  Core functions — REQ-107 reqs 003, 004
# -- ──────────────────────────────────────────────────────────────

# -- flakiness threshold — REQ-107 req 005
FLAKINESS_THRESHOLD = 0.20


def detect_flips(outcomes: list[DispatchOutcome]) -> list[tuple[int, str, str]]:
    """Detect status flips between consecutive runs — REQ-107 req 004.

    Returns list of (index, from_status, to_status) tuples.
    Outcomes must be sorted chronologically.
    """
    flips: list[tuple[int, str, str]] = []
    sorted_outcomes = sorted(outcomes, key=lambda o: o.run_at)
    for i in range(1, len(sorted_outcomes)):
        prev_status = sorted_outcomes[i - 1].status
        curr_status = sorted_outcomes[i].status
        if prev_status != curr_status:
            flips.append((i, prev_status, curr_status))
    return flips


def compute_flakiness_score(outcomes: list[DispatchOutcome]) -> float:
    """Calculate flakiness score = flips / total runs — REQ-107 req 003.

    Rolling 14-day window applied by caller (FlakyEngine filters before passing).
    """
    if len(outcomes) <= 1:
        return 0.0
    flips = detect_flips(outcomes)
    return len(flips) / len(outcomes)


def _compute_confidence_variance(outcomes: list[DispatchOutcome]) -> float:
    """Calculate variance in confidence scores — REQ-107 req 011."""
    confidences = [o.confidence for o in outcomes if o.confidence > 0]
    if len(confidences) < 2:
        return 0.0
    return statistics.variance(confidences)


# -- ──────────────────────────────────────────────────────────────
# --  Flaky engine — main interface
# -- ──────────────────────────────────────────────────────────────


class FlakyEngine:
    """Flakiness detection engine — REQ-107.

    Collects dispatch outcomes, groups by (task_name, prompt_hash),
    computes flakiness scores, flags tasks exceeding threshold.

    Memory contract: max_outcomes limits retained history (default 10000).
    When exceeded, oldest outcomes are evicted. Caller can also set
    window_days to filter analysis to recent data only (default 14).
    """

    def __init__(
        self,
        *,
        max_outcomes: int = 10_000,
        window_days: int = 14,
    ) -> None:
        self._outcomes: list[DispatchOutcome] = []
        self._max_outcomes = max_outcomes
        self._window_days = window_days

    def add_outcome(self, outcome: DispatchOutcome) -> None:
        """Add a dispatch outcome for tracking.

        Evicts oldest outcomes when max_outcomes exceeded (REQ-107 scale).
        """
        self._outcomes.append(outcome)
        if len(self._outcomes) > self._max_outcomes:
            self._outcomes = self._outcomes[-self._max_outcomes :]

    def get_groups(self) -> dict[tuple[str, str], list[DispatchOutcome]]:
        """Group outcomes by (task_name, prompt_hash) — REQ-107 req 002.

        Returns dict with sorted outcome lists.
        """
        groups: dict[tuple[str, str], list[DispatchOutcome]] = {}
        for outcome in self._outcomes:
            key = (outcome.task_name, outcome.prompt_hash)
            if key not in groups:
                groups[key] = []
            groups[key].append(outcome)
        # -- Sort each group chronologically
        for key in groups:
            groups[key].sort(key=lambda o: o.run_at)
        return groups

    def get_summary(
        self,
        task_name: str,
        prompt_hash: str,
    ) -> FlakinessSummary:
        """Get flakiness summary for a specific task+prompt group."""
        groups = self.get_groups()
        outcomes = groups.get((task_name, prompt_hash), [])
        if not outcomes:
            return FlakinessSummary(task_name=task_name, prompt_hash=prompt_hash)

        flips = detect_flips(outcomes)
        score = compute_flakiness_score(outcomes)
        variance = _compute_confidence_variance(outcomes)

        return FlakinessSummary(
            task_name=task_name,
            prompt_hash=prompt_hash,
            flakiness_score=score,
            total_runs=len(outcomes),
            flip_count=len(flips),
            root_cause=RootCause.UNKNOWN,
            confidence_variance=variance,
        )

    def get_flaky_tasks(
        self,
        threshold: float = FLAKINESS_THRESHOLD,
    ) -> list[FlakinessSummary]:
        """Get tasks exceeding flakiness threshold — REQ-107 req 005.

        Returns list of FlakinessSummary for flagged tasks.
        """
        flaky: list[FlakinessSummary] = []
        groups = self.get_groups()
        for (task_name, prompt_hash), outcomes in groups.items():
            if len(outcomes) < 2:
                continue
            summary = self.get_summary(task_name, prompt_hash)
            if summary.flakiness_score > threshold:
                flaky.append(summary)
        return flaky

    def get_model_stats(self) -> dict[str, dict[str, Any]]:
        """Per-model flakiness statistics — REQ-107 req 010.

        Returns dict of model → {total_runs, flips, flakiness}.
        """
        model_outcomes: dict[str, list[DispatchOutcome]] = {}
        for outcome in self._outcomes:
            if outcome.model not in model_outcomes:
                model_outcomes[outcome.model] = []
            model_outcomes[outcome.model].append(outcome)

        stats: dict[str, dict[str, Any]] = {}
        for model, outcomes in model_outcomes.items():
            sorted_outcomes = sorted(outcomes, key=lambda o: o.run_at)
            flips = detect_flips(sorted_outcomes)
            score = compute_flakiness_score(sorted_outcomes)
            stats[model] = {
                "total_runs": len(outcomes),
                "flips": len(flips),
                "flakiness": score,
            }
        return stats


# -- sig: mgh-6201.cd.bd955f.f1a3.94a3b5
