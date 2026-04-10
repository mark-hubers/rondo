#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Mark G. Hubers / HubersTech
# SPDX-License-Identifier: LicenseRef-Proprietary
"""Build Check Round — ace-build gates as Rondo tasks.

Converts the 6 ace-build gates into a Rondo round with AUTO tasks
that run the actual tools + INTERACTIVE tasks for analysis.

Created: 2026-03-13 (Session 75)
Author: Mark Hubers — HubersTech
"""

import subprocess
from pathlib import Path

from rondo.engine import Gate, Round, Task

_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent.parent)


## -- Auto task functions for build gates
def _run_ruff_format(**_kwargs: object) -> tuple[bool, str]:
    """Run ruff format check."""
    result = subprocess.run(
        [".venv/bin/ruff", "format", "--check", "."],
        capture_output=True,
        text=True,
        cwd=_PROJECT_ROOT,
    )
    if result.returncode == 0:
        return True, "All files formatted correctly"
    return False, f"Format issues: {result.stdout[:200]}"


def _run_ruff_lint(**_kwargs: object) -> tuple[bool, str]:
    """Run ruff lint."""
    result = subprocess.run(
        [".venv/bin/ruff", "check", "."],
        capture_output=True,
        text=True,
        cwd=_PROJECT_ROOT,
    )
    if result.returncode == 0:
        return True, "No lint issues"
    lines = result.stdout.strip().split("\n")
    return False, f"{len(lines)} lint issues. First: {lines[0] if lines else 'unknown'}"


def _run_bandit(**_kwargs: object) -> tuple[bool, str]:
    """Run bandit security scan."""
    result = subprocess.run(
        [".venv/bin/bandit", "-c", "pyproject.toml", "-r", "src/ace2", "ob", "rondo", "-q"],
        capture_output=True,
        text=True,
        cwd=_PROJECT_ROOT,
    )
    if result.returncode == 0:
        return True, "No security issues"
    return False, f"Security issues found: {result.stdout[:200]}"


def _run_mypy(**_kwargs: object) -> tuple[bool, str]:
    """Run mypy type check."""
    result = subprocess.run(
        [".venv/bin/mypy", "--config-file", "pyproject.toml", "src/ace2"],
        capture_output=True,
        text=True,
        cwd=_PROJECT_ROOT,
    )
    if result.returncode == 0:
        return True, "Type check passed"
    lines = result.stdout.strip().split("\n")
    return False, f"Type errors: {lines[-1] if lines else 'unknown'}"


def _run_pytest(**_kwargs: object) -> tuple[bool, str]:
    """Run test suite."""
    result = subprocess.run(
        [".venv/bin/pytest", "--tb=short", "-q"],
        capture_output=True,
        text=True,
        cwd=_PROJECT_ROOT,
        timeout=300,
    )
    ## -- Extract summary line
    lines = result.stdout.strip().split("\n")
    summary = lines[-1] if lines else "no output"
    if result.returncode == 0:
        return True, f"Tests passed: {summary}"
    return False, f"Tests failed: {summary}"


def build_check_round() -> Round:
    """Build a round that runs ace-build's 6 gates + analysis tasks."""
    return Round(
        name="build-check",
        round_num=0,
        description="Full build verification (6 gates + analysis)",
        pre_gates=[
            Gate(
                name="Venv exists",
                description=".venv must exist",
                check_fn=lambda **_kw: (
                    Path(_PROJECT_ROOT, ".venv").exists(),
                    "Found .venv" if Path(_PROJECT_ROOT, ".venv").exists() else "MISSING .venv",
                ),
                blocking=True,
            ),
        ],
        tasks=[
            ## -- Gate 1: Format (AUTO)
            Task(
                name="Gate 1: Ruff Format",
                description="Code formatting check",
                auto_fn=_run_ruff_format,
            ),
            ## -- Gate 2: Lint (AUTO)
            Task(
                name="Gate 2: Ruff Lint",
                description="Lint check (E, F, W, I, N, UP, D)",
                auto_fn=_run_ruff_lint,
            ),
            ## -- Gate 3: Security (AUTO)
            Task(
                name="Gate 3: Bandit Security",
                description="Security scan",
                auto_fn=_run_bandit,
            ),
            ## -- Gate 4: Types (AUTO)
            Task(
                name="Gate 4: Mypy Types",
                description="Static type checking",
                auto_fn=_run_mypy,
            ),
            ## -- Gate 5: Tests (AUTO)
            Task(
                name="Gate 5: Pytest",
                description="Full test suite",
                auto_fn=_run_pytest,
            ),
            ## -- Gate 6: Analysis (INTERACTIVE — Claude reviews failures)
            Task(
                name="Gate 6: Build Analysis",
                description="Analyze any failures from gates 1-5",
                instruction="Review the build results from gates 1-5. "
                "If all passed: confirm green build, note test count and coverage. "
                "If any failed: identify the root cause, suggest fixes, "
                "and rate severity (blocker, major, minor).",
                context_files=["pyproject.toml"],
                done_when="Build health summary with action items if needed",
                model="sonnet",
            ),
        ],
        post_gates=[
            Gate(
                name="Build recorded",
                description="Build results saved",
                check_fn=lambda **_kw: (True, "Recorded by runner"),
            ),
        ],
    )
