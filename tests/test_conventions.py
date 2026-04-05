# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Convention lock tests — enforce project patterns across all Rondo source.

VER-001 verification matrix: structural conventions.
Inspired by ACE2's convention lock system (33 test classes, 2,268 lines).
These tests glob source/test files and assert structural patterns. Every
new file is automatically checked — no manual registration needed.

Each test = one convention rule. No parametrize inflation.

Convention categories:
    Tier 1 — Universal Python (SPDX, encoding, docstrings)
    Tier 2 — Rondo-specific (spec refs, import layers, error handling)
    Tier 3 — Code quality (complexity, annotations, hygiene)
"""

import ast
import re
from pathlib import Path

# -- Rondo source and test roots
RONDO_ROOT = Path(__file__).parent.parent
SRC_DIR = RONDO_ROOT / "src" / "rondo"
TEST_DIR = RONDO_ROOT / "tests"

# -- All Python source files (excluding __pycache__, including cli_commands/ package)
SRC_FILES = sorted(SRC_DIR.glob("*.py")) + sorted(SRC_DIR.glob("cli_commands/*.py"))
TEST_FILES = sorted(TEST_DIR.glob("test_*.py"))
ALL_PY_FILES = SRC_FILES + TEST_FILES


# ──────────────────────────────────────────────────────────────────
#  Tier 1 — Universal Python Conventions
# ──────────────────────────────────────────────────────────────────


class TestSpdxHeaders:
    """Every .py file MUST have SPDX copyright and license headers."""

    def test_spdx_copyright(self):
        """SPDX-FileCopyrightText header present on all files."""
        missing = []
        for filepath in ALL_PY_FILES:
            content = filepath.read_text(encoding="utf-8")
            if "SPDX-FileCopyrightText:" not in content:
                missing.append(filepath.name)
        assert not missing, f"Missing SPDX-FileCopyrightText: {missing}"

    def test_spdx_license(self):
        """SPDX-License-Identifier header present on all files."""
        missing = []
        for filepath in ALL_PY_FILES:
            content = filepath.read_text(encoding="utf-8")
            if "SPDX-License-Identifier: MIT" not in content:
                missing.append(filepath.name)
        assert not missing, f"Missing SPDX-License-Identifier: MIT: {missing}"


class TestModuleDocstrings:
    """Every .py file MUST have a module-level docstring."""

    def test_all_modules_have_docstrings(self):
        """Module docstring exists on all files."""
        missing = []
        for filepath in ALL_PY_FILES:
            tree = ast.parse(filepath.read_text(encoding="utf-8"))
            if ast.get_docstring(tree) is None:
                missing.append(filepath.name)
        assert not missing, f"Missing module docstring: {missing}"


class TestNoBarePrints:
    """Source files (not tests) should use logging, not bare print().

    Exception: cli.py is allowed to print (it's the user interface).
    """

    EXEMPT = {
        "cli.py",
        "mcp_dispatch.py",
        "mcp_compose.py",
        "live.py",
        "__main__.py",
        "notify.py",
        "dispatch.py",
        "observe.py",
        "infra.py",
        "review.py",
        "__init__.py",
    }

    def test_no_bare_print_in_library(self):
        """No bare print() calls in library modules."""
        violations = []
        for filepath in SRC_FILES:
            if filepath.name in self.EXEMPT:
                continue
            tree = ast.parse(filepath.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    func = node.func
                    if isinstance(func, ast.Name) and func.id == "print":
                        violations.append(f"{filepath.name}:{node.lineno}")
        assert not violations, f"Bare print() in library modules: {violations}"


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

    def test_source_modules_reference_specs(self):
        """Module docstrings reference governing specs."""
        missing = []
        for filepath in SRC_FILES:
            if filepath.name in self.EXEMPT:
                continue
            tree = ast.parse(filepath.read_text(encoding="utf-8"))
            docstring = ast.get_docstring(tree) or ""
            if not self.SPEC_PATTERN.search(docstring):
                missing.append(filepath.name)
        assert not missing, f"Missing spec reference in docstring: {missing}"


class TestTestSpecReferences:
    """Every test module MUST reference VER-001 (verification matrix)."""

    EXEMPT = {"test_conventions.py"}

    def test_test_modules_reference_ver001(self):
        """Test modules reference VER-001."""
        missing = []
        for filepath in TEST_FILES:
            if filepath.name in self.EXEMPT:
                continue
            content = filepath.read_text(encoding="utf-8")
            if "VER-001" not in content:
                missing.append(filepath.name)
        assert not missing, f"Missing VER-001 reference: {missing}"


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
        "sanitize.py": set(),
        "audit.py": {"sanitize"},
        "flaky.py": set(),
        "spool.py": set(),
        "_version.py": set(),
        "metrics.py": set(),
        "mcp_server.py": {
            "mcp_dispatch",
            "mcp_tools",
            "providers",
            "ai_help",
            "_version",
        },
        "mcp_compose.py": {
            "mcp_dispatch",
            "config",
            "providers",
        },
        "mcp_dispatch.py": {
            "metrics",
            "_version",
            "cli",
            "config",
            "dispatch",
            "runner",
            "ai_help",
            "engine",
            "spool",
            "notify",
            "history",
            "providers",
            "audit",
            "schedule",
            "mcp_tools",
            "mcp_compose",
        },
        "mcp_tools.py": {
            "metrics",
            "_version",
            "cli",
            "config",
            "engine",
            "spool",
            "history",
            "providers",
            "schedule",
            "mcp_server",
            "health",
        },  # mcp_server: lazy import in rondo_cloud() only; health: lazy import in rondo_health() only
        "dispatch.py": {
            "engine",
            "config",
            "history",
            "dispatch_prompt",
            "dispatch_parse",
            "sanitize",
            "audit",
            "spool",
            "metrics",
        },
        "runner.py": {"engine", "config", "dispatch", "parallel", "notify"},
        "parallel.py": {"engine", "config", "dispatch"},
        "overnight.py": {"engine", "config", "runner", "preflight", "spool"},
        "live.py": {"engine"},
        "cli.py": {
            "engine",
            "config",
            "dispatch",
            "runner",
            "parallel",
            "overnight",
            "report",
            "live",
            "preflight",
            "history",
            "ai_help",
            "audit",
            "flaky",
            "sanitize",
            "spool",
            "_version",
            "metrics",
            "mcp_server",
            "providers",
            "schedule",
            "health",
            "cli_commands",
        },
        "cli_commands/__init__.py": {
            "cli_commands",
            "dispatch",
            "observe",
            "infra",
            "review",
        },  # package __init__ imports from submodules
        "cli_commands/dispatch.py": {
            "cli_commands",
            "cli",
            "config",
            "live",
            "overnight",
            "report",
            "preflight",
        },
        "cli_commands/observe.py": {
            "cli_commands",
            "history",
            "audit",
            "flaky",
            "metrics",
        },
        "cli_commands/infra.py": {
            "cli_commands",
            "preflight",
            "spool",
            "mcp_server",
            "schedule",
            "adapters",
            "health",
        },
        "cli_commands/review.py": {
            "cli_commands",
            "mcp_server",
            "providers",
            "config",
        },
        "report.py": {"engine", "config", "overnight"},
        "__init__.py": {"engine", "config", "dispatch", "runner", "parallel", "overnight", "report", "live"},
        "__main__.py": {"cli"},
    }

    def test_import_layers_enforced(self):
        """Modules only import from allowed rondo modules."""
        violations = []
        for filepath in SRC_FILES:
            # -- Use relative path from SRC_DIR for cli_commands/ package files
            try:
                rel = str(filepath.relative_to(SRC_DIR))
            except ValueError:
                rel = filepath.name
            allowed = self.ALLOWED_IMPORTS.get(rel)
            if allowed is None:
                continue
            tree = ast.parse(filepath.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("rondo."):
                    imported_module = node.module.split(".")[-1]
                    if imported_module not in allowed:
                        violations.append(
                            f"{rel} imports rondo.{imported_module} (allowed: {sorted(allowed) or '(none)'})"
                        )
        assert not violations, "Import layer violations:\n  " + "\n  ".join(violations)


class TestWriteTextEncoding:
    """Every write_text() call MUST specify encoding='utf-8' (portability)."""

    def test_write_text_has_encoding(self):
        """write_text() calls include encoding parameter."""
        violations = []
        for filepath in SRC_FILES:
            tree = ast.parse(filepath.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr == "write_text":
                    kwarg_names = {kw.arg for kw in node.keywords}
                    if "encoding" not in kwarg_names:
                        violations.append(f"{filepath.name}:{node.lineno}")
        assert not violations, f"write_text() missing encoding='utf-8': {violations}"


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

    def test_comment_convention_ratio(self):
        """90%+ of comments use '# --' convention across all source files."""
        violations = []
        for filepath in SRC_FILES:
            lines = filepath.read_text(encoding="utf-8").splitlines()
            convention_comments = 0
            bare_comments = 0

            for line in lines:
                stripped = line.strip()
                if not stripped.startswith("#"):
                    continue
                if self.EXEMPT_PATTERNS.match(stripped):
                    continue
                if self.SECTION_HEADER.match(stripped):
                    continue
                if stripped.startswith("# --") or stripped.startswith("# ──"):
                    convention_comments += 1
                elif stripped.startswith("#") and not stripped.startswith('"""'):
                    bare_comments += 1

            total = convention_comments + bare_comments
            if total < 3:
                continue
            ratio = convention_comments / total
            if ratio < 0.9:
                violations.append(f"{filepath.name}: {ratio:.0%} ({convention_comments}/{total}, {bare_comments} bare)")
        assert not violations, "Comment convention < 90%:\n  " + "\n  ".join(violations)


class TestErrorHandlingInCli:
    """CLI command functions MUST wrap load calls in try/except.

    Ensures users see clean error messages, not raw Python tracebacks.
    """

    def test_cmd_run_has_error_handling(self):
        """_cmd_run wraps load_round_file in try/except."""
        content = (SRC_DIR / "cli_commands" / "dispatch.py").read_text(encoding="utf-8")
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
        content = (SRC_DIR / "cli_commands" / "dispatch.py").read_text(encoding="utf-8")
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


# ──────────────────────────────────────────────────────────────────
#  Tier 3 — Code Quality Conventions
# ──────────────────────────────────────────────────────────────────


class TestPublicFunctionDocstrings:
    """Every public function/method in source modules MUST have a docstring.

    DoD-STD-2167A / NASA-STD-8739.8: all public interfaces documented.
    Private functions (leading underscore) are exempt.
    """

    def test_public_functions_have_docstrings(self):
        """Public functions have docstrings."""
        missing = []
        for filepath in SRC_FILES:
            tree = ast.parse(filepath.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if node.name.startswith("_"):
                        continue
                    if ast.get_docstring(node) is None:
                        missing.append(f"{filepath.name}:{node.lineno} {node.name}()")
        assert not missing, "Public functions without docstrings:\n  " + "\n  ".join(missing)


class TestPublicFunctionTypeAnnotations:
    """Every public function MUST have return type annotation.

    Type annotations enable mypy to catch bugs at development time.
    Private functions are exempt. Test files are exempt.
    """

    def test_public_functions_have_return_type(self):
        """Public functions have return type annotation."""
        missing = []
        for filepath in SRC_FILES:
            tree = ast.parse(filepath.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if node.name.startswith("_"):
                        continue
                    if node.returns is None:
                        missing.append(f"{filepath.name}:{node.lineno} {node.name}()")
        assert not missing, "Public functions without return type:\n  " + "\n  ".join(missing)


class TestNoTodoFixmeHack:
    """Source code MUST NOT contain TODO, FIXME, or HACK comments.

    These indicate incomplete work shipped to production. In a DoD codebase,
    every known issue is tracked in a defect tracker — never left as a
    comment that gets ignored.
    """

    # -- Build pattern from parts to avoid self-detection
    _MARKER_WORDS = "|".join(["TO" + "DO", "FIX" + "ME", "HA" + "CK", "X" + "XX"])
    MARKERS = re.compile(rf"#.*\b({_MARKER_WORDS})\b", re.IGNORECASE)

    def test_no_todo_markers(self):
        """No TODO/FIXME/HACK/XXX markers in any code."""
        violations = []
        for filepath in ALL_PY_FILES:
            lines = filepath.read_text(encoding="utf-8").splitlines()
            for i, line in enumerate(lines, 1):
                if self.MARKERS.search(line):
                    violations.append(f"{filepath.name}:{i} {line.strip()}")
        assert not violations, "Found incomplete-work markers:\n  " + "\n  ".join(violations)


class TestNoWildcardImports:
    """Source code MUST NOT use 'from X import *' (wildcard imports).

    Wildcard imports pollute the namespace, hide dependencies, and make
    it impossible to determine where a name comes from without running code.
    """

    def test_no_wildcard_imports(self):
        """No wildcard imports in any file."""
        violations = []
        for filepath in ALL_PY_FILES:
            tree = ast.parse(filepath.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    for alias in node.names:
                        if alias.name == "*":
                            violations.append(f"{filepath.name}:{node.lineno} from {node.module}")
        assert not violations, f"Wildcard imports: {violations}"


class TestNoMutableDefaultArgs:
    """Function defaults MUST NOT be mutable (list, dict, set).

    Python's mutable default argument trap is a common source of bugs —
    the default is shared across all calls. Use None + factory pattern instead.
    """

    MUTABLE_TYPES = (ast.List, ast.Dict, ast.Set)

    def test_no_mutable_defaults(self):
        """No mutable default arguments in any source function."""
        violations = []
        for filepath in SRC_FILES:
            tree = ast.parse(filepath.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    for default in node.args.defaults + node.args.kw_defaults:
                        if isinstance(default, self.MUTABLE_TYPES):
                            violations.append(f"{filepath.name}:{node.lineno} {node.name}()")
        assert not violations, "Mutable default arguments:\n  " + "\n  ".join(violations)


class TestCyclomaticComplexity:
    """No function should exceed cyclomatic complexity of 15.

    High complexity = hard to test, hard to review, likely to have bugs.
    DoD-STD-2167A mandates complexity tracking. NASA limits to 10-15.

    We use AST branch counting: if/elif/else, for, while, except, with,
    boolean operators (and/or), assert, ternary expressions.
    """

    MAX_COMPLEXITY = 15

    def test_function_complexity(self):
        """All source functions have cyclomatic complexity <= 15."""
        violations = []
        for filepath in SRC_FILES:
            tree = ast.parse(filepath.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    complexity = self._calculate_complexity(node)
                    if complexity > self.MAX_COMPLEXITY:
                        violations.append(
                            f"{filepath.name}:{node.lineno} {node.name}() "
                            f"complexity={complexity} (max {self.MAX_COMPLEXITY})"
                        )
        assert not violations, "Functions exceeding complexity limit:\n  " + "\n  ".join(violations)

    @staticmethod
    def _calculate_complexity(func_node: ast.FunctionDef) -> int:
        """Calculate McCabe cyclomatic complexity for a function.

        Complexity = 1 + (number of decision points).
        """
        complexity = 1
        for node in ast.walk(func_node):
            if isinstance(node, (ast.If, ast.While, ast.For, ast.ExceptHandler)):
                complexity += 1
            elif isinstance(node, ast.BoolOp):
                # -- Each 'and'/'or' adds a path
                complexity += len(node.values) - 1
            elif isinstance(node, ast.IfExp):
                # -- Ternary expression: x if cond else y
                complexity += 1
            elif isinstance(node, (ast.Assert, ast.With)):
                complexity += 1
        return complexity


class TestMgHSignature:
    """Every .py file MUST have a 5-segment MgH cryptographic signature.

    Format: # -- sig: mgh-{mark 4hex}.{g 2hex}.{hubers 6hex}.{file 4hex}.{hmac 6hex}

    Segments 1-3: SHA-256 of author name parts (fixed, publicly crackable).
    Segment 4:    SHA-256 of filename (varies per file, crackable).
    Segment 5:    HMAC-SHA256 with secret key (varies, NOT crackable).
    """

    SIG_PATTERN = re.compile(r"^# -- sig: mgh-[0-9a-f]{4}\.[0-9a-f]{2}\.[0-9a-f]{6}\.[0-9a-f]{4}\.[0-9a-f]{6}$")

    def test_all_files_have_signature(self):
        """All files have mgh 5-segment signature line."""
        missing = []
        for filepath in ALL_PY_FILES:
            lines = filepath.read_text(encoding="utf-8").rstrip().splitlines()
            if not lines or not self.SIG_PATTERN.match(lines[-1]):
                missing.append(filepath.name)
        assert not missing, f"Missing mgh signature: {missing}"


# -- ──────────────────────────────────────────────────────────────
# --  Doc/spec sync — catch count drift automatically
# -- ──────────────────────────────────────────────────────────────


class TestDocSpecSync:
    """Verify RONDO-REFERENCE.md counts match actual code."""

    def test_mcp_tool_count_matches(self) -> None:
        """Reference doc tool count matches @mcp.tool() registrations."""
        import re

        server_path = SRC_DIR / "mcp_server.py"
        tool_count = len(re.findall(r"@mcp\.tool\(", server_path.read_text(encoding="utf-8")))
        ref_path = SRC_DIR.parent.parent / "docs" / "RONDO-REFERENCE.md"
        if not ref_path.exists():
            pytest.skip("RONDO-REFERENCE.md not found")
        ref_text = ref_path.read_text(encoding="utf-8")
        # -- Find "MCP Tools (N)" in reference
        match = re.search(r"MCP Tools \((\d+)\)", ref_text)
        if not match:
            pytest.skip("MCP tool count not found in reference")
        doc_count = int(match.group(1))
        assert tool_count == doc_count, f"MCP tool count drift: code has {tool_count}, doc says {doc_count}"

    def test_cli_command_count_matches(self) -> None:
        """Reference doc CLI count matches add_parser() calls."""
        import re

        cli_path = SRC_DIR / "cli.py"
        parser_count = len(re.findall(r"add_parser\(", cli_path.read_text(encoding="utf-8")))
        ref_path = SRC_DIR.parent.parent / "docs" / "RONDO-REFERENCE.md"
        if not ref_path.exists():
            pytest.skip("RONDO-REFERENCE.md not found")
        ref_text = ref_path.read_text(encoding="utf-8")
        match = re.search(r"CLI Commands \((\d+)\)", ref_text)
        if not match:
            pytest.skip("CLI command count not found in reference")
        doc_count = int(match.group(1))
        assert parser_count == doc_count, f"CLI command count drift: code has {parser_count}, doc says {doc_count}"

    def test_ai_help_tool_count_matches(self) -> None:
        """ai_help_data.json mcp_tools count matches @mcp.tool() registrations."""
        import json
        import re

        server_path = SRC_DIR / "mcp_server.py"
        tool_count = len(re.findall(r"@mcp\.tool\(", server_path.read_text(encoding="utf-8")))
        data_path = SRC_DIR / "data" / "ai_help_data.json"
        if not data_path.exists():
            pytest.skip("ai_help_data.json not found")
        data = json.loads(data_path.read_text(encoding="utf-8"))
        ai_help_count = len(data.get("mcp_tools", []))
        assert tool_count == ai_help_count, f"ai_help tool count drift: code has {tool_count}, data has {ai_help_count}"


# -- ──────────────────────────────────────────────────────────────
# --  Architecture: adapter contract enforcement (FIX-679)
# -- ──────────────────────────────────────────────────────────────


class TestAdapterContract:
    """All provider adapters MUST inherit from ProviderAdapter ABC.

    FIX-679: formalize adapter architecture. Convention test ensures
    any new adapter file follows the contract (dispatch, health, models).
    """

    def test_all_adapters_inherit_from_base(self) -> None:
        """Every *Adapter class in adapters/ inherits from ProviderAdapter."""
        import importlib

        from rondo.providers import ProviderAdapter

        adapter_modules = [
            "rondo.adapters.ollama",
            "rondo.adapters.chat_completions",
            "rondo.adapters.gemini",
            "rondo.adapters.anthropic_api",
        ]
        for mod_name in adapter_modules:
            mod = importlib.import_module(mod_name)
            for attr_name in dir(mod):
                obj = getattr(mod, attr_name)
                if isinstance(obj, type) and attr_name.endswith("Adapter") and attr_name != "ProviderAdapter":
                    assert issubclass(obj, ProviderAdapter), (
                        f"{mod_name}.{attr_name} does not inherit from ProviderAdapter"
                    )

    def test_adapter_contract_methods(self) -> None:
        """ProviderAdapter ABC requires dispatch, health, models."""
        from rondo.providers import ProviderAdapter

        abstract_methods = {
            m for m in dir(ProviderAdapter) if getattr(getattr(ProviderAdapter, m, None), "__isabstractmethod__", False)
        }
        assert "dispatch" in abstract_methods
        assert "health" in abstract_methods
        assert "models" in abstract_methods


# -- ──────────────────────────────────────────────────────────────
# --  Security: no hardcoded API keys in source (FIX-675)
# -- ──────────────────────────────────────────────────────────────


class TestNoHardcodedKeys:
    """Source files MUST NOT contain hardcoded API keys or secrets."""

    KEY_PATTERN = re.compile(
        r"""(?:GEMINI_API_KEY|XAI_API_KEY|MISTRAL_API_KEY|OPENAI_API_KEY|ANTHROPIC_API_KEY"""
        r"""|api_key)\s*=\s*['"][A-Za-z0-9_\-]{20,}['"]""",
        re.IGNORECASE,
    )
    EXEMPT = {"test_sanitize.py", "test_conventions.py", "test_audit.py", "test_dispatch.py", "test_integration_e2e.py"}

    def test_no_hardcoded_keys_in_source(self) -> None:
        """No API keys hardcoded in Python source files."""
        violations = []
        for filepath in ALL_PY_FILES:
            if filepath.name in self.EXEMPT:
                continue
            content = filepath.read_text(encoding="utf-8")
            for match in self.KEY_PATTERN.finditer(content):
                violations.append(f"{filepath.name}:{match.start()}: {match.group()[:40]}...")
        assert not violations, f"Hardcoded API keys found:\n  " + "\n  ".join(violations)


class TestNoShellTrue:
    """subprocess calls MUST NOT use shell=True (command injection prevention).

    FIX-681: security convention enforcement.
    """

    SHELL_PATTERN = re.compile(r"shell\s*=\s*True")

    def test_no_shell_true_in_source(self) -> None:
        """No shell=True in any source file (STD-110 S1)."""
        violations = []
        for filepath in SRC_FILES:
            content = filepath.read_text(encoding="utf-8")
            for i, line in enumerate(content.splitlines(), 1):
                if (
                    self.SHELL_PATTERN.search(line)
                    and "never" not in line.lower()
                    and "#" not in line.split("shell")[0]
                ):
                    violations.append(f"{filepath.name}:{i}")
        assert not violations, f"shell=True found in source files: {violations}"


class TestSanitizeScrubsKeys:
    """sanitize.py MUST scrub API keys from stored outputs.

    FIX-681: verify the sanitizer catches key patterns.
    """

    def test_api_key_scrubbed(self) -> None:
        """API key patterns are removed by sanitize_text."""
        from rondo.sanitize import sanitize_text

        text = 'Error: api_key = "sk-abc123def456ghi789jkl012" failed'
        result = sanitize_text(text)
        assert "sk-abc123" not in result.sanitized_text

    def test_bearer_token_scrubbed(self) -> None:
        """Bearer tokens are removed by sanitize_text."""
        from rondo.sanitize import sanitize_text

        text = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test"
        result = sanitize_text(text)
        assert "eyJhbGci" not in result.sanitized_text


# -- ──────────────────────────────────────────────────────────────
# --  Import cycle detection (Cursor "would worry me" item)
# -- ──────────────────────────────────────────────────────────────


class TestNoCircularImports:
    """Verify no circular imports exist between rondo modules."""

    def test_all_modules_import_cleanly(self) -> None:
        """Import every rondo module — fails if circular import exists."""
        import importlib

        modules = [
            "rondo.engine",
            "rondo.config",
            "rondo.providers",
            "rondo.dispatch",
            "rondo.runner",
            "rondo.parallel",
            "rondo.audit",
            "rondo.sanitize",
            "rondo.spool",
            "rondo.history",
            "rondo.metrics",
            "rondo.flaky",
            "rondo.preflight",
            "rondo.report",
            "rondo.overnight",
            "rondo.live",
            "rondo.notify",
            "rondo.ai_help",
            "rondo.adapters.factory",
            "rondo.adapters.auth",
            "rondo.adapters.health",
            "rondo.mcp_tools",
            "rondo.mcp_compose",
            "rondo.mcp_dispatch",
            "rondo.cli_commands",
            "rondo.cli",
        ]
        failures = []
        for mod in modules:
            try:
                importlib.import_module(mod)
            except ImportError as exc:
                failures.append(f"{mod}: {exc}")
        assert not failures, "Circular or broken imports:\n  " + "\n  ".join(failures)


# -- ──────────────────────────────────────────────────────────────
# --  STD-107 Security conventions (RONDO-56)
# -- ──────────────────────────────────────────────────────────────


class TestNoSQLite:
    """STD-107 req 005: Rondo is stateless — no sqlite3 imports."""

    def test_no_sqlite3_in_source(self):
        import re

        for src_file in SRC_FILES:
            content = src_file.read_text(encoding="utf-8")
            matches = re.findall(r"^\s*import sqlite3|^\s*from sqlite3", content, re.MULTILINE)
            assert not matches, f"{src_file.name} imports sqlite3 — Rondo is stateless (STD-107 req 005)"


class TestNoHardcodedSecrets:
    """STD-107 req 001: no API keys or secrets in source."""

    def test_no_api_keys_in_source(self):
        import re

        api_key_pattern = re.compile(r"sk-[a-zA-Z0-9]{20,}|ANTHROPIC_API_KEY\s*=\s*['\"]")
        for src_file in SRC_FILES:
            content = src_file.read_text(encoding="utf-8")
            matches = api_key_pattern.findall(content)
            assert not matches, f"{src_file.name} has hardcoded secrets: {matches[:2]}"


class TestNoHttpUrls:
    """STD-107 req 003: no plain HTTP for external APIs."""

    def test_no_plain_http_api_calls(self):
        import re

        for src_file in SRC_FILES:
            content = src_file.read_text(encoding="utf-8")
            ## -- Find http:// but allow localhost + Apple DTD (plist standard)
            matches = re.findall(r"http://(?!localhost|127\.0\.0\.1|0\.0\.0\.0|www\.apple\.com/DTDs)\S+", content)
            assert not matches, f"{src_file.name} uses plain HTTP: {matches[:2]}"


# -- sig: mgh-6201.cd.bd955f.6280.8f7324
