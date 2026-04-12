# rondo-meta: mode=subprocess provider=anthropic category=pipeline value="Four-stage scan/review/fix/verify round workflow"

"""Rondo demo: Unix-style pipeline — scan → review → fix → verify.

Shows how rounds chain together like Unix pipes: each step reads the
previous step's JSON output, does its work, writes its own JSON.

Usage (run each step, or run all via overnight):

    # -- Step by step (like piping commands):
    rondo run examples/rounds/demo_pipeline.py

    # -- All at once (overnight mode):
    rondo overnight examples/demo_pipeline.py

    # -- Dry run (see prompts without invoking Claude):
    rondo run examples/rounds/demo_pipeline.py --dry-run
"""

import json
from pathlib import Path

from rondo.engine import Gate, Round, Task

RESULTS_DIR = Path("reports/rondo-results")
TARGET = "src/"


# -- Step 1: SCAN (auto + interactive)
# -- Like: find . -name "*.py" | grep TODO
def _count_python_files() -> tuple[bool, str]:
    """Auto task: count .py files (no Claude needed)."""
    files = list(Path(TARGET).rglob("*.py")) if Path(TARGET).exists() else []
    return (len(files) > 0, f"{len(files)} Python files found")


def _build_scan() -> Round:
    """Step 1: Scan the codebase — what's there?"""
    return Round(
        name="step-1-scan",
        tasks=[
            Task(
                name="count-files",
                description="Count Python files (auto — no Claude needed)",
                auto_fn=_count_python_files,
            ),
            Task(
                name="find-issues",
                description="Ask Claude to find TODOs, FIXMEs, and code smells",
                instruction=(
                    f"Scan all Python files in {TARGET} for:\n"
                    "- TODO and FIXME comments\n"
                    "- Functions longer than 40 lines\n"
                    "- Missing type hints on public functions\n\n"
                    "Output a table: file, line, category, description"
                ),
                context_files=[TARGET],
                done_when="Table of issues found with file, line, category, description",
                model="haiku",
            ),
        ],
    )


# -- Step 2: REVIEW (reads Step 1 output)
# -- Like: cat scan-results.json | review-script
def _scan_completed() -> tuple[bool, str]:
    """Gate: check that Step 1 produced output."""
    result_file = RESULTS_DIR / "task-find-issues.json"
    if result_file.exists():
        data = json.loads(result_file.read_text())
        if data.get("status") == "done":
            return (True, "Scan results available")
    return (False, "Step 1 (scan) must complete first — run: rondo run demo_pipeline.py step-1-scan")


def _build_review() -> Round:
    """Step 2: Review scan findings — prioritize what matters."""
    # -- Read Step 1 output (Unix pipe: previous stdout → this stdin)
    findings = "No scan results found"
    result_file = RESULTS_DIR / "task-find-issues.json"
    if result_file.exists():
        data = json.loads(result_file.read_text())
        parsed = data.get("parsed_result", {})
        findings = parsed.get("result", findings)

    return Round(
        name="step-2-review",
        pre_gates=[
            Gate("Scan completed", check_fn=_scan_completed, blocking=True),
        ],
        tasks=[
            Task(
                name="prioritize",
                description="Prioritize scan findings by severity",
                instruction=(
                    f"Previous scan found these issues:\n\n{findings}\n\n"
                    "Prioritize each issue:\n"
                    "- CRITICAL: bugs, security issues, data loss risks\n"
                    "- WARNING: code quality, missing types, long functions\n"
                    "- NIT: style, naming, minor cleanup\n\n"
                    "Output a table: priority, file, line, issue, suggested fix"
                ),
                done_when="Prioritized table with suggested fixes for each issue",
                model="sonnet",
            ),
        ],
    )


# -- Step 3: FIX (reads Step 2 output)
# -- Like: cat review-results.json | fix-script
def _review_completed() -> tuple[bool, str]:
    """Gate: check that Step 2 produced output."""
    result_file = RESULTS_DIR / "task-prioritize.json"
    if result_file.exists():
        data = json.loads(result_file.read_text())
        if data.get("status") == "done":
            return (True, "Review results available")
    return (False, "Step 2 (review) must complete first")


def _build_fix() -> Round:
    """Step 3: Fix critical issues found in review."""
    priorities = "No review results found"
    result_file = RESULTS_DIR / "task-prioritize.json"
    if result_file.exists():
        data = json.loads(result_file.read_text())
        parsed = data.get("parsed_result", {})
        priorities = parsed.get("result", priorities)

    return Round(
        name="step-3-fix",
        pre_gates=[
            Gate("Review completed", check_fn=_review_completed, blocking=True),
        ],
        tasks=[
            Task(
                name="fix-critical",
                description="Fix CRITICAL issues from the review",
                instruction=(
                    f"Review prioritized these issues:\n\n{priorities}\n\n"
                    "Fix all CRITICAL issues. For each fix:\n"
                    "1. Show the file and line\n"
                    "2. Show before/after code\n"
                    "3. Explain what was wrong and why the fix is correct"
                ),
                context_files=[TARGET],
                done_when="All CRITICAL issues fixed with before/after code shown",
                model="sonnet",
            ),
        ],
    )


# -- Step 4: VERIFY (reads Step 3 output)
# -- Like: cat fix-results.json | verify-script
def _fixes_applied() -> tuple[bool, str]:
    """Gate: check that Step 3 produced output."""
    result_file = RESULTS_DIR / "task-fix-critical.json"
    if result_file.exists():
        data = json.loads(result_file.read_text())
        if data.get("status") == "done":
            return (True, "Fix results available")
    return (False, "Step 3 (fix) must complete first")


def _build_verify() -> Round:
    """Step 4: Verify fixes didn't break anything."""
    return Round(
        name="step-4-verify",
        pre_gates=[
            Gate("Fixes applied", check_fn=_fixes_applied, blocking=True),
        ],
        tasks=[
            Task(
                name="verify-clean",
                description="Auto-check: does the code still parse?",
                auto_fn=lambda: (True, "Syntax check passed (placeholder)"),
            ),
            Task(
                name="verify-review",
                description="Ask Claude to verify the fixes are correct",
                instruction=(
                    "Review the recent changes in src/. For each change:\n"
                    "1. Does the fix actually address the original issue?\n"
                    "2. Did the fix introduce any new problems?\n"
                    "3. Are there any edge cases not handled?\n\n"
                    "Output: PASS (all good) or FAIL (with details of what's wrong)"
                ),
                context_files=[TARGET],
                done_when="PASS or FAIL verdict with reasoning for each fix",
                model="haiku",
            ),
        ],
    )


# ──────────────────────────────────────────────────────────────────────
# Entry points: run one step or run all as overnight phases
# ──────────────────────────────────────────────────────────────────────


def build_round() -> Round:
    """Default: run Step 1 (scan). Chain the rest manually or use overnight."""
    return _build_scan()


def build_phases() -> list[Round]:
    """Overnight: run all 4 steps in sequence — scan → review → fix → verify."""
    return [
        _build_scan(),
        _build_review(),
        _build_fix(),
        _build_verify(),
    ]
