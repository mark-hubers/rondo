"""Rondo Real-World: Community Reply + Variant Lookup.

REAL WORKFLOW THIS REPLACES:
  Community members (Heidi, Pam, Dulce, Keith) message Mark with
  questions about genetics, testing, and trials. Mark pastes the
  message, Claude fact-checks what the person got wrong, drafts a
  reply in Mark's voice, and finds the relevant essay to link.
  123+ messages with this exact pattern. Same structure every time,
  different inputs.

SCRIPTED VERSION:
  Incoming message -> classify question type -> check facts against
  local data -> look up variant in ClinVar if mentioned -> find
  matching active trials -> draft reply in Mark's voice -> link
  relevant published essay.

THE DECISION LOGIC:
  - Message mentions a gene variant -> lookup in ClinVar + local DB
  - Message has factual errors -> correct gently in reply
  - Message asks about trials -> search ClinicalTrials.gov by gene
  - Message asks about testing -> find "Know Your Gene" essay
  - Always: draft in Mark's voice (short, no jargon, personal)
  - Always: find most relevant published essay to link
"""

import sys

from rondo import smart_return


def _out(msg: str) -> None:
    """Write output line -- examples are user-facing, not library code."""
    sys.stdout.write(msg + "\n")


## --- Mock Message Classification ---------------------------------
## In production: rondo_run with local 8B model


def _mock_classify(message: str) -> dict:
    """Classify incoming community message by question type.

    Categories: genetics, testing, trials, living_with, general
    """
    _ = message
    return {
        "passed": True,
        "confidence": 0.92,
        "result": "genetics",
        "issues": [],
        "_meta": {"quality": 8, "complete": True, "limitations": ""},
    }


## --- Mock Fact Check ---------------------------------------------


def _mock_fact_check(message: str) -> list[dict]:
    """Check incoming message for factual errors.

    In production: extract claims, verify against local research DB.
    """
    _ = message
    return [
        {
            "claim": "both parents must be tested to confirm Usher syndrome",
            "correct": False,
            "correction": "Genetic testing of the affected individual is sufficient. "
            "Parent testing helps identify carrier status but is not required for diagnosis.",
            "source": "research/genetic-testing-guide.md",
        },
        {
            "claim": "USH2A causes hearing loss that gets worse over time",
            "correct": False,
            "correction": "USH2 hearing loss is typically stable (non-progressive). "
            "It is the vision loss from RP that is progressive.",
            "source": "research/ush2-overview.md",
        },
    ]


## --- Mock Variant Lookup -----------------------------------------


def _mock_variant_lookup(variant_id: str) -> dict:
    """Look up a genetic variant in ClinVar + local database.

    In production: BioMCP variant_getter + local variant DB
    """
    _ = variant_id
    return {
        "variant": "c.2299delG",
        "gene": "USH2A",
        "classification": "Pathogenic",
        "condition": "Usher syndrome type 2A",
        "frequency": "Most common USH2A variant in European populations",
        "source": "ClinVar: RCV000018281",
        "found": True,
    }


## --- Mock Trial Search -------------------------------------------


def _mock_trial_search(gene: str) -> list[dict]:
    """Search for active clinical trials matching a gene.

    In production: BioMCP trial_searcher or ClinicalTrials.gov API
    """
    _ = gene
    return [
        {
            "nct_id": "NCT06283446",
            "title": "Gene Therapy for USH2A-Related Retinitis Pigmentosa",
            "status": "RECRUITING",
            "phase": "Phase 1/2",
            "sponsor": "Ray Therapeutics",
        },
        {
            "nct_id": "NCT05085613",
            "title": "Natural History Study of Usher Syndrome",
            "status": "RECRUITING",
            "phase": "Observational",
            "sponsor": "Foundation Fighting Blindness",
        },
    ]


## --- Mock Essay Index --------------------------------------------


def _mock_find_essay(topic: str) -> dict:
    """Find the most relevant published essay for linking.

    In production: search essay-index.md or semantic search
    """
    _ = topic
    return {
        "title": "Know Your Gene: A Guide for the USH Community",
        "url": "https://markhubers.substack.com/p/know-your-gene",
        "relevance": 0.95,
        "published": "2026-03-15",
    }


## --- Reply Drafter -----------------------------------------------


