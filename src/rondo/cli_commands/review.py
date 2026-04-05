# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""CLI review command — multi-provider file review.

Rondo-REQ-109 reqs 082-087.
Sends a file to 2+ cloud providers for independent review.
Import direction: cli.py → cli_commands → review.py (one-way).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rondo.cli_commands import EXIT_FAILURE, EXIT_SUCCESS


def _cmd_review(args: argparse.Namespace) -> int:
    """Send a file to 2+ cloud providers for independent review — REQ-109 reqs 082-087.

    Uses rondo_cloud() internally — same dispatch engine as MCP, no adapter imports.
    """
    import json as _json  # pylint: disable=import-outside-toplevel

    file_path = Path(args.file).expanduser().resolve()
    if not file_path.is_file():
        print(f"Error: file not found: {file_path}", file=sys.stderr)
        return EXIT_FAILURE

    try:
        content = file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print(f"Error reading file: {exc}", file=sys.stderr)
        return EXIT_FAILURE

    if not content.strip():
        print("Error: file is empty", file=sys.stderr)
        return EXIT_FAILURE

    prompt = f"Review this file for bugs, security issues, and code quality.\n\nFile: {file_path.name}\n\n```\n{content}\n```"
    tier = getattr(args, "tier", "default")
    dry_run = getattr(args, "dry_run", False)
    output_fmt = getattr(args, "output", "text")

    # -- Resolve provider:model list
    provider_models = _resolve_review_providers(args.providers, tier)

    if dry_run:
        return _review_dry_run(file_path, prompt, provider_models, tier, output_fmt)

    # -- Dispatch via rondo_multi_review (same engine as MCP)
    from rondo.mcp_server import rondo_multi_review  # pylint: disable=import-outside-toplevel

    providers_json = _json.dumps(provider_models)
    result_json = rondo_multi_review(prompt=prompt, providers=providers_json, dry_run=False)
    result = _json.loads(result_json)

    if output_fmt == "json":
        result["file"] = str(file_path)
        result["tier"] = tier
        print(_json.dumps(result, indent=2))
    else:
        _print_review_text(file_path, result)

    return EXIT_SUCCESS if result.get("status") == "done" else EXIT_FAILURE


def _resolve_review_providers(providers_arg: str, tier: str) -> list[str]:
    """Resolve provider names to provider:model strings for review dispatch."""
    from rondo.providers import _providers_config, load_providers_config  # pylint: disable=import-outside-toplevel

    load_providers_config()
    tier_map = {"high": "best_model", "default": "default_model", "low": "cheap_model"}
    tier_key = tier_map.get(tier, "default_model")

    # -- Get provider names from arg or config profile
    if providers_arg:
        names = [p.strip() for p in providers_arg.split(",") if p.strip()]
    else:
        names = _get_review_profile_providers()

    # -- Resolve each to provider:model
    result = []
    for name in names:
        cfg = _providers_config.get(name, {})
        model = cfg.get(tier_key, "")
        result.append(f"{name}:{model}" if model else name)
    return result


def _get_review_profile_providers() -> list[str]:
    """Read review profile from config.toml, fallback to defaults."""
    from rondo.config import get_rondo_config  # pylint: disable=import-outside-toplevel

    cfg = get_rondo_config()
    providers = cfg.get("cloud", {}).get("profiles", {}).get("review", {}).get("providers", [])
    return providers if providers else ["gemini", "grok"]


def _review_dry_run(file_path: object, prompt: str, provider_models: list, tier: str, output_fmt: str) -> int:
    """Print dry-run info for review command."""
    import json as _json  # pylint: disable=import-outside-toplevel

    output = {
        "status": "dry_run",
        "file": str(file_path),
        "prompt_length": len(prompt),
        "providers": provider_models,
        "tier": tier,
        "prompt_preview": prompt[:500],
    }
    if output_fmt == "json":
        print(_json.dumps(output, indent=2))
    else:
        print(f"  File: {getattr(file_path, 'name', file_path)} ({len(prompt)} chars)")
        print(f"  Providers: {', '.join(provider_models)}")
        print(f"  Tier: {tier}")
        print(f"  Prompt: {len(prompt)} chars (dry-run, not dispatched)")
    return EXIT_SUCCESS


def _print_review_text(file_path: object, result: dict) -> None:
    """Print review results in human-readable format."""
    print(f"\n  Rondo Review: {getattr(file_path, 'name', file_path)}")
    print(f"  {'═' * 60}\n")
    for r in result.get("per_provider", []):
        status_icon = "PASS" if r.get("status") == "done" else "FAIL"
        print(f"  [{status_icon}] {r.get('provider', '?')} ({r.get('duration_sec', 0):.1f}s)")
        output_text = r.get("output", "")
        if r.get("status") == "done" and output_text:
            for line in output_text.strip().split("\n"):
                print(f"    {line}")
        elif r.get("error"):
            print(f"    Error: {r['error']}")
        print()


# -- sig: mgh-6201.cd.bd955f.a5f6.dd08e8
