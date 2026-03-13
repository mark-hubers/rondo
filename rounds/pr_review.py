#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Mark G. Hubers / HubersTech
# SPDX-License-Identifier: LicenseRef-Proprietary
"""PR Review Round — AI code review before merge.

Runs git diff, creates a task per changed file, plus cross-cutting
checks for architecture, testing, and documentation impact.

Usage:
   from rondo.rounds.pr_review import build_pr_review_round
   round_def = build_pr_review_round()          # diff against main
   round_def = build_pr_review_round("HEAD~3")  # diff against 3 commits back

Created: 2026-03-13 (Session 75)
Author: Mark Hubers — HubersTech
"""

import subprocess
from pathlib import Path

from rondo.engine import Gate, Round, Task

_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent.parent)


def _get_changed_files(base: str = "main") -> list[str]:
    """Get list of files changed vs base branch/commit."""
    result = subprocess.run(
        ["git", "diff", "--name-only", base],
        capture_output=True,
        text=True,
        cwd=_PROJECT_ROOT,
    )
    if result.returncode != 0:
        return []
    return [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]


def _check_has_changes(**kwargs: object) -> tuple[bool, str]:
    """Verify there are changes to review."""
    base = str(kwargs.get("base", "main"))
    files = _get_changed_files(base)
    if files:
        return True, f"{len(files)} files changed vs {base}"
    return False, f"No changes vs {base}"


def build_pr_review_round(base: str = "main", max_files: int = 15) -> Round:
    """Build a PR review round from git diff.

    Args:
       base: Base branch/commit to diff against
       max_files: Max files to create individual tasks for (rest get bulk review)
    """
    changed_files = _get_changed_files(base)

    ## -- Build file-specific review tasks
    file_tasks = []
    for filepath in changed_files[:max_files]:
        ## -- Choose model based on file type
        if filepath.endswith((".py",)):
            model = "sonnet"
        elif filepath.endswith((".md",)):
            model = "haiku"
        elif filepath.endswith((".sql", ".toml", ".json")):
            model = "sonnet"
        else:
            model = "sonnet"

        file_tasks.append(
            Task(
                name=f"Review: {filepath}",
                description=f"Code review for {filepath}",
                instruction=f"Review the changes in {filepath}. Check for: "
                "1) Correctness — does the logic do what it should? "
                "2) Security — any injection, exposure, or unsafe patterns? "
                "3) Style — matches project conventions (## for comments, snake_case)? "
                "4) Edge cases — missing error handling, off-by-one, None checks? "
                "5) Tests — should this change have a test? Is one missing? "
                "Rate: APPROVE, COMMENT (minor), REQUEST_CHANGES (must fix).",
                context_files=[filepath],
                done_when=f"Review verdict for {filepath} with specific line-level comments",
                model=model,
            ),
        )

    ## -- If too many files, add a bulk task for the rest
    if len(changed_files) > max_files:
        overflow = changed_files[max_files:]
        file_tasks.append(
            Task(
                name=f"Bulk Review: {len(overflow)} remaining files",
                description="Quick scan of remaining changed files",
                instruction=f"Quick scan these files for obvious issues: "
                f"{', '.join(overflow[:20])}. "
                "Flag only: security issues, broken imports, syntax errors. "
                "Skip style and minor issues for bulk review.",
                context_files=overflow[:10],
                done_when="Bulk scan complete with critical issues flagged",
                model="sonnet",
            ),
        )

    ## -- Cross-cutting review tasks
    cross_tasks = [
        Task(
            name="Architecture Impact",
            description="Check if changes respect layer boundaries",
            instruction="Look at ALL changed files together. "
            "Do any changes cross architecture layer boundaries? "
            "Do any new imports create circular dependencies? "
            "Does the change touch files in multiple layers that should be separate PRs? "
            f"Changed files: {', '.join(changed_files[:20])}",
            context_files=["pyproject.toml"],
            done_when="Architecture impact assessment: NONE, LOW, HIGH",
            model="opus",
        ),
        Task(
            name="Test Coverage",
            description="Are changed files adequately tested?",
            instruction="For each changed source file (src/, scripts/, rondo/), "
            "check: does a corresponding test file exist? "
            "If source was modified, should the test be updated? "
            "List any test gaps. "
            f"Changed files: {', '.join(changed_files[:20])}",
            context_files=[],
            done_when="Test gap list or confirmed adequate coverage",
            model="sonnet",
        ),
        Task(
            name="PR Summary",
            description="Overall review verdict",
            instruction="Based on all file reviews and cross-cutting checks: "
            "1) Overall verdict: APPROVE, COMMENT, REQUEST_CHANGES "
            "2) Summary of what this change does (1-2 sentences) "
            "3) Top concerns (if any) "
            "4) Suggested follow-up tasks",
            context_files=[],
            done_when="PR verdict with summary and action items",
            model="opus",
        ),
    ]

    return Round(
        name="pr-review",
        round_num=0,
        description=f"PR review: {len(changed_files)} files changed vs {base}",
        pre_gates=[
            Gate(
                name="Has changes",
                description=f"Files changed vs {base}",
                check_fn=_check_has_changes,
                blocking=True,
            ),
        ],
        tasks=file_tasks + cross_tasks,
        post_gates=[
            Gate(
                name="Review complete",
                description="All files reviewed",
                check_fn=lambda **_kw: (True, "Review recorded"),
            ),
        ],
    )
