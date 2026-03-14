# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Tests for Rondo living examples — REQ-001 reqs 42-44.

VER-001 verification matrix: example rounds as test fixtures.
Examples serve dual purpose: user documentation AND automated test fixtures.

Two categories:
  - Spec examples (round_hello, round_file_check, round_multi_task): minimal, under 50 lines
  - Practical examples (round_code_review, etc.): real-world patterns, no size limit
"""

import importlib.util
import sys
from pathlib import Path

import pytest

# -- Add rondo/src to path so we can import rondo
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from rondo.engine import Round

# -- Example directory
EXAMPLES_DIR = Path(__file__).parent.parent / "examples"

# -- All round_*.py files (both spec and practical)
ALL_ROUND_FILES = sorted(EXAMPLES_DIR.glob("round_*.py"))

# -- All files with build_phases() (overnight examples)
ALL_PHASE_FILES = sorted(EXAMPLES_DIR.glob("phases_*.py"))

# -- Spec-mandated examples (must be under 50 lines)
SPEC_EXAMPLES = {"round_hello.py", "round_file_check.py", "round_multi_task.py"}


# ──────────────────────────────────────────────────────────────────
#  Helpers
# ──────────────────────────────────────────────────────────────────


def _load_example(name: str):
    """Dynamically import an example file and return the module."""
    path = EXAMPLES_DIR / name
    assert path.exists(), f"Example file not found: {path}"
    spec = importlib.util.spec_from_file_location(f"example_{name}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ──────────────────────────────────────────────────────────────────
#  REQ-001 req 44 — at least 3 examples ship
# ──────────────────────────────────────────────────────────────────


class TestExampleCount:
    def test_at_least_three_examples(self):
        """REQ-001 req 44: at minimum 3 examples ship."""
        assert len(ALL_ROUND_FILES) >= 3, f"Expected 3+ examples, found {len(ALL_ROUND_FILES)}"

    def test_expected_spec_files_present(self):
        """The 3 spec-mandated examples exist."""
        names = {f.name for f in ALL_ROUND_FILES}
        for expected in SPEC_EXAMPLES:
            assert expected in names, f"Missing spec example: {expected}"

    def test_practical_examples_present(self):
        """Practical examples exist beyond the spec minimum."""
        names = {f.name for f in ALL_ROUND_FILES}
        practical = names - SPEC_EXAMPLES
        assert len(practical) >= 3, f"Expected 3+ practical examples, found {len(practical)}"

    def test_overnight_example_present(self):
        """At least one overnight phases example exists."""
        assert len(ALL_PHASE_FILES) >= 1, "No phases_*.py overnight examples found"


# ──────────────────────────────────────────────────────────────────
#  REQ-001 req 42 — build_round() function exists on all round files
# ──────────────────────────────────────────────────────────────────


class TestExampleBuildRound:
    @pytest.mark.parametrize("example_file", ALL_ROUND_FILES, ids=lambda p: p.name)
    def test_has_build_round(self, example_file):
        """REQ-001 req 42: every round example has build_round()."""
        module = _load_example(example_file.name)
        assert hasattr(module, "build_round"), f"{example_file.name} missing build_round()"
        assert callable(module.build_round)

    @pytest.mark.parametrize("example_file", ALL_ROUND_FILES, ids=lambda p: p.name)
    def test_build_round_returns_round(self, example_file):
        """REQ-001 req 42: build_round() returns a Round."""
        module = _load_example(example_file.name)
        result = module.build_round()
        assert isinstance(result, Round), f"build_round() returned {type(result).__name__}, not Round"


# ──────────────────────────────────────────────────────────────────
#  REQ-001 req 43 — spec examples used as test fixtures
# ──────────────────────────────────────────────────────────────────


class TestSpecExamplesAsFixtures:
    def test_hello_round_structure(self):
        """round_hello.py: 1 task, no gates."""
        module = _load_example("round_hello.py")
        r = module.build_round()
        assert r.name == "hello"
        assert len(r.tasks) == 1
        assert r.tasks[0].name == "Say hello"
        assert r.pre_gates == []
        assert r.post_gates == []

    def test_file_check_round_structure(self):
        """round_file_check.py: 1 pre-gate, 2 tasks (1 auto + 1 interactive)."""
        module = _load_example("round_file_check.py")
        r = module.build_round()
        assert r.name == "file-check"
        assert len(r.pre_gates) == 1
        assert len(r.tasks) == 2
        # -- First task is auto (has auto_fn)
        assert r.tasks[0].auto_fn is not None
        # -- Second task is interactive (has instruction)
        assert r.tasks[1].instruction is not None
        assert r.tasks[1].model == "haiku"

    def test_multi_task_round_structure(self):
        """round_multi_task.py: pre+post gates, 3 tasks with model hints."""
        module = _load_example("round_multi_task.py")
        r = module.build_round()
        assert r.name == "code-survey"
        assert len(r.pre_gates) == 1
        assert len(r.post_gates) == 1
        assert len(r.tasks) == 3
        assert r.tasks[1].model == "haiku"
        assert r.tasks[2].model == "sonnet"

    def test_multi_task_accepts_parameters(self):
        """round_multi_task.py: build_round() accepts target_dir parameter."""
        module = _load_example("round_multi_task.py")
        r = module.build_round(target_dir="/tmp/test")
        assert r.name == "code-survey"
        assert "/tmp/test" in r.tasks[1].instruction


# ──────────────────────────────────────────────────────────────────
#  Practical examples — structure validation
# ──────────────────────────────────────────────────────────────────


class TestPracticalExamples:
    def test_code_review_structure(self):
        """round_code_review.py: pre-gate (git), 1 review task."""
        module = _load_example("round_code_review.py")
        r = module.build_round()
        assert r.name == "code-review"
        assert len(r.pre_gates) == 1
        assert len(r.tasks) == 1
        assert r.tasks[0].model == "sonnet"

    def test_test_generator_structure(self):
        """round_test_generator.py: pre-gate, 1 auto + 1 interactive."""
        module = _load_example("round_test_generator.py")
        r = module.build_round()
        assert r.name == "test-generator"
        assert len(r.pre_gates) == 1
        assert len(r.tasks) == 2
        # -- First task is auto discovery
        assert r.tasks[0].auto_fn is not None
        # -- Second task is Claude-driven
        assert r.tasks[1].instruction != ""
        assert r.tasks[1].model == "sonnet"

    def test_test_generator_accepts_parameters(self):
        """round_test_generator.py: custom src_dir and test_dir."""
        module = _load_example("round_test_generator.py")
        r = module.build_round(src_dir="lib/", test_dir="spec/")
        assert "lib/" in r.tasks[1].instruction

    def test_doc_sweep_structure(self):
        """round_doc_sweep.py: parallel-safe tasks, auto-filters to existing files."""
        module = _load_example("round_doc_sweep.py")
        r = module.build_round()
        assert r.name == "doc-sweep"
        assert len(r.tasks) >= 1  # -- at least 1 (filters to what exists)
        for t in r.tasks:
            assert t.model == "haiku"

    def test_doc_sweep_custom_files(self):
        """round_doc_sweep.py: custom file list."""
        module = _load_example("round_doc_sweep.py")
        r = module.build_round(files=["A.md", "B.md"])
        assert len(r.tasks) == 2
        assert "A.md" in r.tasks[0].name

    def test_refactor_audit_structure(self):
        """round_refactor_audit.py: blocking + non-blocking pre-gates, post-gate."""
        module = _load_example("round_refactor_audit.py")
        r = module.build_round()
        assert r.name == "refactor-audit"
        assert len(r.pre_gates) == 2
        # -- First gate is blocking, second is non-blocking (warning)
        assert r.pre_gates[0].blocking is True
        assert r.pre_gates[1].blocking is False
        assert len(r.post_gates) == 1
        assert len(r.tasks) == 2

    def test_refactor_audit_accepts_target(self):
        """round_refactor_audit.py: custom target file."""
        module = _load_example("round_refactor_audit.py")
        r = module.build_round(target_file="app/server.py")
        assert "app/server.py" in r.tasks[0].instruction


# ──────────────────────────────────────────────────────────────────
#  Overnight phases example
# ──────────────────────────────────────────────────────────────────


class TestOvernightExample:
    def test_has_build_phases(self):
        """phases_overnight.py: has build_phases() function."""
        module = _load_example("phases_overnight.py")
        assert hasattr(module, "build_phases")
        assert callable(module.build_phases)

    def test_build_phases_returns_list_of_rounds(self):
        """phases_overnight.py: build_phases() returns list[Round]."""
        module = _load_example("phases_overnight.py")
        phases = module.build_phases()
        assert isinstance(phases, list)
        assert len(phases) >= 2
        for phase in phases:
            assert isinstance(phase, Round)

    def test_phases_are_ordered(self):
        """phases_overnight.py: phases have sequential names."""
        module = _load_example("phases_overnight.py")
        phases = module.build_phases()
        assert "phase-1" in phases[0].name
        assert "phase-2" in phases[1].name
        assert "phase-3" in phases[2].name

    def test_phases_escalate_models(self):
        """phases_overnight.py: later phases use more capable models."""
        module = _load_example("phases_overnight.py")
        phases = module.build_phases()
        # -- Phase 1: auto tasks only (no model needed)
        for t in phases[0].tasks:
            assert t.auto_fn is not None
        # -- Phase 2: haiku (fast/cheap)
        assert phases[1].tasks[0].model == "haiku"
        # -- Phase 3: sonnet (thorough)
        assert phases[2].tasks[0].model == "sonnet"

    def test_phases_accept_parameter(self):
        """phases_overnight.py: build_phases() accepts target_dir."""
        module = _load_example("phases_overnight.py")
        phases = module.build_phases(target_dir="lib/")
        # -- Verify the parameter propagated
        assert "lib/" in phases[1].tasks[0].instruction


# ──────────────────────────────────────────────────────────────────
#  REQ-001 req 32 — examples only import engine module
# ──────────────────────────────────────────────────────────────────


class TestExampleImports:
    @pytest.mark.parametrize(
        "example_file",
        ALL_ROUND_FILES + ALL_PHASE_FILES,
        ids=lambda p: p.name,
    )
    def test_only_imports_engine(self, example_file):
        """REQ-001 req 32: round files only import rondo.engine (+ stdlib)."""
        content = example_file.read_text()
        rondo_imports = [
            line.strip() for line in content.splitlines() if "from rondo" in line or "import rondo" in line
        ]
        for imp in rondo_imports:
            assert "rondo.engine" in imp, f"{example_file.name} imports non-engine rondo module: {imp}"


# ──────────────────────────────────────────────────────────────────
#  REQ-001 req 33 — SPEC examples under 50 lines (practical exempt)
# ──────────────────────────────────────────────────────────────────


class TestExampleSize:
    @pytest.mark.parametrize(
        "example_file",
        [f for f in ALL_ROUND_FILES if f.name in SPEC_EXAMPLES],
        ids=lambda p: p.name,
    )
    def test_spec_examples_under_50_lines(self, example_file):
        """REQ-001 req 33: spec-mandated examples under 50 lines."""
        lines = example_file.read_text().splitlines()
        assert len(lines) <= 50, f"{example_file.name} is {len(lines)} lines (max 50)"

    @pytest.mark.parametrize(
        "example_file",
        ALL_ROUND_FILES + ALL_PHASE_FILES,
        ids=lambda p: p.name,
    )
    def test_all_examples_under_100_lines(self, example_file):
        """Practical examples stay reasonable — under 100 lines."""
        lines = example_file.read_text().splitlines()
        assert len(lines) <= 100, f"{example_file.name} is {len(lines)} lines (max 100)"
