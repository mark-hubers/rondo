#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Mark G. Hubers / HubersTech
# SPDX-License-Identifier: LicenseRef-Proprietary
"""Sprint Close Round — sprint close steps as a Rondo round.

Converts the sprint-close.py 5-step process into a verifiable round.
AUTO tasks run the actual close steps. INTERACTIVE tasks verify quality.

Created: 2026-03-13 (Session 75)
Author: Mark Hubers — HubersTech
"""

import subprocess
from pathlib import Path

from rondo.engine import Gate, Round, Task

_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent.parent)


def _check_active_sprint(**_kwargs: object) -> tuple[bool, str]:
    """Check if there's an active sprint to close."""
    active = Path(_PROJECT_ROOT) / "reports" / "ACTIVE-SPRINT.md"
    if active.exists():
        return True, f"Active sprint file found: {active}"
    return False, "No ACTIVE-SPRINT.md — nothing to close"


def _run_build(**_kwargs: object) -> tuple[bool, str]:
    """Run ace-build full as gate check."""
    result = subprocess.run(
        ["ace-build", "full"],
        capture_output=True,
        text=True,
        cwd=_PROJECT_ROOT,
        timeout=300,
    )
    if result.returncode == 0:
        return True, "Build passed all 6 gates"
    return False, f"Build failed: {result.stdout[-200:]}"


def build_sprint_close_round() -> Round:
    """Build a sprint close verification round."""
    return Round(
        name="sprint-close",
        round_num=0,
        description="Sprint close verification",
        pre_gates=[
            Gate(
                name="Active sprint exists",
                description="Must have an active sprint to close",
                check_fn=_check_active_sprint,
                blocking=True,
            ),
            Gate(
                name="Build passes",
                description="All 6 build gates must pass before close",
                check_fn=_run_build,
                blocking=True,
            ),
        ],
        tasks=[
            ## -- 1. Metrics collection (INTERACTIVE — Claude reads and summarizes)
            Task(
                name="Sprint Metrics",
                description="Collect sprint metrics before close",
                instruction="Read ACTIVE-SPRINT.md and reports/SPRINT-TRACKER.md. "
                "Summarize: files changed, tests added/modified, "
                "lines of code delta, coverage impact. "
                "Check if sprint goals listed in ACTIVE-SPRINT were met.",
                context_files=["reports/ACTIVE-SPRINT.md", "reports/SPRINT-TRACKER.md"],
                done_when="Sprint metrics summarized with goals-met assessment",
                model="sonnet",
            ),
            ## -- 2. Code quality review (INTERACTIVE)
            Task(
                name="Code Quality Review",
                description="Review code changes for quality",
                instruction="Run: git diff HEAD~1 --stat to see what changed. "
                "For each changed file: is the change clean? "
                "Any TODO comments left behind? Any temporary hacks? "
                "Rate overall quality: CLEAN, ACCEPTABLE, NEEDS-WORK.",
                context_files=["reports/ACTIVE-SPRINT.md"],
                done_when="Code quality rating with specific concerns if any",
                model="sonnet",
            ),
            ## -- 3. Symbol registration (INTERACTIVE)
            Task(
                name="Symbol Registration",
                description="Check if new symbols are registered",
                instruction="Look at files changed in this sprint. "
                "Are there new functions, classes, or constants? "
                "Check if they're in the symbols table in the DB. "
                "List any unregistered symbols that should be tracked.",
                context_files=["reports/ACTIVE-SPRINT.md"],
                done_when="New symbols catalogued: registered or flagged for registration",
                model="sonnet",
            ),
            ## -- 4. Tracker freshness (INTERACTIVE)
            Task(
                name="Tracker Freshness",
                description="Verify trackers are up to date",
                instruction="Check: "
                "1) SPRINT-TRACKER.md — does it reflect this sprint? "
                "2) ACE2-STATE.md — is the status current? "
                "3) ACE-JOURNAL.md — is today's entry at the top? "
                "Flag any tracker that's stale.",
                context_files=[
                    "reports/SPRINT-TRACKER.md",
                    "ace/ACE2-STATE.md",
                ],
                done_when="All trackers verified fresh or flagged stale",
                model="sonnet",
            ),
            ## -- 5. Close readiness (INTERACTIVE — synthesis)
            Task(
                name="Close Readiness",
                description="Final go/no-go for sprint close",
                instruction="Based on all previous checks: "
                "Is this sprint ready to close? "
                "GREEN = close it. YELLOW = close with notes. "
                "RED = fix issues first. "
                "List any open items that would carry to next sprint.",
                context_files=["reports/ACTIVE-SPRINT.md"],
                done_when="Close readiness: GREEN/YELLOW/RED with action items",
                model="opus",
            ),
        ],
        post_gates=[
            Gate(
                name="Close verified",
                description="Sprint close checks complete",
                check_fn=lambda **_kw: (True, "Recorded by runner"),
            ),
        ],
    )
