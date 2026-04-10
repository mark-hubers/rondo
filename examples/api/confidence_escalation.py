"""Rondo Scripted Prompting: Confidence Escalation.

If the AI isn't confident enough, ask again with more context
or escalate to a more capable model. The confidence score
(0.0-1.0) returned by every dispatch drives the decision.

This pattern prevents shipping low-quality AI answers to users.
"""

from rondo.smart_return import normalize_response


def dispatch_mock(prompt: str, model: str, confidence: float = 0.5) -> dict:
    """Mock dispatch with controllable confidence for testing."""
    return {
        "passed": True,
        "confidence": confidence,
        "result": f"Answer from {model}",
        "issues": [],
        "_meta": {
            "quality": int(confidence * 10),
            "complete": confidence > 0.7,
            "limitations": "Low confidence" if confidence < 0.7 else "",
        },
    }


def review_with_confidence_check(prompt: str, threshold: float = 0.8) -> dict:
    """Dispatch and escalate if confidence is below threshold.

    Level 1: Fast/cheap model (flash) — good for simple tasks
    Level 2: Add context and retry — helps with ambiguous prompts
    Level 3: Premium model (opus) — expensive but thorough
    """
    ## Level 1: Fast model
    result = normalize_response(dispatch_mock(prompt, "gemini:flash", confidence=0.6))
    print(f"  Level 1 (flash): confidence={result['confidence']}")

    if result["confidence"] >= threshold:
        return result

    ## Level 2: Same model but with added context
    enriched_prompt = f"{prompt}\n\nAdditional context: focus on security implications"
    result = normalize_response(dispatch_mock(enriched_prompt, "gemini:flash", confidence=0.75))
    print(f"  Level 2 (flash+context): confidence={result['confidence']}")

    if result["confidence"] >= threshold:
        return result

    ## Level 3: Premium model
    result = normalize_response(dispatch_mock(prompt, "opus", confidence=0.95))
    print(f"  Level 3 (opus): confidence={result['confidence']}")
    return result


def main() -> None:
    """Demonstrate confidence-based escalation."""
    print("=== Confidence Escalation Pattern ===")
    print("Threshold: 0.8 — anything below gets escalated")
    result = review_with_confidence_check("Is this login handler secure?")
    print(f"Final: confidence={result['confidence']}, quality={result['_meta']['quality']}/10")


if __name__ == "__main__":
    main()


# -- sig: mgh-6201.cd.bd955f.ea11.1ea4b1
