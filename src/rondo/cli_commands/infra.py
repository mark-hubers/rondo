# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""CLI infrastructure commands — preflight, spool, mcp, init, schedule, providers.

Rondo-REQ-101, Rondo-REQ-103, Rondo-REQ-109, Rondo-IFS-104.
Setup, configuration, and infrastructure management.
Import direction: cli.py → cli_commands → infra.py (one-way).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from rondo.cli_commands import EXIT_FAILURE, EXIT_SUCCESS
from rondo.spool import SpoolConfig, SpoolManager


def _cmd_preflight(args: argparse.Namespace) -> int:
    """Execute 'rondo preflight' — check environment without dispatching.

    Rondo-REQ-103 reqs 015-016: standalone preflight + JSON output.
    """
    from rondo.preflight import run_preflight  # pylint: disable=import-outside-toplevel

    result = run_preflight()

    # -- REQ-103 req 016: JSON output
    if getattr(args, "json", False):
        print(
            json.dumps(
                {
                    "status": result.status,
                    "can_proceed": result.can_proceed,
                    "checks": result.checks,
                    "warnings": result.warnings,
                    "errors": result.errors,
                },
                indent=2,
            )
        )
        return EXIT_SUCCESS if result.can_proceed else EXIT_FAILURE

    # -- Human-readable output
    for check in result.checks:
        print(f"  -PASS- {check}")
    for warn in result.warnings:
        print(f"  -WARNING- {warn}")
    for err in result.errors:
        print(f"  -ERROR- {err}", file=sys.stderr)

    if result.status == "GREEN":
        print(f"\n  Preflight: {result.status} — ready to dispatch")
    elif result.status == "YELLOW":
        print(f"\n  Preflight: {result.status} — proceed with caution")
    else:
        print(f"\n  Preflight: {result.status} — cannot dispatch", file=sys.stderr)

    return EXIT_SUCCESS if result.can_proceed else EXIT_FAILURE


def _cmd_spool(args: argparse.Namespace) -> int:  # pylint: disable=too-many-branches
    """Manage result spool — REQ-101 reqs 047-049."""
    spool = SpoolManager(config=SpoolConfig(spool_dir=args.spool_dir))

    if args.action == "list":
        entries = spool.list_pending()
        if args.json:
            print(json.dumps(entries, indent=2))
        elif not entries:
            print("  Spool empty.")
        else:
            print(f"  Pending Results ({len(entries)}):")
            for e in entries:
                age_h = e["age_sec"] / 3600
                print(f"    {e['filename']:50s} {e['size_bytes']:6d}B  {age_h:.1f}h old")
        return EXIT_SUCCESS

    if args.action == "clean":
        if getattr(args, "all", False):
            removed = spool.clean_all()
        else:
            removed = spool.clean_expired()
        print(f"  Cleaned {removed} file(s).")
        return EXIT_SUCCESS

    if args.action == "export":
        since = args.since or "2000-01-01"
        exported = spool.export_since(since)
        print(json.dumps(exported, indent=2))
        return EXIT_SUCCESS

    if args.action == "consume":
        consumed = spool.consume_all()
        if args.json:
            print(json.dumps(consumed, indent=2))
        elif not consumed:
            print("  No results to consume.")
        else:
            print(f"  Consumed {len(consumed)} result(s):")
            for c in consumed:
                status = c.get("status", "?")
                name = c.get("task_name", c.get("_spool_file", "?"))
                print(f"    {status:8s} | {name}")
        return EXIT_SUCCESS

    return EXIT_SUCCESS


def _cmd_mcp(_args: argparse.Namespace) -> int:
    """Start MCP stdio server — IFS-104.

    Claude Code spawns this, talks via stdin/stdout.
    No daemon, no port, just stdio.
    """
    from rondo.mcp_server import run_mcp  # pylint: disable=import-outside-toplevel

    run_mcp()
    return EXIT_SUCCESS


