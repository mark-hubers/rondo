"""Rondo Real-World: Build Failure Triage (New vs Pre-Existing).

REAL WORKFLOW THIS REPLACES:
  After every ace-build, Claude manually sorts through failures to
  determine which are pre-existing (known, deferred) vs new regressions
  introduced by the current sprint. "Pre-existing subprocess warnings"
  appears as a manual qualifier in 10+ sprint close messages.

SCRIPTED VERSION:
  Keep a baseline snapshot of known failures → after each build,
  diff actual failures against baseline → new failures get flagged
  as sprint regressions → pre-existing ones are suppressed →
  returns only net-new failures for the developer to act on.

THE DECISION LOGIC:
  - Failure matches baseline → KNOWN, suppress (don't alarm)
  - Failure is new → REGRESSION, create sprint finding
  - Baseline failure is gone → FIXED, celebrate (track improvement)
  - Failure is new but in deferred sprint → DEFERRED, note but don't block
"""

import sys

from rondo import smart_return


def _out(msg: str) -> None:
    """Write output line — examples are user-facing, not library code."""
    sys.stdout.write(msg + "\n")


## ─── Mock Data ───────────────────────────────────────────────────
## In production: baseline loaded from JSON file, build output parsed


def _get_baseline() -> list[dict]:
    """Load known failures baseline.

    In production: json.loads(Path("reports/failure-baseline.json").read_text())
    Updated after each sprint close when failures are triaged.
    """
    return [
        {
            "test": "test_subprocess_warning",
            "file": "tests/test_runner.py",
            "error": "DeprecationWarning: subprocess",
            "since": "FIX-590",
            "status": "deferred",
        },
        {
            "test": "test_ollama_timeout",
            "file": "tests/test_local_dispatch.py",
            "error": "ConnectionError: ollama not running",
            "since": "RONDO-180",
            "status": "known",
        },
        {
            "test": "test_gemini_rate_limit",
            "file": "tests/integration/test_providers.py",
            "error": "429 Too Many Requests",
            "since": "RONDO-200",
            "status": "known",
        },
    ]


def _get_build_failures() -> list[dict]:
    """Simulate current build output with mix of old and new failures.

    In production: parse ace-build output or pytest --json-report
    """
    return [
        ## Pre-existing (matches baseline)
        {
            "test": "test_subprocess_warning",
            "file": "tests/test_runner.py",
            "error": "DeprecationWarning: subprocess",
        },
        {
            "test": "test_ollama_timeout",
            "file": "tests/test_local_dispatch.py",
            "error": "ConnectionError: ollama not running",
        },
        ## NEW — regression introduced this sprint
        {
            "test": "test_smart_return_fields",
            "file": "tests/test_smart_return.py",
            "error": "KeyError: 'confidence' not in response",
        },
        ## NEW — another regression
        {
            "test": "test_hook_ordering",
            "file": "tests/test_hooks.py",
            "error": "AssertionError: post_dispatch fired before pre_dispatch",
        },
        ## NOTE: test_gemini_rate_limit is in baseline but NOT in current failures
        ## → this means it was FIXED (improvement!)
    ]


## ─── Failure Matching ────────────────────────────────────────────


def _failure_matches_baseline(failure: dict, baseline: list[dict]) -> dict | None:
    """Check if a failure matches a known baseline entry.

    Match on test name + file path. Error messages can vary slightly
    between runs, so we match on the stable identifiers.
    """
    for known in baseline:
        if failure["test"] == known["test"] and failure["file"] == known["file"]:
            return known
    return None


## ─── The Triage Pipeline ─────────────────────────────────────────


def triage_build_failures(sprint_id: str = "TEST-001") -> dict:
    """Diff build failures against baseline, classify each one.

    This is the REAL scripted workflow:
    1. Load known failure baseline (JSON snapshot)
    2. Get current build failures
    3. For each current failure: is it in the baseline?
       - YES → KNOWN (suppress, don't alarm)
       - NO → REGRESSION (new this sprint, create finding)
    4. For each baseline entry not in current failures:
       → FIXED (improvement! track it)
    5. Return only net-new regressions for developer action

    The AI step: for ambiguous matches (error text changed but test name
    same), ask AI "is this the same failure?" — here we use exact match.
    """
    baseline = _get_baseline()
    current = _get_build_failures()

    _out(f"  Baseline: {len(baseline)} known failures")
    _out(f"  Current build: {len(current)} failures")

    ## Step 1: Classify each current failure
    known: list[dict] = []
    regressions: list[dict] = []
    matched_baseline_tests: set[str] = set()

    for failure in current:
        match = _failure_matches_baseline(failure, baseline)
        if match:
            known.append({"failure": failure, "baseline": match})
            matched_baseline_tests.add(match["test"])
            _out(f"    KNOWN: {failure['test']} (since {match['since']})")
        else:
            regressions.append(failure)
            _out(f"    REGRESSION: {failure['test']} -> {failure['error'][:50]}")

    ## Step 2: Find fixed failures (in baseline but not in current)
    fixed: list[dict] = []
    for baseline_entry in baseline:
        if baseline_entry["test"] not in matched_baseline_tests:
            fixed.append(baseline_entry)
            _out(f"    FIXED: {baseline_entry['test']} (was {baseline_entry['since']})")

    ## Step 3: AI classification for ambiguous regressions
    ## In production: send ambiguous failures to AI for "is this related
    ## to changes in this sprint?" classification
    for reg in regressions:
        ai_result = smart_return.normalize_response(
            {
                "passed": False,
                "confidence": 0.9,
                "result": f"New failure in {reg['file']}",
                "issues": [reg["error"]],
                "_meta": {"quality": 8, "complete": True, "limitations": ""},
            }
        )
        reg["ai_confidence"] = ai_result["confidence"]
        reg["sprint"] = sprint_id

    _out("")
    _out(f"  Result: {len(known)} known, {len(regressions)} NEW, {len(fixed)} fixed")

    return {
        "sprint": sprint_id,
        "total_current": len(current),
        "known_count": len(known),
        "regression_count": len(regressions),
        "fixed_count": len(fixed),
        "regressions": regressions,
        "fixed": fixed,
        "clean_sprint": len(regressions) == 0,
    }


def main() -> None:
    """Demonstrate build failure triage pipeline."""
    _out("=== Build Failure Triage (New vs Pre-Existing) ===")
    _out("(Replaces: manually sorting 'pre-existing subprocess warnings')")
    _out("")

    report = triage_build_failures(sprint_id="RONDO-250")
    _out("")

    if report["clean_sprint"]:
        _out("-PASS- Clean sprint — no new regressions!")
    else:
        _out(f"-WARNING- {report['regression_count']} new regression(s) found:")
        for reg in report["regressions"]:
            _out(f"  {reg['test']}: {reg['error'][:60]}")

    if report["fixed"]:
        _out(f"-PASS- {report['fixed_count']} previously-known failure(s) now passing!")

    ## Verify triage worked correctly
    if report["regression_count"] < 1:
        _out("  -ERROR- Should detect at least 1 new regression")
        sys.exit(1)
    if report["fixed_count"] < 1:
        _out("  -ERROR- Should detect at least 1 fixed baseline failure")
        sys.exit(1)

    _out("")
    _out("The key: baseline snapshot separates signal from noise.")
    _out("Only net-new failures need developer attention.")


if __name__ == "__main__":
    main()


# -- sig: mgh-6201.cd.bd955f.ea23.1ea523
