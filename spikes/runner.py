#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Mark G. Hubers / HubersTech
# SPDX-License-Identifier: LicenseRef-Proprietary
"""Rondo Runner — dispatch a full round end-to-end.

Runs all tasks in a round sequentially (parallel coming in Level 3),
collects results, generates summary. This is the overnight workhorse.

Usage:
   python3 -m rondo.runner spec-health OB-REQ-026
   python3 -m rondo.runner spec-health --all-ob
   python3 -m rondo.runner digest-refresh --all
   python3 -m rondo.runner build-check
   python3 -m rondo.runner convention-check

Created: 2026-03-13 (Session 75)
Author: Mark Hubers — HubersTech
"""

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from rondo.dispatch import RESULTS_DIR, dispatch_task  # noqa: E402
from rondo.engine import TaskMode  # noqa: E402

## -- Results go in round-specific subdirs
ROUND_RESULTS_DIR = RESULTS_DIR / "rounds"
ROUND_RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def _now_stamp() -> str:
    """Filename-safe timestamp."""
    return datetime.now(UTC).strftime("%Y%m%d-%H%M%S")


def run_full_round(
    round_def: object,
    auth: str = "max",
    model: str | None = None,
    effort: str | None = None,
    dry_run: bool = False,
    spec_id: str = "",
    spec_path: str = "",
) -> dict:
    """Run all tasks in a round, collect results.

    Args:
       round_def: A Round object from rondo.engine
       auth: Auth mode
       model: Model override (None = task decides)
       effort: Effort override (None = task decides)
       dry_run: Show prompts without dispatching
       spec_id: Spec being checked (for result labeling)
       spec_path: Full path to spec file (for pre-gate checks)

    Returns:
       Dict with: spec_id, round_name, tasks (list of results), summary
    """
    round_name = round_def.name
    tasks = round_def.tasks
    interactive_tasks = [t for t in tasks if t.mode == TaskMode.INTERACTIVE]

    print(f"\n  {'═' * 60}")
    print(f"  RONDO ROUND: {round_name}")
    if spec_id:
        print(f"  Spec: {spec_id}")
    print(f"  Tasks: {len(interactive_tasks)} interactive, {len(tasks) - len(interactive_tasks)} auto")
    auth_label = "Max plan" if auth == "max" else "API key"
    model_label = model or "per-task"
    print(f"  Auth: {auth_label}  Model: {model_label}")
    print(f"  {'═' * 60}")

    ## -- Run pre-gates
    pre_ok = True
    for gate in round_def.pre_gates:
        passed = gate.check(spec_path=spec_path or spec_id)
        status = "✓" if passed else "✗"
        print(f"  {status} Pre-gate: {gate.name} — {gate.evidence}")
        if not passed and gate.blocking:
            pre_ok = False

    if not pre_ok:
        print("  ✗ Pre-gates FAILED — round blocked")
        return {"spec_id": spec_id, "round_name": round_name, "status": "blocked", "tasks": []}

    ## -- Dispatch interactive tasks
    results = []
    for i, task in enumerate(interactive_tasks, 1):
        print()
        result = dispatch_task(
            task,
            task_num=i,
            dry_run=dry_run,
            auth=auth,
            model=model,
            effort=effort,
        )
        results.append(result)

    ## -- Summary
    done_count = sum(1 for r in results if r.get("status") == "done")
    blocked_count = sum(1 for r in results if r.get("status") == "blocked")
    error_count = sum(1 for r in results if r.get("status") == "error")
    total_time = sum(r.get("duration_sec", 0) for r in results)

    summary = {
        "spec_id": spec_id,
        "round_name": round_name,
        "status": "complete" if error_count == 0 else "partial",
        "tasks_done": done_count,
        "tasks_blocked": blocked_count,
        "tasks_error": error_count,
        "total_duration_sec": total_time,
        "timestamp": datetime.now(UTC).isoformat(),
        "tasks": results,
    }

    ## -- Save round result
    if not dry_run:
        safe_spec = spec_id.replace("/", "-").replace(" ", "-") if spec_id else "unknown"
        result_path = ROUND_RESULTS_DIR / f"{round_name}-{safe_spec}-{_now_stamp()}.json"
        result_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
        print(f"\n  Round result: {result_path}")

    print(f"\n  {'═' * 60}")
    print(f"  ROUND SUMMARY: {round_name} on {spec_id}")
    print(f"  {'─' * 50}")
    print(f"  ✓ Done: {done_count}  ⏳ Blocked: {blocked_count}  ✗ Error: {error_count}")
    print(f"  Total time: {total_time:.0f}s ({total_time / 60:.1f}m)")
    print(f"  {'═' * 60}\n")

    return summary


def _find_ob_specs() -> list[tuple[str, str]]:
    """Find all OB spec files. Returns list of (spec_id, path) tuples."""
    spec_dir = Path(_PROJECT_ROOT) / "ace" / "orbital" / "specs"
    specs = []
    for f in sorted(spec_dir.glob("OB-*.md")):
        ## -- Extract spec ID from filename: OB-REQ-001-orbital-database.md → OB-REQ-001
        name = f.stem
        parts = name.split("-")
        if len(parts) >= 2:
            spec_id = f"{parts[0]}-{parts[1]}"
            specs.append((spec_id, str(f)))
    return specs


