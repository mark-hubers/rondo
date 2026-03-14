# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Convention lock tests — enforce project patterns across all Rondo source.

Inspired by ACE2's convention lock system (33 test classes, 2,268 lines).
These tests glob source/test files and assert structural patterns. Every
new file is automatically checked — no manual registration needed.

Convention categories:
    Tier 1 — Universal Python (SPDX, encoding, docstrings)
    Tier 2 — Rondo-specific (spec refs, import layers, error handling)
"""

import ast
import re
from pathlib import Path

import pytest

# -- Rondo source and test roots
RONDO_ROOT = Path(__file__).parent.parent
SRC_DIR = RONDO_ROOT / "src" / "rondo"
TEST_DIR = RONDO_ROOT / "tests"

# -- All Python source files (excluding __pycache__)
SRC_FILES = sorted(SRC_DIR.glob("*.py"))
TEST_FILES = sorted(TEST_DIR.glob("test_*.py"))
ALL_PY_FILES = SRC_FILES + TEST_FILES


# ──────────────────────────────────────────────────────────────────
#  Tier 1 — Universal Python Conventions
# ──────────────────────────────────────────────────────────────────


class TestSpdxHeaders:
    """Every .py file MUST have SPDX copyright and license headers."""

    @pytest.mark.parametrize("filepath", ALL_PY_FILES, ids=lambda p: p.name)
    def test_spdx_copyright(self, filepath):
        """SPDX-FileCopyrightText header present."""
        content = filepath.read_text(encoding="utf-8")
        assert "SPDX-FileCopyrightText:" in content, f"{filepath.name} missing SPDX-FileCopyrightText header"

    @pytest.mark.parametrize("filepath", ALL_PY_FILES, ids=lambda p: p.name)
    def test_spdx_license(self, filepath):
        """SPDX-License-Identifier header present."""
        content = filepath.read_text(encoding="utf-8")
        assert "SPDX-License-Identifier: MIT" in content, f"{filepath.name} missing SPDX-License-Identifier: MIT"


class TestModuleDocstrings:
    """Every .py file MUST have a module-level docstring."""

    @pytest.mark.parametrize("filepath", ALL_PY_FILES, ids=lambda p: p.name)
    def test_has_docstring(self, filepath):
        """Module docstring exists."""
        tree = ast.parse(filepath.read_text(encoding="utf-8"))
        docstring = ast.get_docstring(tree)
        assert docstring is not None, f"{filepath.name} missing module docstring"


class TestNoBarePrints:
    """Source files (not tests) should use logging, not bare print().

    Exception: cli.py is allowed to print (it's the user interface).
    """

    EXEMPT = {"cli.py", "__main__.py"}

    @pytest.mark.parametrize(
        "filepath",
        [f for f in SRC_FILES if f.name not in {"cli.py", "__main__.py"}],
        ids=lambda p: p.name,
    )
    def test_no_bare_print(self, filepath):
        """No bare print() calls in library modules."""
        tree = ast.parse(filepath.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name) and func.id == "print":
                    pytest.fail(f"{filepath.name}:{node.lineno} — bare print() in library module (use logging)")


# ──────────────────────────────────────────────────────────────────
#  Tier 2 — Rondo-Specific Conventions
# ──────────────────────────────────────────────────────────────────


class TestSpecReferences:
    """Every source module MUST reference its governing spec(s) in the docstring.

    Pattern: REQ-NNN, STD-NNN, IFS-NNN, VER-NNN, or ADR-NNN.
    Exception: __init__.py and __main__.py (thin wrappers).
    """

    EXEMPT = {"__init__.py", "__main__.py"}
    SPEC_PATTERN = re.compile(r"(REQ|STD|IFS|VER|ADR|SOP|TST)-\d{3}")

    @pytest.mark.parametrize(
        "filepath",
        [f for f in SRC_FILES if f.name not in {"__init__.py", "__main__.py"}],
        ids=lambda p: p.name,
    )
    def test_has_spec_ref(self, filepath):
        """Module docstring references governing spec."""
        tree = ast.parse(filepath.read_text(encoding="utf-8"))
        docstring = ast.get_docstring(tree) or ""
        assert self.SPEC_PATTERN.search(docstring), (
            f"{filepath.name} docstring missing spec reference (e.g., REQ-001, STD-002)"
        )


class TestTestSpecReferences:
    """Every test module MUST reference VER-001 (verification matrix)."""

    @pytest.mark.parametrize("filepath", TEST_FILES, ids=lambda p: p.name)
    def test_has_ver_ref(self, filepath):
        """Test module references VER-001."""
        content = filepath.read_text(encoding="utf-8")
        if filepath.name == "test_conventions.py":
            return  # -- this file is about conventions, not spec verification
        assert "VER-001" in content, f"{filepath.name} missing VER-001 verification matrix reference"


class TestImportLayering:
    """Enforce strict import layering (no circular deps).

    L0: engine.py, config.py — import NOTHING from rondo
    L1: dispatch.py — imports engine + config only
    L2: runner.py, parallel.py — imports engine + config + dispatch
    L3: overnight.py — imports engine + config + runner
    Top: cli.py, report.py — can import anything
    """

    # -- What each module is ALLOWED to import from rondo
    ALLOWED_IMPORTS: dict[str, set[str]] = {
        "engine.py": set(),
        "config.py": set(),
        "dispatch.py": {"engine", "config"},
        "runner.py": {"engine", "config", "dispatch", "parallel"},
        "parallel.py": {"engine", "config", "dispatch"},
        "overnight.py": {"engine", "config", "runner"},
        "cli.py": {"engine", "config", "dispatch", "runner", "parallel", "overnight", "report"},
        "report.py": {"engine", "config", "overnight"},
        "__init__.py": {"engine", "config", "dispatch", "runner", "parallel", "overnight", "report"},
        "__main__.py": {"cli"},
    }

    @pytest.mark.parametrize("filepath", SRC_FILES, ids=lambda p: p.name)
    def test_import_layer(self, filepath):
        """Module only imports from allowed rondo modules."""
        allowed = self.ALLOWED_IMPORTS.get(filepath.name)
        if allowed is None:
            return  # -- unknown module, skip

        tree = ast.parse(filepath.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("rondo."):
                imported_module = node.module.split(".")[-1]
                assert imported_module in allowed, (
                    f"{filepath.name} imports rondo.{imported_module} — only allowed: {sorted(allowed) or '(none)'}"
                )


class TestWriteTextEncoding:
    """Every write_text() call MUST specify encoding='utf-8' (portability)."""

    @pytest.mark.parametrize("filepath", SRC_FILES, ids=lambda p: p.name)
    def test_write_text_has_encoding(self, filepath):
        """write_text() calls include encoding parameter."""
        tree = ast.parse(filepath.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            # -- Match *.write_text(...) calls
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "write_text":
                kwarg_names = {kw.arg for kw in node.keywords}
                assert "encoding" in kwarg_names, (
                    f"{filepath.name}:{node.lineno} — write_text() missing encoding='utf-8'"
                )


class TestCommentConvention:
    """Real comments use '# --' prefix per coding style.

    The convention:
        # -- explanation     = real comment (WHY)
        # ──────             = section divider
        #  Section Title     = section header (between dividers)
        # code_here()        = disabled code (no --)

    Bare '#' without '--' means disabled code. Section headers
    (indented text between ────── dividers) are structural, not comments.

    Threshold: 90%+ of non-exempt comments must use '# --'.

    Exemptions: shebangs, type: ignore, pylint, noqa, SPDX, section headers.
    """

    EXEMPT_PATTERNS = re.compile(
        r"^\s*#\s*("
        r"!|type:\s*ignore|pylint:|noqa|SPDX-|pragma:|coding:"
        r")"
    )

    # -- Section headers: '#  Title — context' between ────── dividers
    SECTION_HEADER = re.compile(r"^\s*#\s{2,}\S")

    @pytest.mark.parametrize("filepath", SRC_FILES, ids=lambda p: p.name)
    def test_comment_ratio(self, filepath):
        """90%+ of comments use '# --' convention."""
        lines = filepath.read_text(encoding="utf-8").splitlines()
        convention_comments = 0
        bare_comments = 0

        for line in lines:
            stripped = line.strip()
            if not stripped.startswith("#"):
                continue
            if self.EXEMPT_PATTERNS.match(stripped):
                continue
            # -- Section headers (e.g., '#  Prompt Building — REQ-001') are structural
            if self.SECTION_HEADER.match(stripped):
                continue
            if stripped.startswith("# --") or stripped.startswith("# ──"):
                convention_comments += 1
            elif stripped.startswith("#") and not stripped.startswith('"""'):
                bare_comments += 1

        total = convention_comments + bare_comments
        if total < 3:
            return  # -- too few comments to judge

        ratio = convention_comments / total
        assert ratio >= 0.9, (
            f"{filepath.name}: only {ratio:.0%} of comments use '# --' convention "
            f"({convention_comments}/{total}, {bare_comments} bare)"
        )


class TestErrorHandlingInCli:
    """CLI command functions MUST wrap load calls in try/except.

    Ensures users see clean error messages, not raw Python tracebacks.
    """

    def test_cmd_run_has_error_handling(self):
        """_cmd_run wraps load_round_file in try/except."""
        content = (SRC_DIR / "cli.py").read_text(encoding="utf-8")
        # -- Find the _cmd_run function and check for try/except
        in_cmd_run = False
        has_try = False
        for line in content.splitlines():
            if "def _cmd_run" in line:
                in_cmd_run = True
            elif in_cmd_run and line.strip().startswith("def "):
                break
            elif in_cmd_run and "try:" in line:
                has_try = True
                break
        assert has_try, "_cmd_run() must wrap load_round_file() in try/except"

    def test_cmd_overnight_has_error_handling(self):
        """_cmd_overnight wraps load_phases_file in try/except."""
        content = (SRC_DIR / "cli.py").read_text(encoding="utf-8")
        in_cmd = False
        has_try = False
        for line in content.splitlines():
            if "def _cmd_overnight" in line:
                in_cmd = True
            elif in_cmd and line.strip().startswith("def "):
                break
            elif in_cmd and "try:" in line:
                has_try = True
                break
        assert has_try, "_cmd_overnight() must wrap load_phases_file() in try/except"


class TestAceSignature:
    """Every .py file MUST have an ACE cryptographic signature.

    The signature is an HMAC-SHA256 watermark burned into the last line.
    Format: # -- sig: ace-{8 hex chars}
    Only Mark's system has the key to generate or verify these.
    """

    SIG_PATTERN = re.compile(r"^# -- sig: ace-[0-9a-f]{8}$")

    @pytest.mark.parametrize("filepath", ALL_PY_FILES, ids=lambda p: p.name)
    def test_has_signature(self, filepath):
        """File has ACE signature line."""
        lines = filepath.read_text(encoding="utf-8").rstrip().splitlines()
        assert lines, f"{filepath.name} is empty"
        assert self.SIG_PATTERN.match(lines[-1]), (
            f"{filepath.name} missing ACE signature (expected: # -- sig: ace-xxxxxxxx)"
        )

# -- sig: ace-c1b9fb85
