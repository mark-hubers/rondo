# rondo-meta: mode=subprocess provider=anthropic category=pipeline value="Auto-discover untested modules and generate test stubs"

"""Rondo example: auto-discover source files, generate missing tests.

Pattern: auto_fn scans the filesystem, Claude writes tests for uncovered modules.
Shows: auto tasks for discovery, parameterized build_round(), model hints.
"""

from pathlib import Path

from rondo.engine import Gate, Round, Task


def build_round(src_dir: str = ".", test_dir: str = "tests/") -> Round:
    src = Path(src_dir)
    tests = Path(test_dir)

    def _find_untested() -> tuple[bool, str]:
        """Auto task: find .py files without corresponding test files."""
        source_files = sorted(src.rglob("*.py"))
        test_files = {f.name for f in tests.rglob("test_*.py")}
        missing = []
        for sf in source_files:
            if sf.name.startswith("_"):
                continue
            expected_test = f"test_{sf.name}"
            if expected_test not in test_files:
                missing.append(str(sf))
        if missing:
            return (True, f"Untested: {', '.join(missing)}")
        return (True, "All modules have test files")

    def _src_exists() -> tuple[bool, str]:
        if src.is_dir():
            count = len(list(src.rglob("*.py")))
            return (True, f"{src_dir} exists ({count} .py files)")
        return (False, f"{src_dir} not found")

    return Round(
        name="test-generator",
        pre_gates=[
            Gate("Source directory exists", check_fn=_src_exists),
        ],
        tasks=[
            Task(
                name="Find untested modules",
                description="Scan for source files missing test coverage",
                auto_fn=_find_untested,
            ),
            Task(
                name="Generate test stubs",
                instruction=(
                    f"Look at the source files in {src_dir} that don't have "
                    f"corresponding test files in {test_dir}. For each one, "
                    "write a pytest test file with:\n"
                    "- Test class named Test<ModuleName>\n"
                    "- One test per public function\n"
                    "- Descriptive test names\n"
                    "- TODO comments where assertions need real values"
                ),
                context_files=[src_dir],
                done_when="Test stub files created for all untested modules",
                model="sonnet",
            ),
        ],
    )
