"""Rondo Scripted Prompting: Retry on Failure.

When an AI says "can't do it" or returns low confidence,
don't give up — try a different provider or rephrase.

THIS IS PROMPT CODING: Python logic wrapping AI calls,
using structured return data to decide what happens next.
"""

from rondo.smart_return import normalize_response


def dispatch_mock(prompt: str, model: str, fail: bool = False) -> dict:
    """Mock dispatch — simulates success or failure for testing both paths."""
    if fail:
        return {
            "passed": False,
            "confidence": 0.3,
            "result": "",
            "issues": ["Cannot analyze — code too complex"],
            "_meta": {"quality": 2, "complete": False, "limitations": "Could not parse the input"},
        }
    return {
        "passed": True,
        "confidence": 0.95,
        "result": f"Analysis complete via {model}",
        "issues": [],
        "_meta": {"quality": 9, "complete": True, "limitations": ""},
    }


def review_with_retry(prompt: str) -> dict:
    """Try primary provider; if it fails, retry with a better model.

    This is the core pattern: dispatch → check → decide → retry.
    The structured return (passed, confidence, issues) drives the logic.
    """
    ## Step 1: Try the cheap/fast provider first
    result = dispatch_mock(prompt, model="gemini:flash", fail=True)
    result = normalize_response(result)

    if result["passed"] and result["confidence"] >= 0.8:
        print(f"  PRIMARY succeeded: confidence={result['confidence']}")
        return result

    ## Step 2: Primary failed or uncertain — escalate to premium model
    print(f"  PRIMARY failed: confidence={result['confidence']}, issues={result['issues']}")
    print("  Escalating to premium model...")

    result = dispatch_mock(prompt, model="opus", fail=False)
    result = normalize_response(result)

    if result["passed"]:
        print(f"  ESCALATION succeeded: confidence={result['confidence']}")
        return result

    ## Step 3: Both failed — return failure with combined context
    print("  ESCALATION also failed — returning error")
    return {"passed": False, "result": "All providers failed", "issues": result["issues"]}


def main() -> None:
    """Demonstrate retry-on-failure pattern."""
    print("=== Retry on Failure Pattern ===")
    print("Scenario: primary provider can't handle complex code")
    result = review_with_retry("Review this complex algorithm")
    print(f"Final: passed={result['passed']}, result={result.get('result', '')[:60]}")


if __name__ == "__main__":
    main()


# -- sig: mgh-6201.cd.bd955f.ea10.1ea4b0
