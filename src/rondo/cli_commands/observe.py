# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""CLI observation commands — report, history, audit, flaky, metrics.

Rondo-REQ-101, Rondo-REQ-104, Rondo-REQ-107, Rondo-STD-113.
Monitoring and analysis of dispatch results.
Import direction: cli.py → cli_commands → observe.py (one-way).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from rondo.cli_commands import EXIT_FAILURE, EXIT_SUCCESS
from rondo.flaky import DispatchOutcome, FlakyEngine
from rondo.metrics import compute_metrics


def _cmd_report(args: argparse.Namespace) -> int:
    """Execute 'rondo report <results_dir>' subcommand."""
    # -- Future: re-generate report from saved results
    print(f"Report from {args.results_dir} — not yet implemented", file=sys.stderr)
    return EXIT_FAILURE


def _resolve_task_result_path(results_dir: str, run_id: str) -> Path:
    """Resolve run id to task result JSON path under reports/rondo-results."""
    root = Path(results_dir).expanduser()
    candidate = Path(run_id)
    if candidate.suffix == ".json":
        name = candidate.name
    elif run_id.startswith("task-"):
        name = f"{run_id}.json"
    else:
        name = f"task-{run_id}.json"
    return root / name


def _load_task_result(results_dir: str, run_id: str) -> tuple[dict, Path] | tuple[None, Path]:
    """Load one task result file by run id."""
    path = _resolve_task_result_path(results_dir, run_id)
    if not path.is_file():
        return None, path
    try:
        return json.loads(path.read_text(encoding="utf-8")), path
    except (OSError, json.JSONDecodeError):
        return None, path


def _output_snippet(text: str, size: int = 120) -> str:
    """Compact one-line output preview for compare output."""
    return (text or "").strip().replace("\n", " ")[:size]


def _resolve_replay_execution(loaded: dict, model: str) -> str:
    """Best-effort execution mode reconstruction for thin replay."""
    execution = str(loaded.get("execution", "") or "")
    if execution:
        return execution
    return "" if ":" in model else "subprocess"


def _run_replay_dispatch(prompt: str, model: str, execution: str) -> dict:
    """Dispatch replay prompt through rondo_run_file."""
    from rondo.mcp_dispatch import rondo_run_file  # pylint: disable=import-outside-toplevel

    replay_raw = rondo_run_file(
        prompt=prompt,
        model=model,
        execution=execution,
        dry_run=False,
    )
    return json.loads(replay_raw)


def _build_replay_result(run_id: str, source_path: Path, loaded: dict, replay: dict, model: str, execution: str) -> dict:
    """Build normalized replay summary payload."""
    tasks = replay.get("tasks", []) or []
    first = tasks[0] if tasks else {}
    return {
        "run_id": run_id,
        "source_file": str(source_path),
        "status_before": loaded.get("status", ""),
        "status_after": replay.get("status", ""),
        "model": model,
        "execution": execution or "auto",
        "duration_before_sec": float(loaded.get("duration_sec", 0.0) or 0.0),
        "duration_after_sec": float(first.get("duration_sec", replay.get("duration_sec", 0.0)) or 0.0),
        "cost_after_usd": float(replay.get("total_cost_usd", 0.0) or 0.0),
        "output_after_snippet": _output_snippet(str(first.get("raw_output", "") or "")),
    }


def _print_replay_result(result: dict) -> None:
    """Print replay result in human-readable mode."""
    print(f"Run ID:      {result['run_id']}")
    print(f"Model:       {result['model']} ({result['execution']})")
    print(f"Status:      {result['status_before']} -> {result['status_after']}")
    print(f"Duration(s): {result['duration_before_sec']:.3f} -> {result['duration_after_sec']:.3f}")
    print(f"Cost(USD):   {result['cost_after_usd']:.6f}")
    print(f"Output:      {result['output_after_snippet']}")