def _cmd_version(args: argparse.Namespace) -> int:
    """Show version or bump build counter — RONDO-290 (Finding #266).

    Without --bump: prints current version (MAJOR.MINOR.PATCH+YYYYMMDD.BUILD).
    With --bump:    increments build counter, prints NEW version.

    Intended callers:
        - User: `rondo version` for quick version check
        - ace-sprint done post-hook: `rondo version --bump` after each sprint close
        - CI: `rondo version --bump` after successful build
    """
    from rondo._version import bump_build, get_version  # pylint: disable=import-outside-toplevel

    if getattr(args, "bump", False):
        new_version = bump_build()
        sys.stdout.write(new_version + "\n")
    else:
        sys.stdout.write(get_version() + "\n")
    return EXIT_SUCCESS


def _cmd_init(args: argparse.Namespace) -> int:
    """Create a starter round file or config — U-10 to U-14."""
    # -- rondo init --config: create ~/.rondo/config.toml from template
    if getattr(args, "config", False):
        config_dir = Path.home() / ".rondo"
        config_path = config_dir / "config.toml"
        if config_path.exists():
            print(f"Config already exists: {config_path}", file=sys.stderr)
            print("  Edit it directly, or remove it first to regenerate.", file=sys.stderr)
            return EXIT_FAILURE
        config_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        # -- RONDO-304 (Finding #289): template ships INSIDE the package so
        # -- INSTALLED deployments work (__file__-walking only worked from a
        # -- repo checkout — site-packages has no examples/). Package data
        # -- first, repo examples/ as fallback for editable checkouts.
        template_text = ""
        try:
            from importlib.resources import files  # pylint: disable=import-outside-toplevel

            template_text = (files("rondo") / "data" / "config-template.toml").read_text(encoding="utf-8")
        except (FileNotFoundError, ModuleNotFoundError, OSError):
            repo_template = Path(__file__).parent.parent.parent.parent / "examples" / "config.toml"
            if repo_template.exists():
                template_text = repo_template.read_text(encoding="utf-8")
        if not template_text:
            print("Error: config template not found (package data or examples/)", file=sys.stderr)
            return EXIT_FAILURE
        config_path.write_text(template_text, encoding="utf-8")
        config_path.chmod(0o600)  # -- STD-110 S5: restrictive permissions
        print(f"Created {config_path}")
        print("  Edit provider settings, then validate: pytest -m cloud_full -v -s")
        return EXIT_SUCCESS

    name = getattr(args, "name", "my-round")
    output_path = Path.cwd() / "round.py"

    # -- U-14: refuse to overwrite
    if output_path.exists():
        print(f"Error: {output_path} already exists. Remove it first.", file=sys.stderr)
        return EXIT_FAILURE

    # -- U-13: generate with comments explaining each field
    task_name = name.replace(" ", "-").lower()
    content = f'''"""Rondo round file: {name}

Usage:
    rondo run round.py --dry-run      # preview without running
    rondo run round.py                # execute with default model
    rondo run round.py --model haiku  # use cheaper model
"""

from rondo.engine import Round, Task

def build_round() -> Round:
    """Define the tasks for this round.

    Each Task has three fields (the contract):
        instruction  — what Claude should do (the "Do")
        context_files — files Claude should read (the "Read")
        done_when    — how to know it's complete (the "Done")
    """
    return Round(
        name="{name}",
        tasks=[
            Task(
                name="{task_name}-task-1",
                description="First task — edit this",
                instruction="""Review the code and report findings.

1. Check for bugs
2. Check for security issues
3. Suggest improvements""",
                context_files=[],  # -- add file paths here
                done_when="All findings reported as a numbered list.",
            ),
        ],
    )
'''

    output_path.write_text(content, encoding="utf-8")
    print(f"Created {output_path}")
    print("  Next: rondo run round.py --dry-run")
    return EXIT_SUCCESS


