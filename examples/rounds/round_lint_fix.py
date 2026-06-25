#!/usr/bin/env python3
# rondo-meta: mode=subprocess provider=anthropic category=pipeline value="Linter findings to an automated fix workflow"

"""Rondo round: run a linter (ruff) -> Claude fixes the findings -> re-check.

A self-contained quality-gate loop. ruff finds problems in a generated sample
file, Rondo dispatches Claude to fix them, then ruff re-checks as a post-gate.
Uses ruff (a standard Python linter) and a sample written to a temp dir, so it
runs anywhere with no external setup or hardcoded paths.
"""

import shutil
import subprocess
import tempfile
from pathlib import Path

from rondo.engine import Gate, Round, Task

## -- An intentionally messy sample (unused imports + unused variable), written
## -- to a temp file so the example is fully self-contained and runnable on any
## -- machine. ruff flags F401 (unused import) and F841 (unused variable).
SAMPLE_CODE = """import os
import sys


def add(a, b):
    unused = 1
    return a + b
"""


def _sample_target() -> str:
    """Write the demo sample to a temp file and return its path."""
    path = Path(tempfile.gettempdir()) / "rondo-lint-demo" / "sample.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(SAMPLE_CODE)
    return str(path)


TARGET = _sample_target()


def _run_ruff() -> tuple[bool, str]:
    """Gate: run ruff on the sample and report whether it is clean."""
    ruff = shutil.which("ruff")
    if ruff is None:
        return (False, "ruff not installed — `pip install ruff` to run this example for real")
    result = subprocess.run(
        [ruff, "check", TARGET],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if result.returncode == 0:
        return (True, "ruff is clean — no fixes needed")
    return (False, f"ruff found issues:\n{result.stdout}")


def build_round() -> Round:
    """Build the lint -> fix -> re-check round."""
    _, findings = _run_ruff()

    return Round(
        name="lint-fix",
        pre_gates=[
            Gate(name="ruff pre-check", check_fn=_run_ruff, blocking=False),
        ],
        tasks=[
            Task(
                name="fix-lint-findings",
                # -- The sample is embedded inline (not passed via context_files):
                # -- context_files must be repo-relative, and this demo's sample
                # -- lives in a temp dir, so we hand Claude the source directly.
                description="Fix all ruff findings in the sample file",
                instruction=(
                    "Here is a Python file:\n\n"
                    f"```python\n{SAMPLE_CODE}```\n\n"
                    f"ruff reported:\n\n{findings}\n\n"
                    "Return the fixed file. Remove unused imports and variables and "
                    "tidy formatting. Do NOT add noqa comments — actually fix the code."
                ),
                done_when="ruff check passes on the fixed file",
                model="sonnet",
            ),
        ],
        post_gates=[
            Gate(name="ruff post-check", check_fn=_run_ruff),
        ],
    )
