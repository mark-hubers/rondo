"""Rondo Real-World: Multi-Platform Publish Pipeline.

REAL WORKFLOW THIS REPLACES:
  After every essay publish, Mark needs 4 separate posts:
  Substack (full essay), LinkedIn (1,500 chars, his voice rules),
  Facebook/Blue Book (300 chars, casual), and Substack subtitle.
  Each platform requires different format, length, and voice.
  4,500+ messages on publishing workflows in 90 days — the highest
  volume pattern in the entire chat history.

SCRIPTED VERSION:
  Input essay -> extract thesis + key data -> generate all 4 platform
  variants in one pass -> quality check each against platform rules
  -> flag any that fail voice/length checks -> return ready-to-post set.

THE DECISION LOGIC:
  - Extract thesis (local LLM, free) -> feeds all 4 generators
  - LinkedIn: must be <= 1,500 chars, Mark's voice, no em dashes
  - Facebook: must be <= 300 chars, casual community tone
  - Substack subtitle: one compelling line, <= 100 chars
  - If any variant fails rules -> regenerate with stricter constraints
  - If regeneration still fails -> flag for manual edit
"""

import sys

from rondo import smart_return


def _out(msg: str) -> None:
    """Write output line — examples are user-facing, not library code."""
    sys.stdout.write(msg + "\n")


## ─── Platform Rules ──────────────────────────────────────────────
## These are Mark's REAL rules from documented preferences

PLATFORM_RULES = {
    "linkedin": {
        "max_chars": 1500,
        "voice": "professional but personal, first person",
        "forbidden": ["em dash", "\u2014"],
        "required": ["data point", "personal connection"],
    },
    "facebook": {
        "max_chars": 300,
        "voice": "casual, community tone, like talking to friends",
        "forbidden": ["jargon", "clinical terms without explanation"],
        "required": ["link to full essay"],
    },
    "substack_subtitle": {
        "max_chars": 100,
        "voice": "compelling, draws reader in",
        "forbidden": ["clickbait"],
        "required": [],
    },
}


## ─── Mock AI Generators ─────────────────────────────────────────


def _mock_extract_thesis(essay_path: str) -> dict:
    """Simulate extracting thesis and key data from essay.

    In production: rondo_run with local 8B model (free).
    """
    _ = essay_path
    return {
        "thesis": "Usher syndrome research is accelerating with 3 gene therapies now in trials",
        "key_data": [
            "3 gene therapy trials active in 2026",
            "RTx-015 received RMAT designation",
            "25,000+ Americans affected",
        ],
        "tone": "hopeful but grounded in data",
    }


def _mock_generate_variant(thesis: dict, platform: str, attempt: int = 0) -> dict:
    """Simulate generating a platform-specific post variant.

    In production: rondo_run with platform-specific prompt template.
    Attempt > 0 means regeneration with stricter rules.
    """
    _ = thesis  ## In production: used to seed the prompt
    variants = {
        "linkedin": {
            0: (
                "Three gene therapy trials are now active for Usher syndrome in 2026. "
                "As someone living with USH2, watching RTx-015 receive RMAT designation "
                "from the FDA feels deeply personal. This is not abstract science. "
                "These are therapies that could preserve the remaining vision I have. "
                "The research community has gone from 'maybe someday' to 'active trials "
                "with real patients.' Here is what the data shows and why it matters."
            ),
            1: (
                "Three gene therapy trials are active for Usher syndrome. As someone "
                "with USH2, the RTx-015 RMAT designation is personal. These trials "
                "could preserve remaining vision. The data is real."
            ),
        },
        "facebook": {
            0: (
                "Big news in Usher syndrome research! 3 gene therapy trials are now "
                "active. If you or someone you love has USH, this matters. Read the "
                "full breakdown in my latest essay: [link]"
            ),
        },
        "substack_subtitle": {
            0: "Three gene therapies, one designation, and what it means for our community",
        },
    }
    platform_variants = variants.get(platform, {})
    text = platform_variants.get(attempt, platform_variants.get(0, "Generated text"))
    if isinstance(text, tuple):
        text = text[0] if attempt == 0 else text[1]

    return {
        "passed": True,
        "confidence": 0.9 if attempt == 0 else 0.95,
        "result": text,
        "issues": [],
        "_meta": {"quality": 8, "complete": True, "limitations": ""},
    }


## ─── Quality Checker ─────────────────────────────────────────────