def _cmd_replay(args: argparse.Namespace) -> int:
    """Replay one saved task dispatch from reports/rondo-results/task-*.json."""
    loaded, path = _load_task_result(args.results_dir, args.run_id)
    if loaded is None:
        print(f"-ERROR- Run record not found or unreadable: {path}", file=sys.stderr)
        return EXIT_FAILURE

    prompt = str(loaded.get("prompt_sent", "") or "")
    model = str(loaded.get("model", "sonnet") or "sonnet")
    if not prompt.strip():
        print("-ERROR- Run record has no prompt_sent, cannot replay exactly.", file=sys.stderr)
        return EXIT_FAILURE

    execution = _resolve_replay_execution(loaded, model)
    replay = _run_replay_dispatch(prompt=prompt, model=model, execution=execution)
    result = _build_replay_result(
        run_id=args.run_id,
        source_path=path,
        loaded=loaded,
        replay=replay,
        model=model,
        execution=execution,
    )

    if getattr(args, "json", False):
        print(json.dumps(result, indent=2))
    else:
        _print_replay_result(result)

    return EXIT_SUCCESS if result["status_after"] in ("done", "partial") else EXIT_FAILURE


def _cmd_compare(args: argparse.Namespace) -> int:
    """Compare two saved task runs side-by-side."""
    left, path_a = _load_task_result(args.results_dir, args.id_a)
    right, path_b = _load_task_result(args.results_dir, args.id_b)
    if left is None:
        print(f"-ERROR- Missing run id: {args.id_a} ({path_a})", file=sys.stderr)
        return EXIT_FAILURE
    if right is None:
        print(f"-ERROR- Missing run id: {args.id_b} ({path_b})", file=sys.stderr)
        return EXIT_FAILURE

    compare = {
        "id_a": args.id_a,
        "id_b": args.id_b,
        "status_a": left.get("status", ""),
        "status_b": right.get("status", ""),
        "duration_a_sec": float(left.get("duration_sec", 0.0) or 0.0),
        "duration_b_sec": float(right.get("duration_sec", 0.0) or 0.0),
        "cost_a_usd": float(left.get("cost_usd", left.get("usage", {}).get("cost_usd", 0.0)) or 0.0),
        "cost_b_usd": float(right.get("cost_usd", right.get("usage", {}).get("cost_usd", 0.0)) or 0.0),
        "snippet_a": _output_snippet(str(left.get("raw_output", "") or "")),
        "snippet_b": _output_snippet(str(right.get("raw_output", "") or "")),
    }

    if getattr(args, "json", False):
        print(json.dumps(compare, indent=2))
        return EXIT_SUCCESS

    print(f"{'Field':<12} | {'A':<36} | {'B':<36}")
    print(f"{'-' * 12}-+-{'-' * 36}-+-{'-' * 36}")
    print(f"{'status':<12} | {compare['status_a']:<36} | {compare['status_b']:<36}")
    print(f"{'duration_s':<12} | {compare['duration_a_sec']:<36.6f} | {compare['duration_b_sec']:<36.6f}")
    print(f"{'cost_usd':<12} | {compare['cost_a_usd']:<36.6f} | {compare['cost_b_usd']:<36.6f}")
    print(f"{'output':<12} | {compare['snippet_a']:<36} | {compare['snippet_b']:<36}")
    return EXIT_SUCCESS


