"""Rondo Scripted Prompting: Budget-Aware Routing.

Start with the cheapest option (local Ollama = $0).
If it can't answer well enough, escalate to cloud.
Track spending and stop before exceeding budget.

This pattern minimizes cost while maintaining quality.
"""

from rondo.smart_return import normalize_response


def dispatch_mock(prompt: str, model: str, cost: float = 0.0, quality: int = 5) -> dict:
    """Mock dispatch with cost tracking."""
    return {
        "passed": quality >= 7,
        "confidence": quality / 10,
        "result": f"Answer from {model} (${cost:.3f})",
        "issues": [] if quality >= 7 else ["Answer incomplete"],
        "metadata": {"cost_usd": cost, "model": model},
        "_meta": {"quality": quality, "complete": quality >= 7, "limitations": ""},
    }


def review_within_budget(prompt: str, budget: float = 0.10) -> dict:
    """Route dispatch based on budget and quality needs.

    Tier 1: Local (free) — try first, always
    Tier 2: Cloud cheap (flash) — if local isn't good enough
    Tier 3: Cloud premium (opus) — only if budget allows
    """
    total_spent = 0.0

    ## Tier 1: Local model (FREE)
    result = normalize_response(dispatch_mock(prompt, "local:qwen32b", cost=0.0, quality=6))
    print(f"  Tier 1 (local, $0): quality={result['_meta']['quality']}/10")

    if result["passed"] and result["confidence"] >= 0.7:
        print(f"  Local is good enough — total cost: ${total_spent:.3f}")
        return result

    ## Tier 2: Cloud cheap
    cost_flash = 0.003
    if total_spent + cost_flash > budget:
        print("  Budget exceeded — returning local result")
        return result

    result = normalize_response(dispatch_mock(prompt, "gemini:flash", cost=cost_flash, quality=8))
    total_spent += cost_flash
    print(f"  Tier 2 (flash, ${cost_flash}): quality={result['_meta']['quality']}/10")

    if result["passed"] and result["confidence"] >= 0.8:
        print(f"  Flash is good enough — total cost: ${total_spent:.3f}")
        return result

    ## Tier 3: Premium (expensive)
    cost_opus = 0.05
    if total_spent + cost_opus > budget:
        print(f"  Budget limit — returning flash result (${total_spent:.3f} spent)")
        return result

    result = normalize_response(dispatch_mock(prompt, "opus", cost=cost_opus, quality=10))
    total_spent += cost_opus
    print(f"  Tier 3 (opus, ${cost_opus}): quality={result['_meta']['quality']}/10")
    print(f"  Total cost: ${total_spent:.3f}")
    return result


def main() -> None:
    """Demonstrate budget-aware routing."""
    print("=== Budget-Aware Routing ($0.10 limit) ===")
    result = review_within_budget("Explain quantum computing", budget=0.10)
    print(f"Final: quality={result['_meta']['quality']}/10, cost=${result.get('metadata', {}).get('cost_usd', 0):.3f}")


if __name__ == "__main__":
    main()


# -- sig: mgh-6201.cd.bd955f.ea14.1ea4b4
