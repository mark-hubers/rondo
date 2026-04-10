"""Rondo Real-World: Lint-Fix-Verify Loop.

REAL WORKFLOW THIS REPLACES:
  Run ace-build → see pylint at 9.75 → manually fix one violation →
  rebuild → check score → fix next violation → rebuild → repeat.
  1,460 build/lint messages in 90 days. Session 100 had 22 sprints
  of this loop done manually.

SCRIPTED VERSION:
  Run linter → collect violations → send to AI for minimum-change
  fix → apply fix → re-run linter → loop until score target hit
  or max retries reached.

THE DECISION LOGIC:
  - Score >= target → done, report success
  - Score improved but not there yet → fix next batch, continue
  - Score didn't improve after fix → different approach, retry
  - Max retries hit → stop, report what's left unfixed
"""

import sys

from rondo import smart_return


def _out(msg: str) -> None:
    """Write output line — examples are user-facing, not library code."""
    sys.stdout.write(msg + "\n")


## ─── Mock Build System ───────────────────────────────────────────
## In production: subprocess.run(["ace-build", "lint", "--json"])
## These simulate pylint output at different score levels.


def _mock_lint_run(attempt: int) -> dict:
    """Simulate ace-build lint output at different stages.

    Attempt 0: Initial state — 3 violations, score 9.75
    Attempt 1: After first fix — 1 violation, score 9.92
    Attempt 2: After second fix — 0 violations, score 10.00
    """
    if attempt == 0:
        return {
            "score": 9.75,
            "violations": [
                {
                    "file": "src/rondo/hooks.py",
                    "line": 42,
                    "code": "C0301",
                    "message": "Line too long (142/120)",
                },
                {
                    "file": "src/rondo/smart_return.py",
                    "line": 88,
                    "code": "W0611",
                    "message": "Unused import os",
                },
                {
                    "file": "src/rondo/scoring.py",
                    "line": 15,
                    "code": "R0903",
                    "message": "Too few public methods (1/2)",
                },
            ],
        }
    if attempt == 1:
        return {
            "score": 9.92,
            "violations": [
                {
                    "file": "src/rondo/scoring.py",
                    "line": 15,
                    "code": "R0903",
                    "message": "Too few public methods (1/2)",
                },
            ],
        }
    return {"score": 10.00, "violations": []}


def _mock_ai_fix(violations: list[dict]) -> dict:
    """Simulate AI suggesting fixes for lint violations.

    In production: rondo_run(prompt=f"Fix these pylint violations
    with minimum changes: {violations}", model="gemini:flash")
    """
    fixes = []
    for v in violations:
        fixes.append(
            {
                "file": v["file"],
                "line": v["line"],
                "code": v["code"],
                "fix": f"Fixed {v['code']}: {v['message'][:40]}",
                "diff": f"--- {v['file']}\n+++ {v['file']}\n@@ -{v['line']} @@\n-old\n+fixed",
            }
        )
    return {
        "passed": True,
        "confidence": 0.9,
        "result": f"Generated {len(fixes)} fixes",
        "issues": [],
        "fixes": fixes,
        "_meta": {"quality": 8, "complete": True, "limitations": ""},
    }


## ─── The Loop ────────────────────────────────────────────────────


def lint_fix_loop(
    target_score: float = 10.0,
    max_retries: int = 5,
) -> dict:
    """Run linter → AI fix → re-lint → loop until target score.

    This is the REAL scripted workflow:
    1. Run linter, get score + violations
    2. If score >= target → done
    3. Send violations to AI for minimum-change fixes
    4. Apply fixes (simulated here)
    5. Re-run linter, check new score
    6. If score improved → continue loop
    7. If score stuck → try different approach
    8. If max retries → stop and report

    Returns dict with final score, attempts made, and fix history.
    """
    history: list[dict] = []
    prev_score = 0.0

    for attempt in range(max_retries):
        ## Step 1: Run linter
        lint_result = _mock_lint_run(attempt)
        score = lint_result["score"]
        violations = lint_result["violations"]

        _out(f"  Attempt {attempt + 1}: score={score}, violations={len(violations)}")

        ## Step 2: Check if we hit the target
        if score >= target_score:
            _out(f"  -PASS- Target {target_score} reached!")
            history.append({"attempt": attempt + 1, "score": score, "action": "TARGET_HIT"})
            return {
                "final_score": score,
                "attempts": attempt + 1,
                "target_reached": True,
                "history": history,
            }

        ## Step 3: Check if score is stuck (no improvement)
        if attempt > 0 and score <= prev_score:
            _out(f"  -WARNING- Score stuck at {score} — trying different approach")
            history.append({"attempt": attempt + 1, "score": score, "action": "STUCK_RETRY"})
            ## In production: switch provider, add more context, or flag for human
            prev_score = score
            continue

        ## Step 4: Get AI fixes
        ai_result = smart_return.normalize_response(_mock_ai_fix(violations))
        _out(f"    AI generated {len(violations)} fixes (confidence={ai_result['confidence']})")

        ## Step 5: Apply fixes (simulated)
        for v in violations:
            _out(f"    Applied: {v['code']} in {v['file']}:{v['line']}")

        history.append(
            {
                "attempt": attempt + 1,
                "score": score,
                "fixes_applied": len(violations),
                "action": "FIXED",
            }
        )
        prev_score = score

    ## Max retries exhausted
    _out(f"  -WARNING- Max retries ({max_retries}) reached. Final score: {prev_score}")
    return {
        "final_score": prev_score,
        "attempts": max_retries,
        "target_reached": False,
        "history": history,
    }


def main() -> None:
    """Demonstrate the lint-fix-verify loop."""
    _out("=== Lint-Fix-Verify Loop ===")
    _out("(Replaces: manual ace-build -> fix -> rebuild -> repeat)")
    _out("")

    result = lint_fix_loop(target_score=10.0, max_retries=5)
    _out("")
    _out(f"Final: score={result['final_score']}, attempts={result['attempts']}")
    _out(f"  Target reached: {result['target_reached']}")
    for h in result["history"]:
        _out(f"  Attempt {h['attempt']}: score={h['score']} -> {h['action']}")

    ## Verify the loop worked
    if not result["target_reached"]:
        _out("  -ERROR- Should have reached target 10.0")
        sys.exit(1)
    if result["attempts"] > 5:
        _out("  -ERROR- Should not exceed max retries")
        sys.exit(1)

    _out("")
    _out("The key: the LOOP is the script. AI fixes, Python decides when to stop.")


if __name__ == "__main__":
    main()


# -- sig: mgh-6201.cd.bd955f.ea21.1ea521