def _cmd_history(args: argparse.Namespace) -> int:  # pylint: disable=too-many-return-statements
    """Execute 'rondo history' — show dispatch history.

    Rondo-REQ-104 req 005.
    """
    from rondo.history import load_history, query_history  # pylint: disable=import-outside-toplevel

    history_dir = str(Path(args.results_dir) / "history")
    records = load_history(history_dir)
    filtered = query_history(records, model=args.model, status=args.status)

    if args.json:
        print(json.dumps(filtered, indent=2, default=str))
    elif not filtered:
        print("  No dispatch history found.")
    else:
        total_cost = sum(r.get("cost_usd", 0) for r in filtered)
        print(f"  Dispatches: {len(filtered)} | Total cost: ${total_cost:.4f}")

        # -- REQ-104 req 003: per-model summary
        from rondo.history import aggregate_by_model  # pylint: disable=import-outside-toplevel

        agg = aggregate_by_model(filtered)
        if len(agg) > 1:
            print(
                "  Models:",
                " | ".join(f"{m}: {d['count']} dispatches, ${d['total_cost']:.4f}" for m, d in sorted(agg.items())),
            )
        print()
        # -- REQ-104 req 007: --expensive sorts by cost (top 10)
        is_expensive = getattr(args, "expensive", False)
        if is_expensive:
            filtered = sorted(filtered, key=lambda r: r.get("cost_usd", 0), reverse=True)
        display = filtered[:10] if is_expensive else filtered[-10:]
        for r in display:
            cost = r.get("cost_usd", 0)
            print(
                f"  {r.get('status', '?'):8s} {r.get('task_name', '?'):30s} "
                f"{r.get('model', '?'):8s} ${cost:.4f} {r.get('duration_sec', 0):.1f}s"
            )

    return EXIT_SUCCESS


def _load_audit_records(audit_dir: str) -> list[dict]:
    """Load all records from audit JSONL — STD-113."""
    jsonl_file = Path(audit_dir).expanduser() / "rondo_audit.jsonl"
    if not jsonl_file.exists():
        return []
    records = []
    for line in jsonl_file.read_text(encoding="utf-8").strip().split("\n"):
        if line.strip():
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def _cmd_audit(args: argparse.Namespace) -> int:  # pylint: disable=too-many-return-statements
    """Query dispatch audit trail — STD-113 reqs 011-013.

    Always-on: every dispatch records audit data. This command reads it.
    Callers (ACE, OB, Caliber) get dispatch_id in TaskResult automatically.
    """
    from rondo.audit import AuditConfig, AuditTrail  # pylint: disable=import-outside-toplevel

    # -- Rotate: rondo audit --rotate (RONDO-29)
    if getattr(args, "rotate", False):
        trail = AuditTrail(config=AuditConfig(audit_dir=args.audit_dir))
        count = trail.rotate()
        if count:
            print(f"Rotated {count} audit records to archive/")
        else:
            print("Nothing to rotate.")
        return EXIT_SUCCESS

    # -- Reset: rondo audit --reset (RONDO-29)
    if getattr(args, "reset", False):
        trail = AuditTrail(config=AuditConfig(audit_dir=args.audit_dir))
        count = trail.reset()
        if count:
            print(f"Cleared {count} audit files.")
        else:
            print("Nothing to clear.")
        return EXIT_SUCCESS

    records = _load_audit_records(args.audit_dir)
    if not records:
        print("No audit data yet. Run a dispatch first.")
        return EXIT_SUCCESS

    # -- Detail view: rondo audit <dispatch_id>
    if args.dispatch_id:
        return _cmd_audit_detail(args, records)
    # -- Cost summary: rondo audit --cost
    if args.cost:
        return _cmd_audit_cost(args, records)
    # -- Failed only: rondo audit --failed
    if args.failed:
        return _cmd_audit_failed(args, records)
    # -- Default: list all
    return _cmd_audit_list(args, records)


def _cmd_audit_detail(args: argparse.Namespace, records: list[dict]) -> int:
    """Show detail for one dispatch_id."""
    matches = [r for r in records if r.get("dispatch_id") == args.dispatch_id]
    if not matches:
        print(f"No records for dispatch_id: {args.dispatch_id}")
        return EXIT_FAILURE
    if args.json:
        print(json.dumps(matches, indent=2))
    else:
        for r in matches:
            print(
                f"  {r.get('status', '?'):8s} | {r.get('task_name', '?')} | {r.get('dispatched_at', r.get('completed_at', ''))}"
            )
            if r.get("cost_usd"):
                print(f"           cost: ${r['cost_usd']:.4f} | duration: {r.get('duration_sec', 0):.1f}s")
    audit_dir = Path(args.audit_dir).expanduser()
    for ext in [".prompt.txt", ".result.json"]:
        fpath = audit_dir / f"{args.dispatch_id}{ext}"
        if fpath.exists():
            print(f"  {'Prompt' if 'prompt' in ext else 'Result'}: {fpath}")
    return EXIT_SUCCESS


