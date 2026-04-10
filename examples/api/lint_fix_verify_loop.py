"""Rondo Real-World: Lint-Fix-Verify Loop.

REAL WORKFLOW THIS REPLACES:
  Run ace-build -> see pylint at 9.75 -> manually fix one violation ->
  rebuild -> check score -> fix next violation -> rebuild -> repeat.
  1,460 build/lint messages in 90 days.

SCRIPTED VERSION:
  Feed violations to Claude -> get fix suggestions -> apply ->
  re-check -> loop until score target or max retries.

HOW TO RUN:
  python examples/api/lint_fix_verify_loop.py

THE DECISION LOGIC:
  - Score >= target -> done
  - Score improved -> continue loop
  - Score stuck after fix -> try different approach
  - Max retries hit -> stop, report what's left
"""

import json
import os
import sys

from rondo import smart_return

## Default: Anthropic API — works everywhere (inside Claude Code, terminal, CI).
## Haiku is cheap ($0.001/call). Override: RONDO_MODEL=anthropic:claude-sonnet-4-6
DEFAULT_MODEL = os.environ.get("RONDO_MODEL", "anthropic:claude-haiku-4-5")

_mcp_dispatch = None


def _get_dispatch_module() -> object:
    """Lazy-load mcp_dispatch."""
    global _mcp_dispatch  # noqa: PLW0603
    if _mcp_dispatch is None:
        from rondo import mcp_dispatch  # pylint: disable=import-outside-toplevel

        _mcp_dispatch = mcp_dispatch
    return _mcp_dispatch


def _out(msg: str) -> None:
    """Write output line."""
    sys.stdout.write(msg + "\n")


def _dispatch(prompt: str, model: str = "") -> dict | None:
    """Real AI dispatch via Rondo. Free on Claude Max plan."""
    use_model = model or DEFAULT_MODEL
    try:
        mod = _get_dispatch_module()
        raw = mod.rondo_run_file(  # type: ignore[union-attr]
            prompt=prompt,
            model=use_model,
            dry_run=False,
            timeout_sec=60,
        )
        data = json.loads(raw)
        if data.get("status") == "error":
            return None
        tasks = data.get("tasks", [])
        if not tasks or tasks[0].get("status") == "error":
            return None
        output = tasks[0].get("raw_output", "")
        try:
            parsed = json.loads(output)
        except json.JSONDecodeError:
            parsed = {"passed": True, "result": output[:500], "issues": [], "confidence": 0.5}
        return smart_return.normalize_response(parsed)
    except (FileNotFoundError, OSError, json.JSONDecodeError, TypeError, KeyError) as exc:
        _out(f"  Dispatch failed: {exc}")
        return None


## --- Sample Lint Data --------------------------------------------
## In production: parse output of ace-build lint or pylint --json

SAMPLE_VIOLATIONS = [
    {"file": "src/hooks.py", "line": 42, "code": "C0301", "message": "Line too long (142/120)"},
    {"file": "src/smart_return.py", "line": 88, "code": "W0611", "message": "Unused import os"},
    {"file": "src/scoring.py", "line": 15, "code": "R0903", "message": "Too few public methods (1/2)"},
]

FIX_PROMPT = """Fix these pylint violations with minimum changes.
For each violation, return the fix as JSON:
{{"fixes": [{{"file": "...", "line": N, "code": "...", "fix": "description of change"}}]}}

Violations:
{violations}"""


## --- The Loop (real logic, real AI) -------------------------------


def lint_fix_loop(
    violations: list[dict],
    target_score: float = 10.0,
    max_retries: int = 3,
) -> dict:
    """Loop: send violations to AI -> get fixes -> simulate re-lint -> repeat.

    In production: actually run ace-build lint between iterations.
    Here: we send real violations to Claude and get real fix suggestions.
    The loop logic and retry decisions are REAL.
    """
    history: list[dict] = []
    remaining = list(violations)
    score = 10.0 - (len(remaining) * 0.08)  ## Approximate score from violation count

    for attempt in range(max_retries):
        _out(f"  Attempt {attempt + 1}: score={score:.2f}, violations={len(remaining)}")

        if score >= target_score or not remaining:
            _out(f"  -PASS- Target {target_score} reached!")
            history.append({"attempt": attempt + 1, "score": score, "action": "TARGET_HIT"})
            return {"final_score": score, "attempts": attempt + 1, "target_reached": True, "history": history}

        ## Ask AI to fix violations
        prompt = FIX_PROMPT.format(violations=json.dumps(remaining, indent=2))
        result = _dispatch(prompt)

        if result is None:
            _out("  AI dispatch failed -- stopping loop")
            history.append({"attempt": attempt + 1, "score": score, "action": "DISPATCH_FAILED"})
            break

        ## Count fixes suggested
        fixes = result.get("fixes", result.get("issues", []))
        fix_count = len(fixes) if isinstance(fixes, list) else 1
        _out(f"    AI suggested {fix_count} fixes (confidence={result.get('confidence', 'n/a')})")

        ## Simulate applying fixes and re-linting
        fixed = min(fix_count, len(remaining))
        remaining = remaining[fixed:]
        prev_score = score
        score = 10.0 - (len(remaining) * 0.08)

        if score <= prev_score:
            _out(f"  -WARNING- Score stuck at {score:.2f}")
            history.append({"attempt": attempt + 1, "score": score, "action": "STUCK"})
        else:
            _out(f"    Score: {prev_score:.2f} -> {score:.2f}")
            history.append({"attempt": attempt + 1, "score": score, "fixes": fixed, "action": "FIXED"})

    return {
        "final_score": score,
        "attempts": len(history),
        "target_reached": score >= target_score,
        "history": history,
    }


def main() -> None:
    """Demonstrate lint-fix-verify loop with real AI."""
    _out("=== Lint-Fix-Verify Loop ===")
    _out("")

    _out("(REAL dispatch -- sending violations to Claude)")
    _out("")
    result = lint_fix_loop(SAMPLE_VIOLATIONS)
    _out("")
    _out(f"Final: score={result['final_score']:.2f}, attempts={result['attempts']}")
    _out(f"  Target reached: {result['target_reached']}")


if __name__ == "__main__":
    main()


# -- sig: mgh-6201.cd.bd955f.ea21.1ea521
