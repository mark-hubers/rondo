#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Mark G. Hubers / HubersTech
# SPDX-License-Identifier: LicenseRef-Proprietary
"""Rondo Dispatch — Level 2: Send tasks to Claude via CLI.

Serializes a Task object to a prompt or temp markdown file,
calls `claude -p`, captures the response, saves results.

Usage:
   python3 -m rondo.dispatch 3              # dispatch task 3 from design round
   python3 -m rondo.dispatch 3 --dry-run    # show prompt without calling claude
   python3 -m rondo.dispatch 3 4 5          # dispatch multiple tasks sequentially

Created: 2026-03-13 (Session 75 — Level 2 Spike)
Author: Mark Hubers — HubersTech
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

## -- Project root for imports
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from rondo.engine import Task, TaskMode  # noqa: E402

## -- Results directory
RESULTS_DIR = Path(_PROJECT_ROOT) / "reports" / "rondo-results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def _now() -> str:
    """ISO 8601 UTC timestamp."""
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")


# ═══════════════════════════════════════════════════════════════════════
# TASK → PROMPT SERIALIZATION
# ═══════════════════════════════════════════════════════════════════════


def task_to_prompt(task: Task, task_num: int = 0) -> str:
    """Serialize a Task to a prompt string for claude -p."""
    parts = [
        f"# Rondo Task {task_num}: {task.name}",
        "",
    ]

    if task.description:
        parts.append(f"**Description:** {task.description}")
        parts.append("")

    if task.context_files:
        parts.append(f"**Read these files first:** {', '.join(task.context_files)}")
        parts.append("")

    if task.instruction:
        parts.append(f"**Do:** {task.instruction}")
        parts.append("")

    if task.done_when:
        parts.append(f"**Done when:** {task.done_when}")
        parts.append("")

    parts.extend(
        [
            "---",
            "**Output format:** Respond with a JSON block at the end:",
            "```json",
            '{"status": "done"|"blocked", "confidence": 0.0-1.0,',
            ' "result": "what you did", "question": "if blocked, what you need"}',
            "```",
        ]
    )

    return "\n".join(parts)


def task_to_markdown(task: Task, task_num: int = 0) -> Path:
    """Serialize a Task to a temp markdown file. Returns the path."""
    prompt = task_to_prompt(task, task_num)

    ## -- Write to temp file (auto-cleaned on reboot)
    fd = tempfile.NamedTemporaryFile(
        mode="w",
        prefix=f"rondo-task-{task_num:03d}-",
        suffix=".md",
        dir=tempfile.gettempdir(),
        delete=False,
        encoding="utf-8",
    )
    fd.write(prompt)
    fd.close()
    return Path(fd.name)


# ═══════════════════════════════════════════════════════════════════════
# DISPATCH — call claude -p
# ═══════════════════════════════════════════════════════════════════════

## -- Model aliases for convenience
MODELS = {
    "opus": "opus",
    "sonnet": "sonnet",
    "haiku": "haiku",
}


def dispatch_task(
    task: Task,
    task_num: int = 0,
    dry_run: bool = False,
    use_file: bool = False,
    auth: str = "max",
    model: str | None = None,
    effort: str | None = None,
    max_budget: float | None = None,
) -> dict:
    """Dispatch a single task to Claude via CLI.

    Args:
       task: The Task to dispatch.
       task_num: Task number in the round.
       dry_run: If True, show prompt without calling claude.
       use_file: Force temp file delivery (auto for long prompts).
       auth: Auth mode — "max" (subscription) or "api" (ANTHROPIC_API_KEY).
       model: Model override — "opus", "sonnet", "haiku", or None (use task hint).
       effort: Effort override — "low", "medium", "high", "max", or None (use task hint).
       max_budget: Max USD per task (API mode only, None = no limit).

    Returns:
       Dict with: status, result, confidence, raw_output, duration_sec
    """
    ## -- Task recommends model/effort, CLI arg overrides if provided
    effective_model = model if model else task.model
    effective_effort = effort if effort else task.effort

    prompt = task_to_prompt(task, task_num)

    ## -- Auto-detect: use file for long prompts
    if use_file or len(prompt) > 500:
        md_path = task_to_markdown(task, task_num)
        claude_prompt = (
            f"Read the task file at {md_path} and execute it. Follow the output format instructions exactly."
        )
        print(f"  📋 Task {task_num}: {task.name}")
        print(f"     Delivery: temp file → {md_path}")
    else:
        claude_prompt = prompt
        md_path = None
        print(f"  📋 Task {task_num}: {task.name}")
        print(f"     Delivery: inline prompt ({len(prompt)} chars)")

    if dry_run:
        print(f"\n  {'─' * 50}")
        print("  DRY RUN — prompt that would be sent:")
        print(f"  {'─' * 50}")
        print(prompt)
        print(f"  {'─' * 50}")
        return {"status": "dry_run", "prompt": prompt, "task_num": task_num}

    ## -- Build child env: always strip CLAUDECODE (nested-session guard)
    ## -- Auth mode controls whether API key passes through:
    ## --   "max" = strip ANTHROPIC_API_KEY → uses Max plan (subscription)
    ## --   "api" = keep ANTHROPIC_API_KEY → uses API billing (pay-per-token)
    _strip_vars = {"CLAUDECODE"}
    if auth == "max":
        _strip_vars.add("ANTHROPIC_API_KEY")
    child_env = {k: v for k, v in os.environ.items() if k not in _strip_vars}

    auth_label = "Max plan" if auth == "max" else "API key"
    model_name = MODELS.get(effective_model, effective_model)
    print(f"     Auth: {auth_label}  Model: {model_name}  Effort: {effective_effort}")

    ## -- Build command with flags
    cmd = ["claude", "-p", claude_prompt, "--model", model_name, "--effort", effective_effort]
    if max_budget is not None and auth == "api":
        cmd.extend(["--max-budget-usd", str(max_budget)])

    print("     Calling: claude -p ...")
    start = datetime.now(UTC)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
            cwd=_PROJECT_ROOT,
            env=child_env,
        )
        duration = (datetime.now(UTC) - start).total_seconds()

        raw_output = result.stdout
        raw_stderr = result.stderr
        print(f"     Duration: {duration:.1f}s")
        print(f"     Exit code: {result.returncode}")

        ## -- Surface stderr so errors aren't silent
        if raw_stderr:
            print(f"     Stderr: {raw_stderr[:500]}")

        ## -- Non-zero exit with empty stdout = real error
        if result.returncode != 0 and not raw_output.strip():
            print("     ERROR: claude -p returned non-zero with no output")
            return {
                "status": "error",
                "error": raw_stderr[:500] if raw_stderr else f"exit code {result.returncode}",
                "raw_output": raw_output,
                "raw_stderr": raw_stderr,
                "duration_sec": duration,
                "task_num": task_num,
                "task_name": task.name,
            }

        ## -- Try to parse JSON from output
        parsed = _parse_response(raw_output)
        parsed["raw_output"] = raw_output
        parsed["raw_stderr"] = raw_stderr
        parsed["duration_sec"] = duration
        parsed["task_num"] = task_num
        parsed["task_name"] = task.name
        parsed["model"] = effective_model
        parsed["effort"] = effective_effort
        parsed["auth"] = auth

        ## -- Save result
        result_path = RESULTS_DIR / f"task-{task_num:03d}.json"
        result_path.write_text(json.dumps(parsed, indent=2), encoding="utf-8")
        print(f"     Result: {result_path}")

        return parsed

    except subprocess.TimeoutExpired:
        print("     TIMEOUT after 300s")
        return {"status": "timeout", "task_num": task_num, "task_name": task.name}

    except FileNotFoundError:
        print("     ERROR: 'claude' command not found in PATH")
        return {"status": "error", "error": "claude not found", "task_num": task_num}


def _parse_response(raw: str) -> dict:
    """Try to extract JSON result from Claude's response."""
    ## -- Look for ```json ... ``` block
    json_match = re.search(r"```json\s*\n(.*?)\n\s*```", raw, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass

    ## -- Try parsing the whole thing as JSON
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        pass

    ## -- Fallback: wrap raw text
    return {"status": "done", "result": raw[:500], "confidence": 0.5}


# ═══════════════════════════════════════════════════════════════════════
# CLI ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════


def main() -> None:
    """CLI: dispatch tasks from the OB-REQ-100 design round."""
    parser = argparse.ArgumentParser(
        description="Rondo Dispatch — send tasks to Claude via CLI",
    )
    parser.add_argument(
        "tasks",
        nargs="+",
        type=int,
        help="Task numbers to dispatch (1-15 for design round)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Show prompt without calling claude")
    parser.add_argument("--file", action="store_true", help="Force temp file delivery")
    parser.add_argument(
        "--auth", choices=["max", "api"], default="max", help="Auth mode: max (subscription) or api (ANTHROPIC_API_KEY)"
    )
    parser.add_argument(
        "--model",
        choices=["opus", "sonnet", "haiku"],
        default=None,
        help="Model override: opus (complex), sonnet (balanced), haiku (bulk/cheap). Default: task decides.",
    )
    parser.add_argument(
        "--effort",
        choices=["low", "medium", "high", "max"],
        default=None,
        help="Effort override. Default: task decides (usually high).",
    )
    parser.add_argument("--max-budget", type=float, default=None, help="Max USD per task (API mode only)")
    parser.add_argument("--spec", default="OB-REQ-100", help="Spec ID (default: OB-REQ-100)")

    args = parser.parse_args()

    ## -- Import here to avoid circular dependency
    sys.path.insert(0, _PROJECT_ROOT)
    from ob.demo_round import build_design_round

    round_def = build_design_round(args.spec)

    auth_label = "Max plan" if args.auth == "max" else "API key"
    model_label = args.model or "per-task"
    effort_label = args.effort or "per-task"
    print(f"\n  {'═' * 60}")
    print("  RONDO DISPATCH — Level 2 Spike")
    print(f"  Sending {len(args.tasks)} task(s) to Claude via CLI")
    print(f"  Auth: {auth_label}  Model: {model_label}  Effort: {effort_label}")
    print(f"  {'═' * 60}")

    results = []
    for task_num in args.tasks:
        if task_num < 1 or task_num > len(round_def.tasks):
            print(f"\n  ✗ Task {task_num}: invalid (round has {len(round_def.tasks)} tasks)")
            continue

        task = round_def.tasks[task_num - 1]

        if task.mode != TaskMode.INTERACTIVE:
            print(f"\n  ⊘ Task {task_num}: {task.name} — AUTO task, skipping (use run_round for auto)")
            continue

        print()
        result = dispatch_task(
            task,
            task_num,
            dry_run=args.dry_run,
            use_file=args.file,
            auth=args.auth,
            model=args.model,
            effort=args.effort,
            max_budget=args.max_budget,
        )
        results.append(result)

    ## -- Summary
    print(f"\n  {'═' * 60}")
    print("  DISPATCH SUMMARY")
    print(f"  {'─' * 50}")
    for r in results:
        status = r.get("status", "unknown")
        name = r.get("task_name", f"task-{r.get('task_num', '?')}")
        print(f"  {'✓' if status == 'done' else '⏳'} Task {r.get('task_num')}: {name} — {status}")
    print(f"  {'═' * 60}\n")


if __name__ == "__main__":
    main()