def _find_all_specs() -> list[tuple[str, str]]:
    """Find all spec files (R, F, OB). Returns list of (spec_id, path) tuples."""
    specs = []

    ## -- R specs
    r_dir = Path(_PROJECT_ROOT) / "ace" / "specs"
    for f in sorted(r_dir.glob("R[0-9]*.md")):
        name = f.stem
        spec_id = name.split("-")[0]
        specs.append((spec_id, str(f)))

    ## -- F specs
    for f in sorted(r_dir.glob("F[0-9]*.md")):
        name = f.stem
        spec_id = name.split("-")[0]
        specs.append((spec_id, str(f)))

    ## -- OB specs
    specs.extend(_find_ob_specs())

    return specs


def main() -> None:
    """CLI: run a named round."""
    parser = argparse.ArgumentParser(
        description="Rondo Runner — dispatch a full round",
    )
    parser.add_argument(
        "round",
        choices=[
            "spec-health",
            "digest-refresh",
            "build-check",
            "convention-check",
            "sprint-close",
            "knowledge-mine",
            "pr-review",
            "test-gaps",
        ],
        help="Round to run",
    )
    parser.add_argument("spec", nargs="?", default=None, help="Spec ID (e.g., OB-REQ-026) — for spec-specific rounds")
    parser.add_argument("--all-ob", action="store_true", help="Run on ALL OB specs")
    parser.add_argument("--all", action="store_true", help="Run on ALL specs (R+F+OB)")
    parser.add_argument("--auth", choices=["max", "api"], default="max")
    parser.add_argument("--model", choices=["opus", "sonnet", "haiku"], default=None)
    parser.add_argument("--effort", choices=["low", "medium", "high", "max"], default=None)
    parser.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()

    ## -- Determine which specs to run on
    if args.round in ("spec-health", "digest-refresh"):
        if args.all_ob:
            specs = _find_ob_specs()
        elif args.all:
            specs = _find_all_specs()
        elif args.spec:
            ## -- Find the spec file
            spec_id = args.spec
            found = [s for s in _find_all_specs() if s[0].upper() == spec_id.upper()]
            if not found:
                print(f"  ✗ Spec not found: {spec_id}")
                sys.exit(1)
            specs = found
        else:
            print("  ✗ Specify a spec ID, --all-ob, or --all")
            sys.exit(1)
    else:
        specs = [("project", "")]

    ## -- Build and run rounds
    all_summaries = []
    for spec_id, spec_path in specs:
        if args.round == "spec-health":
            from rondo.rounds.spec_health import build_spec_health_round

            round_def = build_spec_health_round(spec_id, spec_path)
        elif args.round == "digest-refresh":
            from rondo.rounds.digest_refresh import build_digest_round

            round_def = build_digest_round(spec_id, spec_path)
        elif args.round == "build-check":
            from rondo.rounds.build_check import build_check_round

            round_def = build_check_round()
        elif args.round == "convention-check":
            from rondo.rounds.convention_check import build_convention_round

            round_def = build_convention_round()
        elif args.round == "sprint-close":
            from rondo.rounds.sprint_close import build_sprint_close_round

            round_def = build_sprint_close_round()
        elif args.round == "knowledge-mine":
            from rondo.rounds.knowledge_mine import build_knowledge_round

            round_def = build_knowledge_round()
        elif args.round == "pr-review":
            from rondo.rounds.pr_review import build_pr_review_round

            round_def = build_pr_review_round()
        elif args.round == "test-gaps":
            from rondo.rounds.test_gaps import build_test_gap_round

            round_def = build_test_gap_round()
        else:
            print(f"  ✗ Unknown round: {args.round}")
            sys.exit(1)

        summary = run_full_round(
            round_def,
            auth=args.auth,
            model=args.model,
            effort=args.effort,
            dry_run=args.dry_run,
            spec_id=spec_id,
            spec_path=spec_path,
        )
        all_summaries.append(summary)

    ## -- Batch summary
    if len(all_summaries) > 1:
        print(f"\n  {'═' * 60}")
        print(f"  BATCH SUMMARY: {args.round} on {len(all_summaries)} specs")
        print(f"  {'─' * 50}")
        for s in all_summaries:
            status_icon = "✓" if s["status"] == "complete" else "⏳" if s["status"] == "blocked" else "✗"
            print(
                f"  {status_icon} {s['spec_id']}: {s['tasks_done']} done, {s['tasks_blocked']} blocked, {s['tasks_error']} error ({s['total_duration_sec']:.0f}s)"
            )
        total = sum(s["total_duration_sec"] for s in all_summaries)
        print(f"  {'─' * 50}")
        print(f"  Total: {total:.0f}s ({total / 60:.1f}m)")
        print(f"  {'═' * 60}\n")


if __name__ == "__main__":
    main()
