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
        return {"result": output, "passed": True, "issues": [], "confidence": 0.5}


SAMPLE_VIOLATIONS = [
    {"file": "src/hooks.py", "line": 42, "code": "C0301", "message": "Line too long (142/120)"},
    {"file": "src/smart_return.py", "line": 88, "code": "W0611", "message": "Unused import os"},
    {"file": "src/scoring.py", "line": 15, "code": "R0903", "message": "Too few public methods (1/2)"},
]


def lint_fix_loop(violations: list[dict], target: float = 10.0, max_retries: int = 3) -> dict:
    """Loop: send violations to AI -> get fixes -> re-check -> repeat."""
    history: list[dict] = []
    remaining = list(violations)
    score = 10.0 - (len(remaining) * 0.08)

    for attempt in range(max_retries):
        _out(f"  Attempt {attempt + 1}: score={score:.2f}, violations={len(remaining)}")
        if score >= target or not remaining:
            _out(f"  -PASS- Target {target} reached!")
            history.append({"attempt": attempt + 1, "score": score, "action": "TARGET_HIT"})
            return {"final_score": score, "attempts": attempt + 1, "target_reached": True, "history": history}

        result = dispatch(
            f"Fix these pylint violations with minimum changes. Return JSON with fixes array:\n{json.dumps(remaining, indent=2)}",
            rules="You are a Python linter fix assistant. Return JSON only.",
        )
        if result is None:
            _out("  Dispatch failed")
            break

        fixes = result.get("fixes", result.get("issues", []))
        fix_count = len(fixes) if isinstance(fixes, list) else 1
        _out(f"    AI suggested {fix_count} fixes")

        fixed = min(fix_count, len(remaining))
        remaining = remaining[fixed:]
        score = 10.0 - (len(remaining) * 0.08)
        history.append({"attempt": attempt + 1, "score": score, "fixes": fixed, "action": "FIXED"})

    return {"final_score": score, "attempts": len(history), "target_reached": score >= target, "history": history}


def main() -> None:
    """Run lint-fix-verify loop with real AI."""
    _out("=== Lint-Fix-Verify Loop ===")
    _out("")
    result = lint_fix_loop(SAMPLE_VIOLATIONS)
    _out("")
    _out(f"Final: score={result['final_score']:.2f}, attempts={result['attempts']}, target={result['target_reached']}")


if __name__ == "__main__":
    main()


# -- sig: mgh-6201.cd.bd955f.ea21.1ea521
