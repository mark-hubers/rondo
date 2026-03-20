#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Mark G. Hubers / HubersTech
# SPDX-License-Identifier: LicenseRef-Proprietary
"""Rondo Parallel — Level 3: dispatch multiple tasks simultaneously.

Uses concurrent.futures to run N tasks in parallel via claude -p.
Handles result collection, conflict detection, and throttling.

Usage:
   python3 -m rondo.parallel spec-health OB-REQ-001 --workers 4
   python3 -m rondo.parallel spec-health --all-ob --workers 2

Created: 2026-03-13 (Session 75)
Author: Mark Hubers — HubersTech
"""

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from rondo.dispatch import RESULTS_DIR, dispatch_task  # noqa: E402
from rondo.engine import TaskMode  # noqa: E402
from rondo.runner import _find_all_specs, _find_ob_specs  # noqa: E402

PARALLEL_RESULTS_DIR = RESULTS_DIR / "parallel"
PARALLEL_RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def _now_stamp() -> str:
    """Filename-safe timestamp."""
    return datetime.now(UTC).strftime("%Y%m%d-%H%M%S")


def dispatch_round_parallel(
    round_def: object,
    auth: str = "max",
    model: str | None = None,
    effort: str | None = None,
    workers: int = 4,
    throttle_sec: float = 2.0,
    spec_id: str = "",
) -> dict:
    """Dispatch all interactive tasks in parallel.

    Args:
       round_def: A Round object
       auth: Auth mode
       model: Model override (None = task decides)
       effort: Effort override
       workers: Max concurrent Claude instances
       throttle_sec: Delay between launches (respect rate limits)
       spec_id: Spec being checked

    Returns:
       Dict with round results
    """
    tasks = [t for t in round_def.tasks if t.mode == TaskMode.INTERACTIVE]

    print(f"\n  {'═' * 60}")
    print("  RONDO PARALLEL DISPATCH")
    print(f"  Round: {round_def.name}  Spec: {spec_id or 'project'}")
    print(f"  Tasks: {len(tasks)}  Workers: {workers}  Throttle: {throttle_sec}s")
    auth_label = "Max plan" if auth == "max" else "API key"
    print(f"  Auth: {auth_label}  Model: {model or 'per-task'}")
    print(f"  {'═' * 60}")

    results = {}
    start_time = datetime.now(UTC)

    def _dispatch_one(task_num: int, task: object) -> tuple[int, dict]:
        """Worker function — dispatches one task."""
        result = dispatch_task(
            task,
            task_num=task_num,
            auth=auth,
            model=model,
            effort=effort,
        )
        return task_num, result

    ## -- Launch tasks with throttle
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {}
        for i, task in enumerate(tasks, 1):
            future = executor.submit(_dispatch_one, i, task)
            futures[future] = i
            if i < len(tasks):
                time.sleep(throttle_sec)

        ## -- Collect results as they complete
        for future in as_completed(futures):
            task_num = futures[future]
            try:
                num, result = future.result()
                results[num] = result
                status = result.get("status", "?")
                dur = result.get("duration_sec", 0)
                print(f"  ✓ Task {num} complete: {status} ({dur:.0f}s)")
            except Exception as e:
                results[task_num] = {"status": "error", "error": str(e), "task_num": task_num}
                print(f"  ✗ Task {task_num} failed: {e}")

    total_time = (datetime.now(UTC) - start_time).total_seconds()

    ## -- Conflict detection: check if multiple tasks touched same file
    ## -- (parse raw_output for file paths mentioned)
    conflicts = _detect_conflicts(results)

    ## -- Summary
    done_count = sum(1 for r in results.values() if r.get("status") == "done")
    error_count = sum(1 for r in results.values() if r.get("status") in ("error", "blocked"))

    summary = {
        "spec_id": spec_id,
        "round_name": round_def.name,
        "mode": "parallel",
        "workers": workers,
        "status": "complete" if error_count == 0 else "partial",
        "tasks_done": done_count,
        "tasks_error": error_count,
        "total_duration_sec": total_time,
        "conflicts": conflicts,
        "timestamp": datetime.now(UTC).isoformat(),
        "tasks": [results.get(i, {}) for i in sorted(results.keys())],
    }

    ## -- Save
    safe_spec = spec_id.replace("/", "-") if spec_id else "project"
    result_path = PARALLEL_RESULTS_DIR / f"{round_def.name}-{safe_spec}-{_now_stamp()}.json"
    result_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")

    print(f"\n  {'═' * 60}")
    print("  PARALLEL SUMMARY")
    print(f"  {'─' * 50}")
    print(f"  ✓ Done: {done_count}  ✗ Error: {error_count}")
    print(f"  Wall time: {total_time:.0f}s ({total_time / 60:.1f}m)")
    sum_task_time = sum(r.get("duration_sec", 0) for r in results.values())
    print(f"  Task time: {sum_task_time:.0f}s (speedup: {sum_task_time / total_time:.1f}x)")
    if conflicts:
        print(f"  ⚠ Conflicts detected: {len(conflicts)}")
        for c in conflicts[:5]:
            print(f"     {c}")
    print(f"  Result: {result_path}")
    print(f"  {'═' * 60}\n")

    return summary