def _cmd_schedule(args: argparse.Namespace) -> int:
    """Create a launchd plist for recurring Rondo dispatch (round file or --cmd)."""
    from rondo.schedule import generate_plist  # pylint: disable=import-outside-toplevel

    sub_cmd = getattr(args, "cmd", "") or ""
    if sub_cmd:
        # -- RONDO-314: schedule a rondo subcommand (e.g. the nightly watchdog)
        name = args.name or sub_cmd
        cmd_args = [sub_cmd]
        work_dir = str(Path.home())
    elif args.file:
        file_path = str(Path(args.file).resolve())
        name = args.name or Path(args.file).stem
        cmd_args = ["run", file_path]
        work_dir = str(Path(file_path).parent)
    else:
        print("-ERROR- schedule needs a round file or --cmd <subcommand>")
        return EXIT_FAILURE
    if args.model:
        cmd_args.extend(["--model", args.model])

    plist = generate_plist(
        name=name,
        command=__import__("shutil").which("rondo") or "rondo",  # -- RONDO-216 C5: was hardcoded path
        args=cmd_args,
        interval=args.interval,
        work_dir=work_dir,
    )

    if getattr(args, "install", False):
        out_dir = Path.home() / "Library" / "LaunchAgents"
        out_path = out_dir / f"com.rondo.{name}.plist"
        out_path.write_text(plist, encoding="utf-8")
        print(f"Installed: {out_path}")
        print(f"  Load: launchctl load {out_path}")
    else:
        print(plist)
        print(f"\n# Install with: rondo schedule {args.file} --install")

    return EXIT_SUCCESS


def _cmd_doctor(args: argparse.Namespace) -> int:
    """Execute 'rondo doctor' — RONDO-320 (REQ-103 reqs 030-036).

    Install diagnosis, zero dispatches. Exit 0 = healthy, 1 = any FAIL.
    --bundle writes ONE redacted support file for issue reports.
    """
    import json as _json  # pylint: disable=import-outside-toplevel

    from rondo.doctor import (  # pylint: disable=import-outside-toplevel
        build_support_bundle,
        doctor_exit_code,
        format_doctor_table,
        run_doctor,
    )

    rows = run_doctor()
    if getattr(args, "json", False):
        print(_json.dumps([r.to_dict() for r in rows], indent=2))
    else:
        print("Rondo doctor — install diagnosis (no dispatches, no cost):")
        print(format_doctor_table(rows))

    if getattr(args, "bundle", False):
        try:
            bundle = build_support_bundle(rows)
        except ValueError as exc:
            print(f"-ERROR- {exc}", file=sys.stderr)
            return EXIT_FAILURE
        out_path = Path.home() / ".rondo" / "support-bundle.txt"
        out_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        out_path.write_text(bundle, encoding="utf-8")
        out_path.chmod(0o600)
        print(f"-PASS- redacted support bundle written: {out_path}")

    return doctor_exit_code(rows)


