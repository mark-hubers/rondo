"""Rondo example: refactor safety audit with pre/post gates.

Pattern: gates verify preconditions before work and postconditions after.
Shows: blocking vs non-blocking gates, subprocess gates, multi-step workflow.
"""
import subprocess

from rondo.engine import Gate, Round, Task


def _git_clean() -> tuple[bool, str]:
    """Blocking gate: working tree must be clean before refactoring."""
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True, text=True,
    )
    if result.stdout.strip():
        lines = result.stdout.strip().splitlines()
        return (False, f"{len(lines)} uncommitted change(s) — commit or stash first")
    return (True, "Working tree clean")


def _on_branch() -> tuple[bool, str]:
    """Non-blocking gate: warn if on main branch."""
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True, text=True,
    )
    branch = result.stdout.strip()
    if branch in ("main", "master"):
        return (False, f"On {branch} — consider a feature branch")
    return (True, f"On branch: {branch}")


def _tests_still_pass() -> tuple[bool, str]:
    """Post-gate: verify tests pass after refactoring."""
    # -- Placeholder — real version would run pytest
    return (True, "Tests pass (placeholder)")


def build_round(target_file: str = "src/rondo/runner.py") -> Round:
    return Round(
        name="refactor-audit",
        pre_gates=[
            Gate("Clean working tree", check_fn=_git_clean, blocking=True),
            Gate("Not on main branch", check_fn=_on_branch, blocking=False),
        ],
        tasks=[
            Task(
                name="Identify refactor targets",
                instruction=(
                    f"Read {target_file} and identify:\n"
                    "1. Functions over 30 lines (candidates for extraction)\n"
                    "2. Repeated code patterns (candidates for DRY)\n"
                    "3. Complex conditionals (candidates for simplification)\n"
                    "For each, suggest a specific refactoring with before/after."
                ),
                context_files=[target_file],
                done_when="List of refactor targets with specific suggestions",
                model="sonnet",
            ),
            Task(
                name="Check naming consistency",
                instruction=(
                    f"Review all names in {target_file} (functions, variables, classes). "
                    "Flag any that don't follow Python conventions (PEP 8). "
                    "Suggest renames where needed."
                ),
                context_files=[target_file],
                done_when="Naming audit with suggested renames",
                model="haiku",
            ),
        ],
        post_gates=[
            Gate("Tests pass after review", check_fn=_tests_still_pass),
        ],
    )
