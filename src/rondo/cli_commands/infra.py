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

def _cmd_spool(args: argparse.Namespace) -> int:
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

def _cmd_mcp(args: argparse.Namespace) -> int:
    """Start MCP stdio server — IFS-104.

    Claude Code spawns this, talks via stdin/stdout.
    No daemon, no port, just stdio.
    """
    from rondo.mcp_server import run_mcp  # pylint: disable=import-outside-toplevel

    run_mcp()
    return EXIT_SUCCESS

def _cmd_init(args: argparse.Namespace) -> int:
    """Create a starter round file or config — U-10 to U-14."""
    import shutil  # pylint: disable=import-outside-toplevel

    # -- rondo init --config: create ~/.rondo/config.toml from template
    if getattr(args, "config", False):
        config_dir = Path.home() / ".rondo"
        config_path = config_dir / "config.toml"
        if config_path.exists():
            print(f"Config already exists: {config_path}", file=sys.stderr)
            print("  Edit it directly, or remove it first to regenerate.", file=sys.stderr)
            return EXIT_FAILURE
        config_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        # -- Copy template from examples/
        template = Path(__file__).parent.parent.parent.parent / "examples" / "config.toml"
        if not template.exists():
            print("Error: template not found at examples/config.toml", file=sys.stderr)
            return EXIT_FAILURE
        shutil.copy2(template, config_path)
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
    """Create a launchd plist for recurring Rondo dispatch."""
    from rondo.schedule import generate_plist  # pylint: disable=import-outside-toplevel

    file_path = str(Path(args.file).resolve())
    name = args.name or Path(args.file).stem
    cmd_args = ["run", file_path]
    if args.model:
        cmd_args.extend(["--model", args.model])

    plist = generate_plist(
        name=name,
        command=__import__("shutil").which("rondo") or "rondo",  # -- RONDO-216 C5: was hardcoded path
        args=cmd_args,
        interval=args.interval,
        work_dir=str(Path(file_path).parent),
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

def _cmd_providers(args: argparse.Namespace) -> int:
    """Show all configured providers with health status — REQ-109 req 020."""
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

# -- sig: mgh-6201.cd.bd955f.a4e5.32ef29