def _cmd_models(args: argparse.Namespace) -> int:
    """Execute 'rondo models' — RONDO-316 (REQ-111 reqs 604-610).

    --tiers      : derived auto_low/mid/high per provider (free, registry cache)
    --verify     : live canary per configured tier model (~cents; req 604)
    --docs-drift : stale model IDs in examples/ + docs/ (free; req 611, RONDO-325)
    """
    import json as _json  # pylint: disable=import-outside-toplevel

    from rondo.config import get_rondo_config  # pylint: disable=import-outside-toplevel
    from rondo.model_registry import (  # pylint: disable=import-outside-toplevel
        derive_auto_tiers,
        docs_drift,
        format_verify_table,
        load_cache,
        verify_models,
    )

    providers_cfg = get_rondo_config().get("providers", {})

    if getattr(args, "verify", False):
        rows = verify_models(providers_cfg)
        if getattr(args, "json", False):
            print(_json.dumps(rows, indent=2))
        else:
            print("Model canary — every configured tier, one tiny live dispatch each (req 604):")
            print(format_verify_table(rows))
        return EXIT_FAILURE if any(r["result"] == "FAIL" for r in rows) else EXIT_SUCCESS

    if getattr(args, "tiers", False):
        cache = load_cache()
        if cache is None:
            print("-WARNING- no registry cache yet — run: rondo providers --refresh", file=sys.stderr)
            return EXIT_FAILURE
        tiers = derive_auto_tiers(cache, providers_cfg)
        if getattr(args, "json", False):
            print(_json.dumps(tiers, indent=2))
        else:
            print("Derived auto-tiers (suggest mode — NEVER written to config; reqs 605/607-609):")
            for provider, t in sorted(tiers.items()):
                print(f"  {provider:<11} low={t['auto_low']}  mid={t['auto_mid']}  high={t['auto_high']}")
        return EXIT_SUCCESS

    if getattr(args, "docs_drift", False):
        cache = load_cache()
        if cache is None:
            print("-WARNING- no registry cache yet — run: rondo providers --refresh", file=sys.stderr)
            return EXIT_FAILURE
        # -- req 611: examples ARE the docs — scan both trees when present
        roots = [d for d in ("examples", "docs") if Path(d).is_dir()]
        hits = docs_drift(cache, roots)
        if getattr(args, "json", False):
            print(_json.dumps(hits, indent=2))
        elif not hits:
            print("  -PASS- docs drift: no stale model IDs in examples/ or docs/ (req 611)")
        else:
            print(f"  -WARNING- {len(hits)} stale model reference(s) — stale docs teach dead dispatches:")
            for h in hits:
                print(f"    {h['file']}:{h['line']}  {h['model']} ({h['provider']}) no longer served")
            print("  Fix by hand (detection-only — Rondo never edits docs); history lines are skipped.")
        return EXIT_FAILURE if hits else EXIT_SUCCESS

    print("Usage: rondo models --tiers (free) | --verify (live canary, ~cents) | --docs-drift (free) [--json]")
    return EXIT_SUCCESS


def _cmd_nightly(args: argparse.Namespace) -> int:
    """Execute 'rondo nightly' — RONDO-314 watchdog sweep (finding #285).

    Exit code contract: 0 = all green, 1 = at least one alert.
    """
    import json as _json  # pylint: disable=import-outside-toplevel

    from rondo.nightly import run_nightly_check  # pylint: disable=import-outside-toplevel

    report = run_nightly_check(
        refresh=not getattr(args, "no_refresh", False),
        notify_alerts=not getattr(args, "no_notify", False),
    )

    if getattr(args, "json", False):
        print(_json.dumps(report.to_dict(), indent=2))
        return EXIT_SUCCESS if report.status == "OK" else EXIT_FAILURE

    print(f"Rondo nightly watchdog — {report.status}")
    stale = [d for d in report.drift if d.get("state") in ("STALE", "NO_CACHE")]
    print(f"  drift:       {len(report.drift)} models checked, {len(stale)} stale")
    print(
        f"  retryq:      {report.retry_sweep.get('dead_lettered', 0)} dead-lettered, "
        f"{report.retry_sweep.get('remaining', 0)} remaining"
    )
    rate = report.success_rate_7d
    rate_str = f"{rate:.0%}" if rate is not None else "n/a (no dispatches)"
    print(f"  reliability: {rate_str} over 7d ({report.dispatches_7d} dispatches)")
    if report.alerts:
        for alert in report.alerts:
            print(f"  -WARNING- {alert}")
        return EXIT_FAILURE
    print("  -PASS- fleet healthy")
    return EXIT_SUCCESS


def _providers_registry_action(args: argparse.Namespace) -> int:
    """--refresh / --drift: the registry that caught dead grok-3 (RONDO-305).

    Extracted from _cmd_providers (RONDO-322 complexity lock).
    """
    from rondo.adapters.auth import load_api_key  # pylint: disable=import-outside-toplevel
    from rondo.config import get_rondo_config  # pylint: disable=import-outside-toplevel
    from rondo.model_registry import (  # pylint: disable=import-outside-toplevel
        drift_report,
        format_drift_table,
        load_cache,
        refresh_registry,
    )

    providers_cfg = get_rondo_config().get("providers", {})
    if getattr(args, "refresh", False):
        cache = refresh_registry(providers_cfg, key_loader=load_api_key)
        ok = sum(1 for v in cache["providers"].values() if not v["error"])
        print(f"  -PASS- registry refreshed: {ok}/{len(cache['providers'])} providers cached")
    else:
        cache = load_cache()
        if cache is None:
            print("  -WARNING- no registry cache yet — run: rondo providers --refresh", file=sys.stderr)
            return EXIT_FAILURE
    if getattr(args, "drift", False):
        print(format_drift_table(drift_report(cache, providers_cfg)))
    return EXIT_SUCCESS


