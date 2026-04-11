# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Rondo example: batched lint-fix *suggestions* from a model.

What this demonstrates
----------------------
* Batching structured input (violations as JSON in the prompt).
* Parsing a **fixes** array from model JSON.
* **Matching fixes to violations by pylint ``code``** when the model cooperates;
  if codes are missing, the script explains the demo-only fallback.

What this does *not* do
-----------------------
* It does not edit files or run pylint. Wire ``subprocess.run(["pylint", ...])`` (or your
  build) where the ``PRODUCTION`` comments indicate.

Uses **live** dispatch (``dry_run=False``). Requires a working ``claude`` / Rondo setup.

Run::

    cd rondo && uv run python examples/api/lint_fix_verify_loop.py
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from example_dispatch import banner, run_prompt_json

SAMPLE_VIOLATIONS: list[dict[str, Any]] = [
    {"file": "src/hooks.py", "line": 42, "code": "C0301", "message": "Line too long (142/120)"},
    {"file": "src/smart_return.py", "line": 88, "code": "W0611", "message": "Unused import os"},
    {"file": "src/scoring.py", "line": 15, "code": "R0903", "message": "Too few public methods (1/2)"},
]


def lint_fix_loop(
    violations: list[dict[str, Any]],
    *,
    max_retries: int,
    timeout_sec: int,
) -> dict[str, Any]:
    """Ask the model for fixes; shrink ``remaining`` using codes when possible."""
    all_fixes: list[Any] = []
    remaining = list(violations)

    for attempt in range(max_retries):
        if not remaining:
            print(f"  Attempt {attempt + 1}: nothing left to send.")
            break

        print(f"  Attempt {attempt + 1}: asking model about {len(remaining)} violation(s)…")
        prompt = (
            "Fix these pylint violations with minimal changes.\n"
            'Return JSON only: {"fixes": [{"code": "C0301", "fix": "what to change"}]}\n\n'
            f"{json.dumps(remaining, indent=2)}"
        )
        try:
            env, parsed = run_prompt_json(
                prompt=prompt,
                model="",
                dry_run=False,
                timeout_sec=timeout_sec,
                rules="You suggest pylint fixes. Output JSON only, no markdown.",
            )
        except RuntimeError as exc:
            print(f"    -ERROR- {exc}", file=sys.stderr)
            break

        if parsed.get("_non_json"):
            print("    -WARNING- Model output was not JSON; stop.", file=sys.stderr)
            break

        fixes = parsed.get("fixes")
        if not isinstance(fixes, list):
            print("    -WARNING- Missing 'fixes' list; stop.")
            break

        print(f"    Model returned {len(fixes)} fix object(s); status={env.get('status')!r}")
        all_fixes.extend(fixes)

        codes_from_model = {
            str(f.get("code", "")).strip() for f in fixes if isinstance(f, dict) and str(f.get("code", "")).strip()
        }
        if codes_from_model:
            before = len(remaining)
            remaining = [v for v in remaining if str(v.get("code", "")).strip() not in codes_from_model]
            print(f"    Removed {before - len(remaining)} violation(s) by matching pylint code.")
        else:
            # -- Demo fallback: model did not echo codes — do not pretend we verified fixes.
            n = min(len(fixes), len(remaining))
            remaining = remaining[n:]
            print(
                f"    Demo fallback: dropped first {n} violation(s) (model omitted 'code' — "
                "tighten the prompt or parse free text in production)."
            )

        if not fixes:
            break

    return {
        "total_violations": len(violations),
        "fixes_suggested": len(all_fixes),
        "remaining_count": len(remaining),
        "all_addressed": len(remaining) == 0,
        "fixes": all_fixes,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--max-retries", type=int, default=3, metavar="N")
    parser.add_argument("--timeout", type=int, default=120, metavar="SEC")
    args = parser.parse_args()

    print(banner("Lint-fix suggestions (no files modified)"))
    result = lint_fix_loop(
        SAMPLE_VIOLATIONS,
        max_retries=args.max_retries,
        timeout_sec=args.timeout,
    )
    print()
    print(
        f"Violations: {result['total_violations']}, "
        f"fix objects: {result['fixes_suggested']}, "
        f"remaining: {result['remaining_count']}, "
        f"cleared={result['all_addressed']}"
    )
    return 0 if result["remaining_count"] == 0 or result["fixes_suggested"] > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
