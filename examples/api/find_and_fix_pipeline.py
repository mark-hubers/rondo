# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
# rondo-meta: mode=subprocess provider=anthropic category=pipeline value="Find -> fix -> verify chain with real dispatches"

"""Rondo example: find → fix → verify pipeline.

Chain AI calls where each step's output feeds the next.
Step 1: Find bugs. Step 2: Generate fixes. Step 3: Verify fixes.

Uses **live** dispatch.

Run::

    cd rondo && uv run python examples/api/find_and_fix_pipeline.py
"""

from __future__ import annotations

import argparse
from typing import Any

from example_dispatch import banner, run_prompt_json

CODE_SAMPLE = """def login(username, password):
    query = f"SELECT * FROM users WHERE name={username}"
    result = db.execute(query)
    return result  # No auth check on /admin routes
"""


def find_fix_verify(*, timeout_sec: int) -> dict[str, Any]:
    """Three-step pipeline: find → fix → verify via real AI."""
    ## Step 1: Find bugs
    print("  Step 1: Find bugs...")
    try:
        _, findings = run_prompt_json(
            prompt=f'Find security bugs in this code. Return JSON: {{"issues": ["bug 1", "bug 2"]}}\n\n{CODE_SAMPLE}',
            timeout_sec=timeout_sec,
            rules="You find code bugs. Return JSON only.",
        )
    except RuntimeError as exc:
        return {"error": str(exc), "stage": "find"}

    if findings.get("_non_json"):
        return {"error": "non-JSON from find step", "stage": "find"}

    bugs = findings.get("issues", [])
    print(f"    Found {len(bugs)} bug(s)")
    if not bugs:
        return {"stage": "find", "bugs": [], "fixes": [], "all_verified": True}

    ## Step 2: Fix each bug
    print("  Step 2: Generate fixes...")
    fixes: list[dict[str, Any]] = []
    for bug in bugs[:3]:  ## Limit to 3 to keep tests fast
        try:
            _, fix = run_prompt_json(
                prompt=f'Suggest a fix for this bug. Return JSON: {{"fix": "description"}}\n\nBug: {bug}',
                timeout_sec=timeout_sec,
                rules="You fix code bugs. Return JSON with 'fix' field.",
            )
        except RuntimeError as exc:
            fixes.append({"bug": str(bug)[:80], "fix": None, "error": str(exc)[:80]})
            continue
        fixes.append(
            {
                "bug": str(bug)[:80],
                "fix": str(fix.get("fix", ""))[:120],
                "verified": False,
            }
        )

    ## Step 3: Verify (just count non-empty fixes)
    verified = sum(1 for f in fixes if f.get("fix"))
    print(f"  Step 3: {verified}/{len(fixes)} fixes produced")

    return {
        "stage": "complete",
        "bugs": bugs,
        "fixes": fixes,
        "verified_count": verified,
    }


def main() -> int:
    """Run find-fix-verify pipeline."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--timeout", type=int, default=60, metavar="SEC")
    args = parser.parse_args()

    print(banner("Find → Fix → Verify"))
    result = find_fix_verify(timeout_sec=args.timeout)
    print()
    if result.get("error"):
        print(f"-ERROR- {result['stage']}: {result['error']}")
        return 1
    print(f"Bugs: {len(result['bugs'])}, Fixes: {result.get('verified_count', 0)}")
    for f in result.get("fixes", []):
        print(f"  - {f.get('bug', '')[:50]}")
        print(f"    → {str(f.get('fix', ''))[:60]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
