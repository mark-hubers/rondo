# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
# rondo-meta: mode=subprocess provider=anthropic category=pipeline value="Prompt/result hook lifecycle from Python API"

"""Rondo API: Dispatch with Hooks.

Pre-hooks transform prompts before dispatch.
Post-hooks process results after dispatch.
"""

import re

from rondo.config import RondoConfig
from rondo.engine import DispatchUsage, Task, TaskResult
from rondo.hooks import run_pre_dispatch_hooks


def redact_emails(prompt: str, _task: Task, _config: RondoConfig) -> str:
    """Remove email addresses before sending to cloud AI."""
    return re.sub(r"\b[\w.]+@[\w.]+\.\w+\b", "[REDACTED]", prompt)


def flag_high_cost(result: TaskResult, usage: DispatchUsage) -> TaskResult:
    """Warn if dispatch cost exceeds $0.10."""
    if usage.cost_usd > 0.10:
        result.raw_output = f"[HIGH COST: ${usage.cost_usd:.4f}]\n{result.raw_output}"
    return result


def main() -> None:
    """Demonstrate hook chaining."""
    task = Task(
        name="review",
        instruction="Review user@example.com code",
        pre_dispatch=[redact_emails],
        post_dispatch=[flag_high_cost],
    )
    hooked, trace = run_pre_dispatch_hooks(task.instruction, task, RondoConfig())
    print(f"Original: {task.instruction}")
    print(f"After hooks: {hooked}")
    print(f"Trace: {trace}")


if __name__ == "__main__":
    main()


# -- sig: mgh-6201.cd.bd955f.e003.a10300