def _detect_conflicts(results: dict) -> list[str]:
    """Detect potential file conflicts from parallel tasks.

    Looks for file paths mentioned in multiple task results.
    """
    ## -- Simple heuristic: look for file paths in raw_output
    file_mentions: dict[str, list[int]] = {}
    for task_num, result in results.items():
        raw = result.get("raw_output", "")
        ## -- Look for common file patterns
        for word in raw.split():
            if "/" in word and ("." in word.split("/")[-1]):
                ## -- Looks like a file path
                clean = word.strip("`,\"'()[]")
                if clean.endswith((".py", ".md", ".sql", ".toml", ".json")):
                    file_mentions.setdefault(clean, []).append(task_num)

    ## -- Files mentioned by 2+ tasks = potential conflict
    conflicts = []
    for filepath, task_nums in file_mentions.items():
        if len(task_nums) > 1:
            conflicts.append(f"{filepath} mentioned by tasks {task_nums}")

    return conflicts


def main() -> None:
    """CLI: parallel dispatch."""
    parser = argparse.ArgumentParser(description="Rondo Parallel — concurrent task dispatch")
    parser.add_argument(
        "round",
        choices=["spec-health", "digest-refresh", "convention-check", "pr-review", "test-gaps", "knowledge-mine"],
    )
    parser.add_argument("spec", nargs="?", default=None)
    parser.add_argument("--all-ob", action="store_true")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--workers", type=int, default=4, help="Max concurrent tasks (default: 4)")
    parser.add_argument("--throttle", type=float, default=2.0, help="Seconds between launches (default: 2)")
    parser.add_argument("--auth", choices=["max", "api"], default="max")
    parser.add_argument("--model", choices=["opus", "sonnet", "haiku"], default=None)
    parser.add_argument("--effort", choices=["low", "medium", "high", "max"], default=None)

    args = parser.parse_args()

    ## -- Determine specs
    if args.round in ("spec-health", "digest-refresh"):
        if args.all_ob:
            specs = _find_ob_specs()
        elif args.all:
            specs = _find_all_specs()
        elif args.spec:
            found = [s for s in _find_all_specs() if s[0].upper() == args.spec.upper()]
            if not found:
                print(f"  ✗ Spec not found: {args.spec}")
                sys.exit(1)
            specs = found
        else:
            print("  ✗ Specify a spec, --all-ob, or --all")
            sys.exit(1)
    else:
        specs = [("project", "")]

    for spec_id, spec_path in specs:
        if args.round == "spec-health":
            from rondo.rounds.spec_health import build_spec_health_round

            round_def = build_spec_health_round(spec_id, spec_path)
        elif args.round == "digest-refresh":
            from rondo.rounds.digest_refresh import build_digest_round

            round_def = build_digest_round(spec_id, spec_path)
        elif args.round == "convention-check":
            from rondo.rounds.convention_check import build_convention_round

            round_def = build_convention_round()
        elif args.round == "pr-review":
            from rondo.rounds.pr_review import build_pr_review_round

            round_def = build_pr_review_round()
        elif args.round == "test-gaps":
            from rondo.rounds.test_gaps import build_test_gap_round

            round_def = build_test_gap_round()
        elif args.round == "knowledge-mine":
            from rondo.rounds.knowledge_mine import build_knowledge_round

            round_def = build_knowledge_round()
        else:
            print(f"  ✗ Unknown round: {args.round}")
            sys.exit(1)

        dispatch_round_parallel(
            round_def,
            auth=args.auth,
            model=args.model,
            effort=args.effort,
            workers=args.workers,
            throttle_sec=args.throttle,
            spec_id=spec_id,
        )


if __name__ == "__main__":
    main()
