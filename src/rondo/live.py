# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Rondo live mode — execute round tasks in current conversation.

Rondo-REQ-100 reqs 47-56.
Presents one task at a time. Claude reads instruction, executes, proves done_when.
Mark reviews. Same round definition as batch mode.

Usage:
    rondo live round.py             # run all tasks
    rondo live round.py --from 3    # resume from task 3
    rondo live round.py --task 5    # run only task 5
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from rondo.engine import Round, Task


def present_task(task: Task, index: int, total: int) -> dict:
    """Present one task for live execution. Returns task summary dict.

    Rondo-REQ-100 req 48: presents ONE task at a time.
    """
    print(f"\n{'═' * 70}")
    print(f"  TASK {index + 1} of {total}: {task.name}")
    print(f"{'═' * 70}")
    print()

    # -- Build summary dict (populated incrementally)
    summary: dict = {
        "task_index": index + 1,
        "task_name": task.name,
        "presented_at": datetime.now(UTC).isoformat(),
        "mode": "auto" if task.is_auto else "interactive",
    }

    if task.description:
        print(f"  {task.description}")
        print()

    if task.is_auto:
        print("  MODE: auto (Python callable)")
        # -- Finding #153: execute auto_fn in live mode
        try:
            auto_result = task.auto_fn()  # type: ignore[misc]
            passed, message = auto_result
            status_label = "PASS" if passed else "FAIL"
            print(f"  RESULT: {status_label} — {message}")
            summary["auto_result"] = auto_result
        except Exception as exc:  # noqa: BLE001  # pylint: disable=broad-exception-caught
            # -- RONDO-209 #254: broad-except is INTENTIONAL — task.auto_fn is
            # -- user-supplied Python code. We can't predict what exceptions it
            # -- raises. We DO surface the type and message so user errors are
            # -- visible (not silent). SystemExit/KeyboardInterrupt are BaseException
            # -- subclasses and correctly NOT caught here.
            print(f"  ERROR: auto_fn raised {type(exc).__name__}: {exc}")
            summary["auto_error"] = str(exc)
    else:
        print("INSTRUCTION:")
        instruction = task.instruction.strip()
        for line in instruction.split("\n"):
            print(f"  {line}")
        print()
        print(f"DONE WHEN: {task.done_when}")
        print()
        if task.context_files:
            print(f"CONTEXT FILES ({len(task.context_files)}):")
            for cf in task.context_files:
                print(f"  → {cf}")
            print()

    # -- REQ-100 req 063: human_input shown before dispatch
    if task.human_input:
        print("HUMAN INPUT REQUIRED:")
        print(f"  {task.human_input}")
        print()

    # -- REQ-106: context_data shown in live mode
    if task.context_data:
        print(f"CONTEXT DATA ({len(task.context_data)} keys):")
        for key in task.context_data:
            print(f"  → {key}")
        print()

    if task.model:
        print(f"MODEL: {task.model}")

    print(f"{'─' * 70}")
    print()

    return summary


def run_live(
    round_def: Round,
    start_from: int = 0,
    single_task: int = -1,
    progress_file: Path | None = None,
) -> list[dict]:
    """Execute a round in live mode — present tasks step by step.

    Rondo-REQ-100 reqs 47-56.

    Args:
        round_def: The round to execute.
        start_from: Resume from this task index (0-based).
        single_task: Run only this task index (0-based). -1 = run all.
        progress_file: Optional path to save progress for --resume.

    Returns:
        List of task presentation records.
    """
    tasks = round_def.tasks
    total = len(tasks)
    presentations: list[dict] = []

    print("=== RONDO LIVE MODE ===")
    print(f"Round: {round_def.name}")
    print(f"Tasks: {total}")
    if start_from > 0:
        print(f"Resuming from task {start_from + 1}")
    print()

    # -- Pre-gates
    for gate in round_def.pre_gates:
        print(f"  PRE-GATE: {gate.name}")
        if gate.check_fn:
            passed, detail = gate.check_fn()
            status = "✓ PASS" if passed else "✗ FAIL"
            print(f"    {status}: {detail}")
            if not passed and gate.blocking:
                print("\n  -ERROR- Pre-gate failed. Cannot proceed.")
                return presentations
        else:
            # -- RONDO-338: description existed in this print before it existed on
            # -- Gate (latent AttributeError); fall back to name when empty
            print(f"    Manual check: {gate.description or gate.name}")
    print()

    if single_task >= 0:
        # -- Single task mode
        if single_task >= total:
            print(
                f"-ERROR- Task {single_task + 1} doesn't exist (max {total})",
            )
            return presentations
        record = present_task(tasks[single_task], single_task, total)
        presentations.append(record)
    else:
        # -- Sequential mode
        for idx in range(start_from, total):
            record = present_task(tasks[idx], idx, total)
            presentations.append(record)

            # -- Save progress for --resume
            # -- Note (Finding #154): progress tracks PRESENTATION, not
            # -- verification. "completed_task" = presented to Claude,
            # -- not confirmed done by human review.
            if progress_file:
                progress = {
                    "round": round_def.name,
                    "completed_task": idx,
                    "total_tasks": total,
                    "saved_at": datetime.now(UTC).isoformat(),
                }
                progress_file.write_text(json.dumps(progress, indent=2), encoding="utf-8")

    print(f"\n{'═' * 70}")
    if single_task >= 0:
        print(f"  TASK {single_task + 1} PRESENTED")
    else:
        completed = len(presentations)
        print(f"  {completed}/{total} TASKS PRESENTED")
    print(f"{'═' * 70}")

    return presentations


def load_progress(progress_file: Path) -> dict:
    """Load saved progress for --resume.

    Rondo-REQ-100 req 56: resume from last completed task.
    """
    if progress_file.exists():
        return json.loads(progress_file.read_text())
    return {}


# -- sig: mgh-6201.cd.bd955f.a1b2.c3d4e5