def _cmd_providers(args: argparse.Namespace) -> int:
    """Show providers: health (REQ-109 req 020), registry drift (REQ-111 600-603)."""
    if getattr(args, "refresh", False) or getattr(args, "drift", False):
        return _providers_registry_action(args)

    # -- RONDO-306 (REQ-109 req 313): --scores was a DEAD FLAG — parsed, never
    # -- handled. Now shows the learned 7-day per-model score breakdown.
    if getattr(args, "scores", False):
        from rondo.scoring import compute_provider_scores  # pylint: disable=import-outside-toplevel

        scores = compute_provider_scores()
        if getattr(args, "json", False):
            print(json.dumps({"scores": scores}, indent=2))
            return EXIT_SUCCESS
        if not scores:
            print("  No learned scores yet — needs 10+ dispatches per model in the last 7 days.")
            return EXIT_SUCCESS
        print(f"\n  {'Model':<30} {'Success':>8} {'AvgCost':>9} {'AvgLat':>8} {'Score':>6} {'Sample':>7}")
        print(f"  {'─' * 30} {'─' * 8} {'─' * 9} {'─' * 8} {'─' * 6} {'─' * 7}")
        for model, s in sorted(scores.items(), key=lambda kv: -kv[1].get("score", 0.0)):
            print(
                f"  {model:<30} {s.get('success_rate', 0):>7.0%} ${s.get('avg_cost_usd', 0):>8.4f}"
                f" {s.get('avg_latency_sec', 0):>7.1f}s {s.get('score', 0):>6.2f} {s.get('sample_count', 0):>7}"
            )
        print()
        return EXIT_SUCCESS

    from rondo.adapters.health import get_all_providers_health  # pylint: disable=import-outside-toplevel

    health_map = get_all_providers_health()

    if not health_map:
        if getattr(args, "json", False):
            print(json.dumps({"providers": []}))
        else:
            print("  No providers configured. Add [providers] to ~/.rondo/config.toml")
        return EXIT_SUCCESS

    if getattr(args, "json", False):
        providers_list = [
            {
                "provider": name,
                "healthy": status.healthy,
                "latency_ms": status.latency_ms,
                "error": status.error,
                "checked_at": status.checked_at,
            }
            for name, status in sorted(health_map.items())
        ]
        print(json.dumps({"providers": providers_list}, indent=2))
        return EXIT_SUCCESS

    # -- Human-readable table
    print(f"\n  {'Provider':<12}  {'Status':<8}  {'Latency':>10}")
    print(f"  {'─' * 12}  {'─' * 8}  {'─' * 10}")
    for name, status in sorted(health_map.items()):
        health_label = "UP" if status.healthy else "DOWN"
        latency = f"{status.latency_ms:.0f}ms" if status.healthy else "—"
        print(f"  {name:<12}  {health_label:<8}  {latency:>10}")
    print()
    return EXIT_SUCCESS


