"""Rondo example: security audit round with sanitization.

Demonstrates STD-114 (output sanitization) integration with dispatch.
The audit trail (STD-113) records every dispatch automatically.
Flakiness detection (REQ-107) tracks results over time.

This is a REAL working round — run with:
    rondo run examples/rounds/round_security_audit.py --dry-run --verbose
    rondo run examples/rounds/round_security_audit.py --bare --max-budget 0.50
"""

from rondo.engine import Gate, Round, Task


def _check_git_clean() -> tuple[bool, str]:
    """Pre-gate: ensure working directory is clean."""
    import subprocess

    result = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.stdout.strip():
        return False, f"Working directory has {len(result.stdout.strip().splitlines())} uncommitted changes"
    return True, "Working directory clean"


def build_round() -> Round:
    """Security audit: scan code for secrets, review error handling."""
    return Round(
        name="security-audit",
        pre_gates=[
            Gate(name="git-clean", check_fn=_check_git_clean),
        ],
        tasks=[
            Task(
                name="secret-scan",
                description="Find hardcoded secrets in source files",
                instruction=(
                    "Scan all Python files in src/ for hardcoded secrets: "
                    "API keys, passwords, tokens, private keys, connection strings. "
                    "Report each finding with file, line number, and pattern matched. "
                    "Do NOT include the actual secret value in your output."
                ),
                context_files=["src/"],
                done_when="All Python files scanned, findings listed with file:line references",
                human_input="Focus on config files and test fixtures — those are most likely to have leaked secrets",
            ),
            Task(
                name="error-handling-review",
                description="Check error handling patterns",
                instruction=(
                    "Review all try/except blocks in the codebase. Flag: "
                    "1. Bare except clauses (catch-all). "
                    "2. Exception swallowing (except: pass). "
                    "3. Missing error context in re-raises. "
                    "4. User-facing error messages that leak internal paths."
                ),
                context_files=["src/"],
                done_when="All try/except blocks reviewed, issues categorized by severity",
            ),
        ],
    )
