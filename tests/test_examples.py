"""Tests for Rondo living examples — REQ-001 reqs 42-44.

VER-001 verification matrix: example rounds as test fixtures.
Examples serve dual purpose: user documentation AND automated test fixtures.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

# -- Add rondo/src to path so we can import rondo
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from rondo.engine import Gate, Round, Task

# -- Example directory
EXAMPLES_DIR = Path(__file__).parent.parent / "examples"


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


EXAMPLE_FILES = sorted(EXAMPLES_DIR.glob("round_*.py"))


# ──────────────────────────────────────────────────────────────────
#  REQ-001 req 44 — at least 3 examples ship
# ──────────────────────────────────────────────────────────────────

class TestExampleCount:

    def test_at_least_three_examples(self):
        """REQ-001 req 44: at minimum 3 examples ship."""
        assert len(EXAMPLE_FILES) >= 3, f"Expected 3+ examples, found {len(EXAMPLE_FILES)}"

    def test_expected_files_present(self):
        """The 3 spec-mandated examples exist."""
        names = {f.name for f in EXAMPLE_FILES}
        assert "round_hello.py" in names
        assert "round_file_check.py" in names
        assert "round_multi_task.py" in names


# ──────────────────────────────────────────────────────────────────
#  REQ-001 req 42 — build_round() function exists
# ──────────────────────────────────────────────────────────────────

class TestExampleBuildRound:

    @pytest.mark.parametrize("example_file", EXAMPLE_FILES, ids=lambda p: p.name)
    def test_has_build_round(self, example_file):
        """REQ-001 req 42: every example has build_round()."""
        module = _load_example(example_file.name)
        assert hasattr(module, "build_round"), f"{example_file.name} missing build_round()"
        assert callable(module.build_round)

    @pytest.mark.parametrize("example_file", EXAMPLE_FILES, ids=lambda p: p.name)
    def test_build_round_returns_round(self, example_file):
        """REQ-001 req 42: build_round() returns a Round."""
        module = _load_example(example_file.name)
        result = module.build_round()
        assert isinstance(result, Round), f"build_round() returned {type(result).__name__}, not Round"


# ──────────────────────────────────────────────────────────────────
#  REQ-001 req 43 — examples used as test fixtures
# ──────────────────────────────────────────────────────────────────

class TestExamplesAsFixtures:

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
        # -- Task model hints
        assert r.tasks[1].model == "haiku"
        assert r.tasks[2].model == "sonnet"

    def test_multi_task_accepts_parameters(self):
        """round_multi_task.py: build_round() accepts target_dir parameter."""
        module = _load_example("round_multi_task.py")
        r = module.build_round(target_dir="/tmp/test")
        assert r.name == "code-survey"
        # -- Instruction should reference the custom target_dir
        assert "/tmp/test" in r.tasks[1].instruction


# ──────────────────────────────────────────────────────────────────
#  REQ-001 req 32 — examples only import engine module
# ──────────────────────────────────────────────────────────────────

class TestExampleImports:

    @pytest.mark.parametrize("example_file", EXAMPLE_FILES, ids=lambda p: p.name)
    def test_only_imports_engine(self, example_file):
        """REQ-001 req 32: round files only import rondo.engine (+ stdlib)."""
        content = example_file.read_text()
        rondo_imports = [
            line.strip()
            for line in content.splitlines()
            if "from rondo" in line or "import rondo" in line
        ]
        for imp in rondo_imports:
            assert "rondo.engine" in imp, (
                f"{example_file.name} imports non-engine rondo module: {imp}"
            )


# ──────────────────────────────────────────────────────────────────
#  REQ-001 req 33 — examples under 50 lines
# ──────────────────────────────────────────────────────────────────

class TestExampleSize:

    @pytest.mark.parametrize("example_file", EXAMPLE_FILES, ids=lambda p: p.name)
    def test_under_50_lines(self, example_file):
        """REQ-001 req 33: round definition files under 50 lines."""
        lines = example_file.read_text().splitlines()
        assert len(lines) <= 50, f"{example_file.name} is {len(lines)} lines (max 50)"
