"""Rondo Real-World: Build Failure Triage (New vs Pre-Existing).

REAL WORKFLOW THIS REPLACES:
  After every ace-build, manually sort failures into pre-existing
  vs new regressions. Every sprint close.

SCRIPTED VERSION:
  Diff current failures against known baseline -> new failures
  flagged as regressions -> baseline failures suppressed ->
  optionally ask AI to classify ambiguous failures.

HOW TO RUN:
  python examples/api/build_failure_triage.py
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
    """Real AI dispatch via Rondo."""
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


## --- Sample Data (real failure shapes from actual builds) ---------

BASELINE = [
    {
        "test": "test_subprocess_warning",
        "file": "tests/test_runner.py",
        "error": "DeprecationWarning: subprocess",
        "since": "FIX-590",
    },
    {
        "test": "test_ollama_timeout",
        "file": "tests/test_local_dispatch.py",
        "error": "ConnectionError: ollama not running",
        "since": "RONDO-180",
    },
]

CURRENT_FAILURES = [
    {"test": "test_subprocess_warning", "file": "tests/test_runner.py", "error": "DeprecationWarning: subprocess"},
    {
        "test": "test_smart_return_fields",
        "file": "tests/test_smart_return.py",
        "error": "KeyError: 'confidence' not in response",
    },
    {
        "test": "test_hook_ordering",
        "file": "tests/test_hooks.py",
        "error": "AssertionError: post_dispatch fired before pre_dispatch",
    },
]

CLASSIFY_PROMPT = """This test failure appeared in a new sprint. Is it likely:
1. A real regression (new bug introduced this sprint)
2. A flaky test (intermittent failure, not a real bug)
3. An environment issue (missing dependency, config)

Return JSON: {{"classification": "regression"|"flaky"|"environment", "confidence": 0.9, "reason": "why"}}

Test: {test}
Error: {error}"""


## --- The Triage Pipeline -----------------------------------------


def triage_failures(baseline: list[dict], current: list[dict], sprint_id: str = "EXAMPLE-001") -> dict:
    """Diff current failures against baseline, classify new ones with AI."""
    baseline_tests = {b["test"] for b in baseline}
    current_tests = {c["test"] for c in current}

    known: list[dict] = []
    regressions: list[dict] = []
    fixed: list[dict] = []

    ## Step 1: Classify each current failure
    for failure in current:
        if failure["test"] in baseline_tests:
            since = next((b["since"] for b in baseline if b["test"] == failure["test"]), "unknown")
            known.append({**failure, "since": since})
            _out(f"    KNOWN: {failure['test']} (since {since})")
        else:
            regressions.append(failure)
            _out(f"    REGRESSION: {failure['test']} -> {failure['error'][:50]}")

    ## Step 2: Find fixed failures
    for b in baseline:
        if b["test"] not in current_tests:
            fixed.append(b)
            _out(f"    FIXED: {b['test']} (was {b['since']})")

    ## Step 3: AI classification of regressions
    for reg in regressions:
        prompt = CLASSIFY_PROMPT.format(test=reg["test"], error=reg["error"])
        result = _dispatch(prompt)
        if result:
            reg["ai_classification"] = result.get("result", "unknown")
            reg["ai_confidence"] = result.get("confidence", 0.0)
            _out(f"      AI: {result.get('result', '')[:50]}")
        reg["sprint"] = sprint_id

    return {
        "sprint": sprint_id,
        "known_count": len(known),
        "regression_count": len(regressions),
        "fixed_count": len(fixed),
        "regressions": regressions,
        "fixed": fixed,
        "clean_sprint": len(regressions) == 0,
    }


def main() -> None:
    """Demonstrate build failure triage."""
    _out("=== Build Failure Triage (New vs Pre-Existing) ===")
    _out("")

    _out("  Baseline: 2 known failures")
    _out("  Current: 3 failures")
    report = triage_failures(BASELINE, CURRENT_FAILURES)
    _out("")

    if report["clean_sprint"]:
        _out("-PASS- Clean sprint")
    else:
        _out(f"-WARNING- {report['regression_count']} new regression(s)")
        for reg in report["regressions"]:
            _out(f"  {reg['test']}: {reg['error'][:60]}")

    if report["fixed"]:
        _out(f"-PASS- {report['fixed_count']} previously-known failure(s) now passing!")


if __name__ == "__main__":
    main()


# -- sig: mgh-6201.cd.bd955f.ea23.1ea523
