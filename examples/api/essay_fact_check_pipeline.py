"""Rondo Real-World: Essay Fact-Check Pipeline.

REAL WORKFLOW THIS REPLACES:
  Before publishing an essay, Mark runs a fact-check pass. An agent
  reviewed 62 claims in one session — but gave wrong verdicts. Called
  things "unverified" that WERE in local files. Missed a 2015 ARVO
  source. Mark had to re-verify the agent's output manually. 685
  fact-check messages in 90 days.

SCRIPTED VERSION:
  Extract claims from essay -> check local data FIRST (cheap, accurate)
  -> only hit web for unresolved claims -> flag conflicts between
  local and web data -> return structured verdict per claim.

THE DECISION LOGIC:
  - Claim verified by local data -> VERIFIED, done (no web call needed)
  - Claim not in local data -> check web sources
  - Web confirms -> VERIFIED (with web source)
  - Web contradicts local -> CONFLICT (flag for Mark, HIGH priority)
  - Neither local nor web has data -> UNVERIFIED (flag for review)
  - Key: LOCAL FIRST. Cheaper, faster, more reliable for Mark's domain.
"""

import sys

from rondo import smart_return


def _out(msg: str) -> None:
    """Write output line — examples are user-facing, not library code."""
    sys.stdout.write(msg + "\n")


## ─── Mock Claim Extraction ───────────────────────────────────────
## In production: rondo_run("Extract all factual claims from this essay")


def _mock_extract_claims(essay_path: str) -> list[dict]:
    """Simulate extracting factual claims from an essay.

    In production: send essay text to local LLM (8B, free) to pull
    out every statement that asserts a fact, number, or date.
    """
    _ = essay_path
    return [
        {
            "id": 1,
            "text": "Usher syndrome affects approximately 25,000 people in the US",
            "type": "prevalence",
        },
        {
            "id": 2,
            "text": "USH2A is the most common gene associated with Usher Type 2",
            "type": "genetics",
        },
        {
            "id": 3,
            "text": "Ray Therapeutics received RMAT designation for RTx-015 in April 2026",
            "type": "clinical",
        },
        {
            "id": 4,
            "text": "Retinitis pigmentosa causes progressive vision loss starting in adolescence",
            "type": "medical",
        },
        {
            "id": 5,
            "text": "The USH2A gene is located on chromosome 1q41",
            "type": "genetics",
        },
    ]


## ─── Mock Local Data Check ──────────────────────────────────────
## In production: search local research/ files, ChromaDB vectors,
## or BioMCP queries against Mark's curated data


def _mock_local_check(claim: dict) -> dict:
    """Simulate checking a claim against local research files.

    In production: search local files first (Mark's curated data is
    more reliable than web for USH-specific facts).
    """
    local_data = {
        1: {
            "found": True,
            "source": "research/prevalence-data.md",
            "note": "Mark's data says 30,400 based on Kimberling 2010",
            "matches": False,
        },
        2: {
            "found": True,
            "source": "research/genetics-overview.md",
            "note": "Confirmed: USH2A is most common USH2 gene (68%)",
            "matches": True,
        },
        3: {
            "found": False,
            "source": None,
            "note": "Not in local files — too recent",
            "matches": False,
        },
        4: {
            "found": True,
            "source": "research/rp-progression.md",
            "note": "Confirmed: RP starts with night blindness in adolescence",
            "matches": True,
        },
        5: {
            "found": True,
            "source": "research/gene-locations.md",
            "note": "Confirmed: 1q41",
            "matches": True,
        },
    }
    return local_data.get(
        claim["id"],
        {"found": False, "source": None, "note": "No data", "matches": False},
    )


## ─── Mock Web Check ─────────────────────────────────────────────
## In production: BioMCP article search, PubMed API, ClinicalTrials.gov


def _mock_web_check(claim: dict) -> dict:
    """Simulate checking a claim against web sources.

    In production: use BioMCP or web search. Only called for claims
    not resolved by local data (saves API calls and money).
    """
    web_data = {
        1: {
            "found": True,
            "source": "NIDCD prevalence page",
            "note": "NIDCD says 25,000 — contradicts Mark's 30,400",
            "matches": True,
        },
        3: {
            "found": True,
            "source": "FDA RMAT database, April 2026",
            "note": "Confirmed: RTx-015 RMAT designation granted",
            "matches": True,
        },
    }
    return web_data.get(
        claim["id"],
        {"found": False, "source": None, "note": "Not found", "matches": False},
    )


## ─── The Pipeline ────────────────────────────────────────────────


