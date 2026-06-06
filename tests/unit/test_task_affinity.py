# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Tests for per-task model affinity — RONDO-315 (finding #297).

Scores were per-MODEL only: a model great at summarizing but bad at code
review got one blended score. The affinity chain: task_type rides the
AuditRecord → scoring groups by (task_type, model) → recommend_model
prefers the task-level learned winner over the global one.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from rondo.audit import AuditRecord
from rondo.engine import Task
from rondo.scoring import MIN_SAMPLE_COUNT, compute_task_scores


def _write_outcomes(
    audit_dir: Path,
    model: str,
    count: int,
    *,
    status: str = "done",
    task_type: str = "",
) -> None:
    """Write N outcome records, optionally tagged with a task_type."""
    audit_dir.mkdir(parents=True, exist_ok=True)
    jsonl = audit_dir / "audit.jsonl"
    existing = jsonl.read_text() if jsonl.exists() else ""
    lines = []
    for _ in range(count):
        rec = {
            "model": model,
            "status": status,
            "completed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "cost_usd": 0.003,
            "duration_sec": 2.5,
        }
        if task_type:
            rec["task_type"] = task_type
        lines.append(json.dumps(rec))
    jsonl.write_text(existing + "\n".join(lines) + "\n")


class TestTaskTypeField:
    """task_type rides Task and AuditRecord as an additive field."""

    def test_task_has_task_type_default_empty(self) -> None:
        task = Task(name="t1")
        assert task.task_type == ""

    def test_audit_record_carries_task_type(self) -> None:
        rec = AuditRecord(dispatch_id="dsp_x", task_type="code-review")
        assert rec.to_dict()["task_type"] == "code-review"

    def test_audit_record_task_type_defaults_empty(self) -> None:
        """Append-only schema: old records without the field stay readable."""
        assert AuditRecord(dispatch_id="dsp_y").to_dict()["task_type"] == ""


class TestRecordIntentPassThrough:
    """record_intent persists task_type into the JSONL trail."""

    def test_intent_record_includes_task_type(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))
        from rondo.audit import AuditConfig, AuditTrail

        trail = AuditTrail(config=AuditConfig(audit_dir=str(tmp_path / "audit")))
        rec = trail.record_intent(
            task_name="t1",
            round_name="r1",
            model="sonnet",
            prompt="hello",
            task_type="summarize",
        )
        assert rec.task_type == "summarize"
        log = (tmp_path / "audit" / "rondo_audit.jsonl").read_text()
        assert '"task_type": "summarize"' in log


class TestRoundLoaderTaskType:
    """Round files may declare task_type per task (REQ-111 req 414 set)."""

    def test_yaml_task_type_loads(self, tmp_path: Path) -> None:
        from rondo.round_loader import load_round

        round_file = tmp_path / "r.yaml"
        round_file.write_text(
            "name: affinity-demo\n"
            "tasks:\n"
            "  - name: t1\n"
            "    instruction: review this\n"
            "    done_when: reviewed\n"
            "    task_type: code-review\n"
        )
        loaded = load_round(str(round_file))
        assert loaded.tasks[0].task_type == "code-review"


class TestComputeTaskScores:
    """Scoring groups by (task_type, model) — the affinity table."""

    def test_groups_by_task_type_and_model(self, tmp_path: Path) -> None:
        _write_outcomes(tmp_path, "haiku", MIN_SAMPLE_COUNT, task_type="summarize")
        _write_outcomes(tmp_path, "opus", MIN_SAMPLE_COUNT, status="error", task_type="summarize")
        scores = compute_task_scores(str(tmp_path))
        assert "summarize" in scores
        assert scores["summarize"]["haiku"]["score"] > scores["summarize"]["opus"]["score"]

    def test_untyped_records_excluded(self, tmp_path: Path) -> None:
        """Legacy records without task_type never pollute the affinity table."""
        _write_outcomes(tmp_path, "sonnet", MIN_SAMPLE_COUNT)  # -- no task_type
        assert compute_task_scores(str(tmp_path)) == {}

    def test_min_sample_floor_per_pair(self, tmp_path: Path) -> None:
        """9 records of a (task, model) pair is below the signal floor."""
        _write_outcomes(tmp_path, "haiku", MIN_SAMPLE_COUNT - 1, task_type="summarize")
        assert compute_task_scores(str(tmp_path)) == {}

    def test_empty_dir_returns_empty(self, tmp_path: Path) -> None:
        assert compute_task_scores(str(tmp_path / "nope")) == {}


class TestRecommendModelAffinity:
    """recommend_model: override → curated → task-learned → global-learned → sonnet."""

    def test_task_learned_beats_global_learned(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        audit = tmp_path / "audit"
        ## -- globally, opus looks best (most volume, all green)...
        _write_outcomes(audit, "opus", MIN_SAMPLE_COUNT * 3)
        ## -- ...but for THIS task type, haiku is the proven winner
        _write_outcomes(audit, "haiku", MIN_SAMPLE_COUNT, task_type="weird-niche-task")
        monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))
        from rondo.providers import recommend_model

        assert recommend_model("weird-niche-task") == "haiku"

    def test_curated_default_still_wins_over_learned(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """REQ-109 req 320: learning fills the blind spot, never overrides curation."""
        audit = tmp_path / "audit"
        _write_outcomes(audit, "haiku", MIN_SAMPLE_COUNT, task_type="code-review")
        monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))
        from rondo.providers import _DEFAULT_TASK_MODELS, recommend_model

        assert recommend_model("code-review") == _DEFAULT_TASK_MODELS["code-review"]

    def test_unknown_task_no_data_falls_back(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))
        from rondo.providers import recommend_model

        assert recommend_model("never-seen-task") == "sonnet"