def _mock_draft_reply(
    corrections: list[dict],
    variant_info: dict,
    trials: list[dict],
    essay: dict,
) -> str:
    """Draft a reply in Mark's voice.

    Rules: short, no jargon, correct gently (never condescending),
    personal tone, always link to essay for more detail.
    """
    parts = ["Hey! Great questions. Let me share what I know."]

    ## Gentle corrections
    for c in corrections:
        parts.append(f"One thing to note: {c['correction']}")

    ## Variant info
    if variant_info.get("found"):
        parts.append(
            f"The {variant_info['variant']} variant is classified as "
            f"{variant_info['classification']}. {variant_info['frequency']}."
        )

    ## Active trials
    if trials:
        recruiting = [t for t in trials if t["status"] == "RECRUITING"]
        if recruiting:
            parts.append(
                f"There are {len(recruiting)} active trials for USH2A right now, "
                f"including a {recruiting[0]['phase']} from {recruiting[0]['sponsor']}."
            )

    ## Essay link
    parts.append(f"I wrote about this in detail here: {essay['url']}")

    return " ".join(parts)


## --- The Pipeline ------------------------------------------------


def handle_community_message(
    message: str,
    variant_id: str = "c.2299delG",
) -> dict:
    """Full pipeline: incoming message -> fact-check -> lookup -> reply.

    This is the REAL scripted workflow:
    1. Classify the question type (genetics/testing/trials/living_with)
    2. Check for factual errors in the message
    3. If variant mentioned -> ClinVar lookup
    4. If gene identified -> search active trials
    5. Find most relevant published essay to link
    6. Draft reply in Mark's voice with gentle corrections
    7. Return ready-to-send reply with all source data
    """
    _out(f"  Message: {message[:60]}...")

    ## Step 1: Classify
    classification = smart_return.normalize_response(_mock_classify(message))
    category = classification["result"]
    _out(f"  Category: {category} (confidence={classification['confidence']})")

    ## Step 2: Fact-check incoming message
    errors = _mock_fact_check(message)
    _out(f"  Fact-check: {len(errors)} corrections needed")
    for err in errors:
        _out(f"    WRONG: {err['claim'][:50]}...")
        _out(f"    RIGHT: {err['correction'][:50]}...")

    ## Step 3: Variant lookup (if genetics question)
    variant_info: dict = {}
    if category == "genetics" and variant_id:
        variant_info = _mock_variant_lookup(variant_id)
        if variant_info["found"]:
            _out(f"  Variant: {variant_info['variant']} = {variant_info['classification']}")
        else:
            _out(f"  Variant: {variant_id} not found in ClinVar")

    ## Step 4: Trial search
    gene = variant_info.get("gene", "USH2A")
    trials = _mock_trial_search(gene)
    recruiting = [t for t in trials if t["status"] == "RECRUITING"]
    _out(f"  Trials: {len(recruiting)} recruiting for {gene}")

    ## Step 5: Find relevant essay
    essay = _mock_find_essay(category)
    _out(f"  Essay: {essay['title']}")

    ## Step 6: Draft reply
    reply = _mock_draft_reply(errors, variant_info, trials, essay)
    _out(f"  Reply draft: {len(reply)} chars")

    return {
        "category": category,
        "corrections": len(errors),
        "variant_found": variant_info.get("found", False),
        "trials_found": len(recruiting),
        "essay_linked": essay["title"],
        "reply": reply,
        "reply_length": len(reply),
        "ready_to_send": True,
    }


def main() -> None:
    """Demonstrate community reply + variant lookup pipeline."""
    _out("=== Community Reply + Variant Lookup ===")
    _out("(Replaces: paste message -> fact-check -> lookup -> draft reply)")
    _out("")

    ## Simulate a real community message (based on actual pattern from Heidi)
    message = (
        "Hi Mark, my daughter was just diagnosed with Usher syndrome. "
        "They found c.2299delG in her USH2A gene. We were told both "
        "parents must be tested to confirm. Is her hearing loss going "
        "to get worse? Are there any trials she could join?"
    )

    result = handle_community_message(message, variant_id="c.2299delG")
    _out("")
    _out("--- Draft Reply ---")
    _out(result["reply"])
    _out("---")
    _out("")
    _out(f"Corrections: {result['corrections']}")
    _out(f"Variant found: {result['variant_found']}")
    _out(f"Trials found: {result['trials_found']}")
    _out(f"Essay linked: {result['essay_linked']}")

    ## Verify pipeline produced a usable reply
    if result["reply_length"] < 50:
        _out("  -ERROR- Reply too short to be useful")
        sys.exit(1)
    if result["corrections"] < 1:
        _out("  -ERROR- Should catch at least 1 factual error")
        sys.exit(1)

    _out("")
    _out("The key: same structure every time, different inputs.")
    _out("Fact-check, lookup, draft -- all scripted.")


if __name__ == "__main__":
    main()


# -- sig: mgh-6201.cd.bd955f.ea26.1ea526