def _cmd_audit_cost(args: argparse.Namespace, records: list[dict]) -> int:
    """Show total cost summary."""
    outcomes = [r for r in records if r.get("cost_usd")]
    total_cost = sum(r.get("cost_usd", 0) for r in outcomes)
    if args.json:
        print(json.dumps({"total_cost_usd": total_cost, "dispatch_count": len(outcomes)}))
    else:
        print(f"  Total cost: ${total_cost:.4f}")
        print(f"  Dispatches: {len(outcomes)}")
        if outcomes:
            print(f"  Average:    ${total_cost / len(outcomes):.4f}/dispatch")
    return EXIT_SUCCESS


def _cmd_audit_failed(args: argparse.Namespace, records: list[dict]) -> int:
    """Show only failed dispatches."""
    failed = [r for r in records if r.get("status") in ("error", "blocked", "timeout")]
    if args.json:
        print(json.dumps(failed, indent=2))
    elif not failed:
        print("  No failed dispatches.")
    else:
        print(f"  Failed Dispatches ({len(failed)}):")
        for r in failed:
            print(f"    {r.get('dispatch_id', '?')[:12]} | {r.get('task_name', '?')} | {r.get('status', '?')}")
    return EXIT_SUCCESS


def _cmd_audit_list(args: argparse.Namespace, records: list[dict]) -> int:
    """Default: list all audit records with summary."""
    if args.json:
        print(json.dumps(records, indent=2))
        return EXIT_SUCCESS
    intents = [r for r in records if r.get("status") == "INTENT"]
    outcomes = [r for r in records if r.get("status") != "INTENT"]
    total_cost = sum(r.get("cost_usd", 0) for r in outcomes)
    print(f"  Audit Trail: {len(records)} records ({len(intents)} intents, {len(outcomes)} outcomes)")
    print(f"  Total cost:  ${total_cost:.4f}")
    print()
    recent = sorted(outcomes, key=lambda r: r.get("completed_at", ""))[-10:]
    if recent:
        print("  Recent dispatches:")
        for r in recent:
            did = r.get("dispatch_id", "?")[:12]
            print(f"    {did} | {r.get('status', '?'):8s} | ${r.get('cost_usd', 0):.4f} | {r.get('task_name', '?')}")
    return EXIT_SUCCESS


def _cmd_flaky(args: argparse.Namespace) -> int:
    """Show flaky task templates — REQ-107 reqs 007-008.

    Reads audit trail, feeds into FlakyEngine, reports flip rates.
    """
    audit_dir = Path(args.audit_dir).expanduser()
    jsonl_file = audit_dir / "rondo_audit.jsonl"

    if not jsonl_file.exists():
        print("No audit data yet. Run dispatches first to build history.")
        return EXIT_SUCCESS

    # -- Load outcomes from audit trail
    engine = FlakyEngine()
    for line in jsonl_file.read_text(encoding="utf-8").strip().split("\n"):
        if not line.strip():
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        # -- Only outcomes (not INTENTs)
        if r.get("status") == "INTENT":
            continue
        if not r.get("task_name"):
            continue
        engine.add_outcome(
            DispatchOutcome(
                task_name=r.get("task_name", ""),
                prompt_hash=r.get("prompt_hash", "unknown"),
                model=r.get("model", "unknown"),
                status=r.get("status", "unknown"),
                confidence=0.0,
                run_at=r.get("completed_at", r.get("dispatched_at", "")),
            )
        )

    flaky_tasks = engine.get_flaky_tasks(threshold=args.threshold)

    if args.json:
        print(json.dumps([f.to_dict() for f in flaky_tasks], indent=2))
        return EXIT_SUCCESS

    if not flaky_tasks:
        print(f"  No flaky tasks (threshold: {args.threshold:.0%})")
        stats = engine.get_model_stats()
        if stats:
            print("\n  Model reliability:")
            for model, data in sorted(stats.items()):
                print(f"    {model}: {data['total_runs']} runs, {data['flakiness']:.0%} flip rate")
        return EXIT_SUCCESS

    print(f"  Flaky Tasks ({len(flaky_tasks)}, threshold: {args.threshold:.0%}):")
    for f in flaky_tasks:
        print(f"    {f.task_name}: {f.flakiness_score:.0%} flaky ({f.flip_count} flips / {f.total_runs} runs)")
    return EXIT_SUCCESS