def _cmd_matrix(args: argparse.Namespace) -> int:
    """Execute 'rondo matrix run|status|report|reveal' — REQ-113 req 060 (RONDO-308)."""
    from rondo.matrix import (  # pylint: disable=import-outside-toplevel
        MatrixError,
        build_grid,
        default_effort_capable,
        estimate_grid_cost,
        load_matrix,
        matrix_report,
        matrix_status,
        reveal_matrix,
        run_matrix_live,
    )

    try:
        if args.action == "run":
            spec = load_matrix(args.target)
            cells = build_grid(spec, effort_capable=default_effort_capable)
            est = estimate_grid_cost(cells, spec.prompt)
            print(f"  matrix {spec.name}: {len(cells)} cells, estimated ${est:.3f}, budget ${spec.budget_usd:.2f}")
            if getattr(args, "dry_run", False):
                for c in cells:
                    print(f"    {c['key']}")
                return EXIT_SUCCESS
            manifest = run_matrix_live(spec)
            done = sum(1 for r in manifest["cells"].values() if r.get("status") == "done")
            print(f"  -PASS- {done}/{len(manifest['cells'])} cells done, spent ${manifest['spent_usd']:.4f}")
            print(matrix_report(spec.name))
            return EXIT_SUCCESS
        if args.action == "status":
            print(json.dumps(matrix_status(args.target), indent=2))
            return EXIT_SUCCESS
        if args.action == "report":
            print(matrix_report(args.target))
            return EXIT_SUCCESS
        if args.action == "reveal":
            mapping = reveal_matrix(args.target)
            for code, group in sorted(mapping.items()):
                print(f"  {code}  =  {group}")
            return EXIT_SUCCESS
        print(f"Unknown matrix action: {args.action}", file=sys.stderr)
        return EXIT_FAILURE
    except (MatrixError, OSError, json.JSONDecodeError) as exc:
        print(f"  -ERROR- matrix: {exc}", file=sys.stderr)
        return EXIT_FAILURE


def _resolve_retry_dir() -> str:
    """Retry dir — delegates to the canonical resolver (RONDO-314)."""
    from rondo.retry_queue import resolve_retry_dir  # pylint: disable=import-outside-toplevel

    return resolve_retry_dir()


def _cmd_retryq(args: argparse.Namespace) -> int:
    """Execute 'rondo retryq list|sweep|drain|purge-dead' — STD-108 req 018 (#296)."""
    from rondo.retry_queue import (  # pylint: disable=import-outside-toplevel
        DEAD_LETTER_DIRNAME,
        list_queue,
        sweep_retry_queue,
    )

    retry_dir = _resolve_retry_dir()
    if args.action == "list":
        entries = list_queue(retry_dir)
        if not entries:
            print("  retry queue empty")
            return EXIT_SUCCESS
        print(f"  {'Dispatch':<22} {'Class':<10} {'Age(d)':>7} Reason")
        for e in entries:
            print(f"  {e['dispatch_id']:<22} {e['error_class']:<10} {e['age_days']:>7.1f} {e['reason']}")
        return EXIT_SUCCESS
    if args.action == "sweep":
        report = sweep_retry_queue(retry_dir)
        print(
            f"  -PASS- sweep: {report.dead_lettered_permanent} permanent + "
            f"{report.dead_lettered_expired} expired dead-lettered, {report.remaining} remaining"
        )
        if report.alert:
            print(f"  -WARNING- {report.alert}", file=sys.stderr)
        return EXIT_SUCCESS
    if args.action == "drain":
        from rondo.mcp_dispatch import rondo_retry  # pylint: disable=import-outside-toplevel

        entries = [e for e in list_queue(retry_dir) if e["error_class"] == "transient"]
        if not entries:
            print("  nothing transient to drain")
            return EXIT_SUCCESS
        for e in entries:
            print(f"  draining {e['dispatch_id']} ({e['reason']})")
            rondo_retry(dispatch_id=e["dispatch_id"])
        print(f"  -PASS- drained {len(entries)} transient entr(ies)")
        return EXIT_SUCCESS
    if args.action == "purge-dead":
        dead = Path(retry_dir).expanduser() / DEAD_LETTER_DIRNAME
        count = 0
        if dead.is_dir():
            for f in dead.glob("*.json"):
                f.unlink()
                count += 1
        print(f"  -PASS- purged {count} dead-letter file(s)")
        return EXIT_SUCCESS
    print(f"Unknown retryq action: {args.action}", file=sys.stderr)
    return EXIT_FAILURE


# -- sig: mgh-6201.cd.bd955f.a4e5.32ef29
