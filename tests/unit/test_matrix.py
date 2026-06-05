# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Tests for rondo.matrix — REQ-113 experiment matrix (RONDO-308).

Driver: the USH essay-split protocol run by hand (PROTOCOL.md 2026-06-03).
Dispatch is injected — these tests never touch a network or a real provider.
"""

import json
from pathlib import Path

import pytest

from rondo.matrix import (
    MatrixError,
    build_grid,
    estimate_grid_cost,
    load_matrix,
    matrix_report,
    reveal_matrix,
    run_matrix,
)

# -- ──────────────────────────────────────────────────────────────
# --  Helpers
# -- ──────────────────────────────────────────────────────────────

GOOD_YAML = """\
name: demo
prompt: "Reply with exactly: OK"
models: [anthropic:claude-opus-4-8, openai:gpt-5.5]
efforts: [low, max]
contexts:
  blind: none
replicates: 2
budget_usd: 1.00
"""


def _write_yaml(tmp_path: Path, text: str = GOOD_YAML) -> str:
    p = tmp_path / "exp.yaml"
    p.write_text(text, encoding="utf-8")
    return str(p)


def _ok_dispatch(cell: dict, prompt: str) -> dict:
    """Injected dispatch — always succeeds, tiny cost, fake self-rating."""
    return {
        "status": "done",
        "cost_usd": 0.01,
        "latency_sec": 1.0,
        "output": '{"passed": true, "confidence": 0.9, "result": "OK"}',
        "self_rating": 8.0,
    }


def _always_effort_capable(model: str) -> bool:
    return True


# -- ──────────────────────────────────────────────────────────────
# --  Reqs 001-004: definition + grid
# -- ──────────────────────────────────────────────────────────────


class TestMatrixDefinition:
    def test_load_valid_yaml(self, tmp_path: Path) -> None:
        spec = load_matrix(_write_yaml(tmp_path))
        assert spec.name == "demo"
        assert spec.replicates == 2

    def test_unknown_field_rejected(self, tmp_path: Path) -> None:
        """REQ-113 req 003: unknown fields rejected with clear error."""
        bad = GOOD_YAML + "surprise_field: 1\n"
        with pytest.raises(MatrixError, match="surprise_field"):
            load_matrix(_write_yaml(tmp_path, bad))

    def test_missing_required_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(MatrixError, match="models"):
            load_matrix(_write_yaml(tmp_path, "name: x\nprompt: p\nbudget_usd: 1.0\n"))

    def test_grid_size(self, tmp_path: Path) -> None:
        """REQ-113 req 002: models × efforts × contexts × replicates."""
        spec = load_matrix(_write_yaml(tmp_path))
        cells = build_grid(spec, effort_capable=_always_effort_capable)
        assert len(cells) == 2 * 2 * 1 * 2  # -- 8 cells

    def test_effort_collapse_for_non_capable(self, tmp_path: Path) -> None:
        """REQ-113 req 004: non-effort models collapse the effort axis — no dup spend."""
        spec = load_matrix(_write_yaml(tmp_path))
        cells = build_grid(spec, effort_capable=lambda m: m.startswith("anthropic"))
        anthropic = [c for c in cells if c["model"].startswith("anthropic")]
        openai = [c for c in cells if c["model"].startswith("openai")]
        assert len(anthropic) == 2 * 1 * 2  # -- both efforts
        assert len(openai) == 1 * 1 * 2  # -- collapsed to one, effort n/a
        assert all(c["effort"] == "n/a" for c in openai)


# -- ──────────────────────────────────────────────────────────────
# --  Reqs 010-012: budget gates
# -- ──────────────────────────────────────────────────────────────


class TestBudgetGates:
    def test_estimate_abort_over_budget(self, tmp_path: Path) -> None:
        """REQ-113 req 010: estimate > budget → abort BEFORE any dispatch."""
        spec = load_matrix(_write_yaml(tmp_path, GOOD_YAML.replace("budget_usd: 1.00", "budget_usd: 0.000001")))
        calls = []

        def counting(cell: dict, prompt: str) -> dict:
            calls.append(cell)
            return _ok_dispatch(cell, prompt)

        with pytest.raises(MatrixError, match="budget"):
            run_matrix(spec, dispatch=counting, effort_capable=_always_effort_capable, base_dir=str(tmp_path))
        assert calls == []

    def test_running_budget_stop(self, tmp_path: Path) -> None:
        """REQ-113 req 012: spend reaching budget skips remaining cells, keeps results."""
        spec = load_matrix(_write_yaml(tmp_path))
        spec.budget_usd = 0.025  # -- room for ~2 cells at 0.01 actual

        def pricey(cell: dict, prompt: str) -> dict:
            out = _ok_dispatch(cell, prompt)
            out["cost_usd"] = 0.012
            return out

        manifest = run_matrix(
            spec, dispatch=pricey, effort_capable=_always_effort_capable, base_dir=str(tmp_path), estimate_ok=True
        )
        statuses = [c["status"] for c in manifest["cells"].values()]
        assert "budget_exhausted" in statuses
        assert statuses.count("done") >= 1

    def test_estimate_grid_cost_positive(self, tmp_path: Path) -> None:
        spec = load_matrix(_write_yaml(tmp_path))
        cells = build_grid(spec, effort_capable=_always_effort_capable)
        assert estimate_grid_cost(cells, spec.prompt) > 0


# -- ──────────────────────────────────────────────────────────────
# --  Reqs 020-023, 030: execution + manifest + resume + isolation
# -- ──────────────────────────────────────────────────────────────


class TestExecution:
    def test_manifest_written_with_all_cells(self, tmp_path: Path) -> None:
        spec = load_matrix(_write_yaml(tmp_path))
        manifest = run_matrix(
            spec, dispatch=_ok_dispatch, effort_capable=_always_effort_capable, base_dir=str(tmp_path), estimate_ok=True
        )
        assert len(manifest["cells"]) == 8
        assert (tmp_path / "demo" / "manifest.json").exists()

    def test_cell_failure_never_aborts(self, tmp_path: Path) -> None:
        """REQ-113 req 023: one bad cell, run continues (STD-108 rule 6)."""
        spec = load_matrix(_write_yaml(tmp_path))

        def flaky(cell: dict, prompt: str) -> dict:
            if cell["replicate"] == 1 and cell["model"].startswith("openai"):
                raise OSError("provider exploded")
            return _ok_dispatch(cell, prompt)

        manifest = run_matrix(
            spec, dispatch=flaky, effort_capable=_always_effort_capable, base_dir=str(tmp_path), estimate_ok=True
        )
        statuses = [c["status"] for c in manifest["cells"].values()]
        assert "error" in statuses
        assert statuses.count("done") >= 4

    def test_resume_skips_done_cells(self, tmp_path: Path) -> None:
        """REQ-113 req 022: re-run skips done cells (idempotent by cell key)."""
        spec = load_matrix(_write_yaml(tmp_path))
        run_matrix(
            spec, dispatch=_ok_dispatch, effort_capable=_always_effort_capable, base_dir=str(tmp_path), estimate_ok=True
        )
        second_calls = []

        def counting(cell: dict, prompt: str) -> dict:
            second_calls.append(cell)
            return _ok_dispatch(cell, prompt)

        run_matrix(
            spec, dispatch=counting, effort_capable=_always_effort_capable, base_dir=str(tmp_path), estimate_ok=True
        )
        assert second_calls == []


# -- ──────────────────────────────────────────────────────────────
# --  Reqs 031-033: report, replicates, self-rating honesty
# -- ──────────────────────────────────────────────────────────────


class TestReport:
    def _run(self, tmp_path: Path, dispatch=_ok_dispatch) -> None:
        spec = load_matrix(_write_yaml(tmp_path))
        run_matrix(
            spec, dispatch=dispatch, effort_capable=_always_effort_capable, base_dir=str(tmp_path), estimate_ok=True
        )

    def test_report_has_replicate_stats(self, tmp_path: Path) -> None:
        """REQ-113 req 032: mean ± stdev over replicates."""
        ratings = iter([6.0, 10.0] * 8)

        def vary(cell: dict, prompt: str) -> dict:
            out = _ok_dispatch(cell, prompt)
            out["self_rating"] = next(ratings)
            return out

        self._run(tmp_path, vary)
        text = matrix_report("demo", base_dir=str(tmp_path))
        assert "±" in text
        assert "noisy" in text.lower()

    def test_self_ratings_labeled_uncalibrated(self, tmp_path: Path) -> None:
        """REQ-113 req 033: self-ratings never trusted silently."""
        self._run(tmp_path)
        text = matrix_report("demo", base_dir=str(tmp_path))
        assert "uncalibrated" in text


# -- ──────────────────────────────────────────────────────────────
# --  Reqs 040-042: blind scoring
# -- ──────────────────────────────────────────────────────────────


class TestBlind:
    def _run_blind(self, tmp_path: Path) -> None:
        spec = load_matrix(_write_yaml(tmp_path, GOOD_YAML + "blind: true\n"))
        run_matrix(
            spec, dispatch=_ok_dispatch, effort_capable=_always_effort_capable, base_dir=str(tmp_path), estimate_ok=True
        )

    def test_blind_report_shows_codes_only(self, tmp_path: Path) -> None:
        """REQ-113 reqs 040-041: model names hidden until reveal."""
        self._run_blind(tmp_path)
        text = matrix_report("demo", base_dir=str(tmp_path))
        assert "cell-" in text
        assert "claude-opus-4-8" not in text

    def test_reveal_prints_mapping_and_verifies_seal(self, tmp_path: Path) -> None:
        """REQ-113 reqs 041-042: reveal shows mapping; seal hash verifies."""
        self._run_blind(tmp_path)
        mapping = reveal_matrix("demo", base_dir=str(tmp_path))
        assert any("claude-opus-4-8" in v for v in mapping.values())
        text = matrix_report("demo", base_dir=str(tmp_path))
        assert "claude-opus-4-8" in text  # -- after reveal, report de-anonymizes


# -- ──────────────────────────────────────────────────────────────
# --  Req 050: baseline mechanical deltas
# -- ──────────────────────────────────────────────────────────────


class TestBaseline:
    def test_baseline_deltas_in_report(self, tmp_path: Path) -> None:
        base = tmp_path / "baseline.md"
        base.write_text("# Plan\n## A\n## B\n", encoding="utf-8")
        spec = load_matrix(_write_yaml(tmp_path, GOOD_YAML + f"baseline: {base}\n"))
        run_matrix(
            spec, dispatch=_ok_dispatch, effort_capable=_always_effort_capable, base_dir=str(tmp_path), estimate_ok=True
        )
        text = matrix_report("demo", base_dir=str(tmp_path))
        assert "len×" in text or "len x" in text


# -- sig: mgh-6201.cd.bd955f.f1a9.mx308a
