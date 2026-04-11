"""Rondo Real-World: Lint-Fix-Verify Loop.

REAL WORKFLOW THIS REPLACES:
  ace-build -> see violations -> fix one -> rebuild -> repeat.

SCRIPTED VERSION:
  Feed violations to Claude via Rondo -> get fix suggestions ->
  simulate apply -> loop until score target or max retries.

HOW TO RUN:
  python examples/api/lint_fix_verify_loop.py
"""

import json
import sys

from rondo import mcp_dispatch


def _out(msg: str) -> None:
    """Write output line."""
    sys.stdout.write(msg + "\n")


def dispatch(prompt: str, **kwargs: str | int) -> dict | None:
    """Dispatch prompt via Rondo inline subprocess (free on Max)."""
    raw = mcp_dispatch.rondo_run_file(
        prompt=prompt,
        model="",
        dry_run=False,
        timeout_sec=60,
        _session=object(),
        **kwargs,
    )
    data = json.loads(raw)
    tasks = data.get("tasks", [])
    if not tasks or tasks[0].get("status") == "error":
        return None
    output = tasks[0].get("raw_output", "")
    try:
        return json.loads(output)
    except json.JSONDecodeError:
        return {"result": output, "passed": None, "issues": [], "confidence": 0.0}


SAMPLE_VIOLATIONS = [
    {"file": "src/hooks.py", "line": 42, "code": "C0301", "message": "Line too long (142/120)"},
    {"file": "src/smart_return.py", "line": 88, "code": "W0611", "message": "Unused import os"},
    {"file": "src/scoring.py", "line": 15, "code": "R0903", "message": "Too few public methods (1/2)"},
]


def lint_fix_loop(violations: list[dict], max_retries: int = 3) -> dict:
    """Send violations to AI in batches, collect fix suggestions.

    NOTE: This example asks AI for fixes but does NOT apply them or re-run
    the linter. In production, you would: apply the fix → run ace-build lint
    → check the new score → loop. Here we demonstrate the AI dispatch + retry
    pattern without the build system integration.
    """
    all_fixes: list[dict] = []
    remaining = list(violations)

    for attempt in range(max_retries):
        if not remaining:
            _out(f"  Attempt {attempt + 1}: all violations addressed")
            break

        _out(f"  Attempt {attempt + 1}: {len(remaining)} violations remaining")
        result = dispatch(
            f"Fix these pylint violations with minimum changes. For each, return the fix.\n"
            f'Return JSON: {{"fixes": [{{"code": "C0301", "fix": "description"}}]}}\n\n'
            f"{json.dumps(remaining, indent=2)}",
            rules="You fix pylint violations. Return JSON with fixes array.",
        )
        if result is None:
            _out("    Dispatch failed — stopping")
            break

        fixes = result.get("fixes", result.get("issues", []))
        fix_count = len(fixes) if isinstance(fixes, list) else 0
        _out(f"    AI suggested {fix_count} fix(es)")

        if fix_count == 0:
            _out("    No fixes suggested — stopping")
            break

        all_fixes.extend(fixes if isinstance(fixes, list) else [])
        ## In production: apply fixes here, then re-run linter
        ## remaining = run_linter_and_get_violations()
        ## For demo: assume fixes address the violations sent
        remaining = remaining[min(fix_count, len(remaining)) :]

    return {
        "total_violations": len(violations),
        "fixes_suggested": len(all_fixes),
        "remaining": len(remaining),
        "all_addressed": len(remaining) == 0,
        "fixes": all_fixes,
    }


def main() -> None:
    """Run lint fix loop with real AI."""
    _out("=== Lint Fix Loop ===")
    _out("")
    result = lint_fix_loop(SAMPLE_VIOLATIONS)
    _out("")
    _out(
        f"Violations: {result['total_violations']}, Fixes: {result['fixes_suggested']}, Remaining: {result['remaining']}"
    )


if __name__ == "__main__":
    main()


# -- sig: mgh-6201.cd.bd955f.ea21.1ea521
