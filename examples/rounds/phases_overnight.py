# rondo-meta: mode=subprocess provider=anthropic category=pipeline value="Multi-phase overnight plan with model-tier escalation"

"""Rondo example: overnight multi-phase build.

Pattern: build_phases() returns a list of Rounds for the overnight scheduler.
Shows: sequential phases, mixed auto/interactive, escalating model tiers.

Usage:
    rondo overnight examples/rounds/phases_overnight.py --mode standard
"""

from pathlib import Path

from rondo.engine import Gate, Round, Task


def _tests_pass() -> tuple[bool, str]:
    """Gate: check if test suite passes (placeholder — real version runs pytest)."""
    # -- In production, this would run: subprocess.run(["pytest", "--tb=short"])
    return (True, "Tests pass (placeholder)")


def build_phases(target_dir: str = ".") -> list[Round]:
    """Build overnight phases — ordered from fast/cheap to slow/expensive."""
    return [
        # -- Phase 1: fast checks (auto tasks, no Claude needed)
        Round(
            name="phase-1-checks",
            tasks=[
                Task(
                    name="Count source files",
                    auto_fn=lambda: (True, f"{len(list(Path(target_dir).rglob('*.py')))} Python files"),
                ),
                Task(
                    name="Check for TODOs",
                    auto_fn=lambda: (
                        True,
                        f"{sum(1 for f in Path(target_dir).rglob('*.py') for line in open(f) if 'TODO' in line)} TODOs found",
                    ),
                ),
            ],
        ),
        # -- Phase 2: lightweight AI review (haiku — fast, cheap)
        Round(
            name="phase-2-lint-review",
            pre_gates=[
                Gate("Tests pass before review", check_fn=_tests_pass),
            ],
            tasks=[
                Task(
                    name="Style review",
                    instruction=(
                        f"Scan all .py files in {target_dir} for:\n"
                        "- Inconsistent naming (snake_case vs camelCase)\n"
                        "- Missing type hints on public functions\n"
                        "- Functions over 50 lines\n"
                        "Output a table: file, line, issue"
                    ),
                    context_files=[target_dir],
                    done_when="Table of style issues found",
                    model="haiku",
                ),
            ],
        ),
        # -- Phase 3: deep analysis (sonnet — thorough)
        Round(
            name="phase-3-deep-review",
            tasks=[
                Task(
                    name="Architecture review",
                    instruction=(
                        f"Analyze the module structure in {target_dir}:\n"
                        "1. Draw the import graph (which modules import which)\n"
                        "2. Identify circular dependencies\n"
                        "3. Check layer violations (higher layers importing lower)\n"
                        "4. Suggest refactoring if needed"
                    ),
                    context_files=[target_dir],
                    done_when="Import graph + dependency analysis + recommendations",
                    model="sonnet",
                ),
            ],
        ),
    ]