def _check_platform_rules(text: str, platform: str) -> dict:
    """Check if generated text meets platform-specific rules.

    Returns pass/fail with specific violations found.
    """
    rules = PLATFORM_RULES.get(platform, {})
    violations: list[str] = []

    ## Length check
    max_chars = rules.get("max_chars", 9999)
    if len(text) > max_chars:
        violations.append(f"Too long: {len(text)}/{max_chars} chars")

    ## Forbidden content check
    for forbidden in rules.get("forbidden", []):
        if forbidden.lower() in text.lower():
            violations.append(f"Contains forbidden: '{forbidden}'")

    return {
        "passed": len(violations) == 0,
        "length": len(text),
        "max_length": max_chars,
        "violations": violations,
    }


## ─── The Pipeline ────────────────────────────────────────────────


def generate_all_variants(
    essay_path: str = "essays/usher-syndrome.md",
    max_regenerations: int = 2,
) -> dict:
    """Generate all platform variants from one essay.

    This is the REAL scripted workflow:
    1. Extract thesis + key data from essay (local LLM, free)
    2. Generate each platform variant using thesis as seed
    3. Quality-check each against platform rules
    4. If fails rules -> regenerate with stricter constraints
    5. If still fails after max retries -> flag for manual edit
    6. Return all variants ready for review + one-click post
    """
    _out(f"  Input: {essay_path}")

    ## Step 1: Extract thesis
    thesis = _mock_extract_thesis(essay_path)
    _out(f"  Thesis: {thesis['thesis'][:60]}...")
    _out(f"  Key data points: {len(thesis['key_data'])}")

    ## Step 2: Generate each variant with quality gate
    variants: dict[str, dict] = {}
    platforms = ["linkedin", "facebook", "substack_subtitle"]

    for platform in platforms:
        _out(f"  Generating {platform}...")

        for attempt in range(max_regenerations + 1):
            ## Generate
            raw = _mock_generate_variant(thesis, platform, attempt)
            normalized = smart_return.normalize_response(raw)
            text = normalized["result"]

            ## Quality check
            check = _check_platform_rules(text, platform)

            if check["passed"]:
                variants[platform] = {
                    "text": text,
                    "length": check["length"],
                    "max_length": check["max_length"],
                    "attempts": attempt + 1,
                    "status": "READY",
                }
                _out(f"    -PASS- {check['length']}/{check['max_length']} chars, attempt {attempt + 1}")
                break

            ## Failed — regenerate with stricter rules
            _out(f"    RETRY: {', '.join(check['violations'])} (attempt {attempt + 1})")

            if attempt == max_regenerations:
                ## Max retries — flag for manual edit
                variants[platform] = {
                    "text": text,
                    "length": check["length"],
                    "max_length": check["max_length"],
                    "attempts": attempt + 1,
                    "violations": check["violations"],
                    "status": "NEEDS_EDIT",
                }
                _out("    -WARNING- Max retries — needs manual edit")

    ## Summary
    ready = [p for p, v in variants.items() if v["status"] == "READY"]
    needs_edit = [p for p, v in variants.items() if v["status"] == "NEEDS_EDIT"]

    _out("")
    _out(f"  Result: {len(ready)} ready, {len(needs_edit)} need editing")

    return {
        "essay": essay_path,
        "thesis": thesis["thesis"],
        "total_platforms": len(platforms),
        "ready_count": len(ready),
        "needs_edit_count": len(needs_edit),
        "all_ready": len(needs_edit) == 0,
        "variants": variants,
    }


def main() -> None:
    """Demonstrate multi-platform publish pipeline."""
    _out("=== Multi-Platform Publish Pipeline ===")
    _out("(Replaces: separate LinkedIn + FB + Substack drafts per essay)")
    _out("")

    result = generate_all_variants()
    _out("")

    ## Show each variant preview
    for platform, variant in result["variants"].items():
        status = variant["status"]
        length = variant["length"]
        _out(f"  {platform} [{status}] ({length} chars):")
        _out(f"    {variant['text'][:80]}...")
        _out("")

    ## Verify pipeline generated usable output
    if result["ready_count"] < 2:
        _out("  -ERROR- Should have at least 2 ready variants")
        sys.exit(1)

    _out("The key: one essay in, all platform variants out.")
    _out("AI generates, Python enforces platform rules.")


if __name__ == "__main__":
    main()


# -- sig: mgh-6201.cd.bd955f.ea25.1ea525
