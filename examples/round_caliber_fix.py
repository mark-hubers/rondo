#!/usr/bin/env python3
"""Rondo round: Run Caliber checks → Claude fixes failures.

First real end-to-end: Caliber finds problems, Rondo dispatches Claude to fix them.
"""

import json
import subprocess
import sys
from pathlib import Path

from rondo.engine import Gate, Round, Task

CALIBER_CLI = str(Path(__file__).resolve().parent.parent.parent / "caliber" / "spikes" / "cli-spike.py")
TARGET = str(Path.home() / "tmp" / "caliber-demo" / "buggy.py")


def _run_caliber() -> tuple[bool, str]:
    """Auto gate: run Caliber check and report results."""
    result = subprocess.run(
        [sys.executable, CALIBER_CLI, TARGET, "--json"],
        capture_output=True, text=True, timeout=60,
    )
    try:
        data = json.loads(result.stdout)
        summary = data.get("summary", {})
        failed = summary.get("failed", 0)
        if failed == 0:
            return (True, "All Caliber checks pass — no fixes needed")
        return (False, f"Caliber found {failed} failures — Claude needs to fix them")
    except json.JSONDecodeError:
        return (False, f"Caliber error: {result.stderr[:200]}")


def _get_failures() -> str:
    """Get Caliber failure details for Claude's instruction."""
    result = subprocess.run(
        [sys.executable, CALIBER_CLI, TARGET],
        capture_output=True, text=True, timeout=60,
    )
    return result.stdout


def build_round() -> Round:
    """Build the Caliber fix round."""
    failures = _get_failures()

    return Round(
        name="caliber-fix",
        pre_gates=[
            Gate(
                name="Caliber pre-check",
                check_fn=_run_caliber,
                blocking=False,
            ),
        ],
        tasks=[
            Task(
                name="fix-caliber-failures",
                description="Fix all Caliber findings in buggy.py",
                instruction=(
                    f"Caliber found these issues in {TARGET}:\n\n"
                    f"{failures}\n\n"
                    "Fix ALL issues:\n"
                    "- Add try/except around input()\n"
                    "- Replace os.system with subprocess.run (no shell=True)\n"
                    "- Add proper error handling\n"
                    "- Add type hints where missing\n"
                    "Do NOT add # nosec — actually fix the security issues."
                ),
                context_files=[TARGET],
                done_when="All Caliber checks would pass on the fixed code",
                model="sonnet",
            ),
        ],
        post_gates=[
            Gate(
                name="Caliber post-check",
                check_fn=_run_caliber,
            ),
        ],
    )
