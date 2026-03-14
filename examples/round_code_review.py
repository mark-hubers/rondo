"""Rondo example: code review round.

Pattern: gate checks for uncommitted changes, then Claude reviews the diff.
Shows: pre-gate with subprocess, context_files, done_when criteria.
"""
import subprocess

from rondo.engine import Gate, Round, Task


def _has_staged_changes() -> tuple[bool, str]:
    """Pre-gate: verify there are staged changes to review."""
    result = subprocess.run(
        ["git", "diff", "--cached", "--stat"],
        capture_output=True, text=True,
    )
    lines = result.stdout.strip().splitlines()
    if lines:
        return (True, f"{len(lines)} file(s) staged")
    return (False, "No staged changes — stage files with git add first")


def build_round() -> Round:
    return Round(
        name="code-review",
        pre_gates=[
            Gate("Staged changes exist", check_fn=_has_staged_changes),
        ],
        tasks=[
            Task(
                name="Review diff",
                instruction=(
                    "Review the staged git diff. For each file:\n"
                    "1. Check for bugs, security issues, and logic errors\n"
                    "2. Note any style or naming concerns\n"
                    "3. Rate severity: critical / warning / nit\n"
                    "Output a structured review with file, line, severity, comment."
                ),
                done_when="Structured review with per-file findings and severity ratings",
                model="sonnet",
            ),
        ],
    )