def _cmd_metrics(args: argparse.Namespace) -> int:
    """Dispatch metrics for OB dashboards — one call, everything.

    ALWAYS-ON: reads existing audit data, no new capture needed.
    Designed for OB dashboard, ACE health, and future MCP (IFS-104).
    """
    report = compute_metrics(audit_dir=args.audit_dir)

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
        return EXIT_SUCCESS

    print("  Rondo Metrics")
    print(f"  {'─' * 45}")
    print(f"  Health:       {report.health}")
    print(f"  Dispatches:   {report.total_dispatches}")
    print(f"  Success rate: {report.success_rate:.0%}")
    print(f"  Total cost:   ${report.total_cost_usd:.4f}")
    print(f"  Avg cost:     ${report.avg_cost_usd:.4f}")
    print(f"  Avg duration: {report.avg_duration_sec:.1f}s")
    print(f"  Max duration: {report.max_duration_sec:.1f}s")
    print(f"  Tokens:       {report.total_input_tokens:,} in / {report.total_output_tokens:,} out")
    print(f"  Spool:        {report.spool_pending} pending")
    if report.dispatches_by_model:
        print("\n  Models:")
        for model, count in sorted(report.dispatches_by_model.items()):
            cost = report.cost_by_model.get(model, 0)
            print(f"    {model:12s}  {count:3d} dispatches  ${cost:.4f}")
    if report.error_breakdown:
        print("\n  Errors:")
        for code, count in sorted(report.error_breakdown.items(), key=lambda x: -x[1]):
            print(f"    {code:20s}  {count}")
    return EXIT_SUCCESS


def _cmd_learn(args: argparse.Namespace) -> int:
    """Compute provider scores from dispatch history — REQ-111 req 442."""
    from rondo.scoring import compute_provider_scores, save_scores_cache  # pylint: disable=import-outside-toplevel

    audit_dir = getattr(args, "audit_dir", "") or ""
    scores = compute_provider_scores(audit_dir)

    if not scores:
        print("  No provider scores available (need 10+ dispatches per provider).")
        return EXIT_SUCCESS

    save_scores_cache(scores)

    if getattr(args, "json", False):
        print(json.dumps(scores, indent=2))
    else:
        print(f"\n  Provider Scores ({len(scores)} providers)")
        print(
            f"  {'Provider':<20}  {'Success':>7}  {'Avg Cost':>9}  {'Avg Lat':>8}  {'JSON OK':>7}  {'Score':>6}  {'N':>5}"
        )
        print(f"  {'─' * 20}  {'─' * 7}  {'─' * 9}  {'─' * 8}  {'─' * 7}  {'─' * 6}  {'─' * 5}")
        for name, s in sorted(scores.items(), key=lambda x: x[1].get("score", 0), reverse=True):
            json_ok = f"{s['json_success_rate']:.0%}" if s.get("json_success_rate") is not None else "—"
            print(
                f"  {name:<20}  {s['success_rate']:>6.0%}  ${s['avg_cost_usd']:>7.4f}  {s['avg_latency_sec']:>6.1f}s  {json_ok:>7}  {s['score']:>5.3f}  {s['sample_count']:>5}"
            )
        print()

    return EXIT_SUCCESS


# -- sig: mgh-6201.cd.bd955f.a3d4.9136a5
