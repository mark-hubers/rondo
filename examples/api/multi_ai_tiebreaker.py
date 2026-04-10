"""Rondo Scripted Prompting: Multi-AI Tiebreaker.

Send the same question to 2 AIs. If they disagree,
send to a 3rd for tiebreaker. The structured return
(passed, issues) makes disagreement detection trivial.

This pattern catches AI hallucinations — if 2 out of 3
agree, the answer is likely correct.
"""

from rondo.smart_return import normalize_response


def dispatch_mock(prompt: str, model: str, finds_bug: bool = True) -> dict:
    """Mock dispatch with controllable findings."""
    if finds_bug:
        return {
            "passed": False,
            "confidence": 0.9,
            "result": f"{model} found issues",
            "issues": ["SQL injection on line 42"],
            "_meta": {"quality": 8, "complete": True, "limitations": ""},
        }
    return {
        "passed": True,
        "confidence": 0.85,
        "result": f"{model} found no issues",
        "issues": [],
        "_meta": {"quality": 7, "complete": True, "limitations": ""},
    }


def review_with_tiebreaker(prompt: str) -> dict:
    """Two reviewers + optional tiebreaker if they disagree.

    The key: 'passed' and 'issues' fields let us detect disagreement
    programmatically. With text blobs, you'd need NLP to compare.
    """
    ## Ask two providers independently
    review_a = normalize_response(dispatch_mock(prompt, "gemini:flash", finds_bug=True))
    review_b = normalize_response(dispatch_mock(prompt, "grok:grok-3", finds_bug=False))

    print(f"  Gemini: passed={review_a['passed']}, issues={len(review_a['issues'])}")
    print(f"  Grok:   passed={review_b['passed']}, issues={len(review_b['issues'])}")

    ## Check agreement
    if review_a["passed"] == review_b["passed"]:
        print(f"  AGREE: both say passed={review_a['passed']}")
        return review_a  ## They agree — use either

    ## Disagreement — tiebreaker
    print(f"  DISAGREE: Gemini says {review_a['passed']}, Grok says {review_b['passed']}")
    print("  Calling tiebreaker (Mistral)...")

    review_c = normalize_response(dispatch_mock(prompt, "mistral:large", finds_bug=True))
    print(f"  Mistral: passed={review_c['passed']}, issues={len(review_c['issues'])}")

    ## Majority vote
    votes = [review_a["passed"], review_b["passed"], review_c["passed"]]
    majority = sum(votes) >= 2  ## True if 2+ say passed
    print(f"  MAJORITY VOTE: passed={majority} ({sum(votes)}/3 agree)")

    ## Return the review that matches majority
    if majority:
        return review_b  ## The one that said "passed"
    return review_a  ## The one that found issues (safer)


def main() -> None:
    """Demonstrate multi-AI tiebreaker pattern."""
    print("=== Multi-AI Tiebreaker Pattern ===")
    result = review_with_tiebreaker("Review this authentication handler")
    print(f"Final: passed={result['passed']}, issues={result['issues']}")


if __name__ == "__main__":
    main()


# -- sig: mgh-6201.cd.bd955f.ea13.1ea4b3