def fact_check_essay(essay_path: str = "essays/usher-syndrome.md") -> dict:
    """Full pipeline: extract claims -> local check -> web check -> verdicts.

    This is the REAL scripted workflow:
    1. Extract all factual claims from essay (local LLM, cheap)
    2. For EACH claim, check local data first (free, fast, reliable)
    3. If local confirms -> VERIFIED, skip web call (save money)
    4. If local has data but DISAGREES -> CONFLICT (high priority!)
    5. If local has no data -> check web sources (costs API calls)
    6. If web confirms -> VERIFIED with web source
    7. If BOTH local and web have data and they disagree -> CONFLICT
    8. If neither has data -> UNVERIFIED (flag for review)
    """
    _out(f"  Checking: {essay_path}")

    ## Step 1: Extract claims
    claims = _mock_extract_claims(essay_path)
    _out(f"  Found {len(claims)} factual claims")

    ## Step 2: Check each claim (local first, web only if needed)
    results: list[dict] = []
    web_calls = 0

    for claim in claims:
        local = _mock_local_check(claim)

        if local["found"] and local["matches"]:
            ## Local data confirms — no web call needed
            results.append(
                {
                    "claim_id": claim["id"],
                    "text": claim["text"][:60],
                    "verdict": "VERIFIED",
                    "source": f"LOCAL: {local['source']}",
                    "note": local["note"],
                }
            )
            _out(f"    VERIFIED (local): claim {claim['id']} — {local['note'][:50]}")
            continue

        if local["found"] and not local["matches"]:
            ## Local data DISAGREES with the essay claim
            web = _mock_web_check(claim)
            web_calls += 1

            if web["found"] and web["matches"]:
                ## Web agrees with essay but local disagrees — CONFLICT
                results.append(
                    {
                        "claim_id": claim["id"],
                        "text": claim["text"][:60],
                        "verdict": "CONFLICT",
                        "source": f"LOCAL: {local['source']} vs WEB: {web['source']}",
                        "note": f"Essay says: {claim['text'][:40]}. Local says: {local['note'][:40]}",
                    }
                )
                _out(f"    CONFLICT: claim {claim['id']} — local vs web disagree")
            else:
                ## Local disagrees, web has no opinion — trust local
                results.append(
                    {
                        "claim_id": claim["id"],
                        "text": claim["text"][:60],
                        "verdict": "NEEDS_REVIEW",
                        "source": f"LOCAL: {local['source']}",
                        "note": f"Local data differs: {local['note'][:50]}",
                    }
                )
                _out(f"    NEEDS_REVIEW: claim {claim['id']} — local data differs")
            continue

        ## Local has no data — check web
        web = _mock_web_check(claim)
        web_calls += 1

        if web["found"]:
            normalized = smart_return.normalize_response(
                {
                    "passed": web["matches"],
                    "confidence": 0.85,
                    "result": web["note"],
                    "issues": [] if web["matches"] else [web["note"]],
                    "_meta": {"quality": 7, "complete": True, "limitations": "Web only"},
                }
            )
            results.append(
                {
                    "claim_id": claim["id"],
                    "text": claim["text"][:60],
                    "verdict": "VERIFIED" if normalized["passed"] else "NEEDS_REVIEW",
                    "source": f"WEB: {web['source']}",
                    "note": web["note"],
                }
            )
            _out(f"    VERIFIED (web): claim {claim['id']} — {web['note'][:50]}")
        else:
            results.append(
                {
                    "claim_id": claim["id"],
                    "text": claim["text"][:60],
                    "verdict": "UNVERIFIED",
                    "source": "NONE",
                    "note": "No data in local files or web sources",
                }
            )
            _out(f"    UNVERIFIED: claim {claim['id']} — no data found anywhere")

    ## Summary
    verified = [r for r in results if r["verdict"] == "VERIFIED"]
    conflicts = [r for r in results if r["verdict"] == "CONFLICT"]
    unverified = [r for r in results if r["verdict"] == "UNVERIFIED"]
    needs_review = [r for r in results if r["verdict"] == "NEEDS_REVIEW"]

    _out("")
    _out(
        f"  Summary: {len(verified)} verified, {len(conflicts)} conflicts,"
        f" {len(unverified)} unverified, {len(needs_review)} needs review"
    )
    _out(f"  Web API calls: {web_calls} (saved {len(claims) - web_calls} by checking local first)")

    return {
        "essay": essay_path,
        "total_claims": len(claims),
        "verified": len(verified),
        "conflicts": len(conflicts),
        "unverified": len(unverified),
        "needs_review": len(needs_review),
        "web_calls_made": web_calls,
        "web_calls_saved": len(claims) - web_calls,
        "safe_to_publish": len(conflicts) == 0 and len(unverified) == 0,
        "results": results,
    }


def main() -> None:
    """Demonstrate essay fact-check pipeline."""
    _out("=== Essay Fact-Check Pipeline ===")
    _out("(Replaces: agent gave wrong verdicts, Mark re-verified manually)")
    _out("")

    report = fact_check_essay()
    _out("")

    if report["safe_to_publish"]:
        _out("-PASS- All claims verified — safe to publish")
    else:
        _out("-WARNING- Issues found before publishing:")
        for r in report["results"]:
            if r["verdict"] in ("CONFLICT", "UNVERIFIED", "NEEDS_REVIEW"):
                _out(f"  [{r['verdict']}] Claim {r['claim_id']}: {r['note'][:60]}")

    ## Verify the pipeline caught the real issues
    if report["conflicts"] < 1:
        _out("  -ERROR- Should detect the prevalence number conflict")
        sys.exit(1)
    if report["web_calls_saved"] < 1:
        _out("  -ERROR- Local-first should save at least 1 web call")
        sys.exit(1)

    _out("")
    _out("The key: LOCAL DATA FIRST. Cheaper, faster, and Mark's data")
    _out("is more reliable than web for USH-specific facts.")


if __name__ == "__main__":
    main()


# -- sig: mgh-6201.cd.bd955f.ea24.1ea524
