"""Rondo Example 04: Dispatch Hooks.

Usage: rondo run examples/04-with-hooks.py

Hooks let you process prompts BEFORE dispatch and results AFTER.
Pre-hooks: sanitize, transform, enrich prompts.
Post-hooks: validate, format, alert on results.

This is the power-user feature — Python required for hooks.
"""

import re

from rondo.engine import DispatchUsage, Round, Task, TaskResult


def redact_emails(prompt: str, task, config) -> str:
    """Remove email addresses before sending to cloud AI."""
    return re.sub(r"\b[\w.]+@[\w.]+\.\w+\b", "[REDACTED]", prompt)


def warn_high_cost(result: TaskResult, usage: DispatchUsage) -> TaskResult:
    """Print a warning if dispatch cost exceeds $0.10."""
    if usage.cost_usd > 0.10:
        print(f"  WARNING: ${usage.cost_usd:.4f} for {result.task_name}")
    return result


def build_round() -> Round:
    return Round(
        name="hooked-review",
        tasks=[
            Task(
                name="review-with-hooks",
                instruction="Review this code for security issues",
                done_when="List all findings",
                pre_dispatch=[redact_emails],
                post_dispatch=[warn_high_cost],
            ),
        ],
    )
