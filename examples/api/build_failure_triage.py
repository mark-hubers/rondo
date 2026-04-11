"""Rondo Real-World: Build Failure Triage (New vs Pre-Existing).

REAL WORKFLOW THIS REPLACES:
  After every ace-build, manually sort failures into pre-existing vs new.

SCRIPTED VERSION:
  Diff current failures against baseline -> flag regressions ->
  ask AI to classify ambiguous failures.

HOW TO RUN:
  python examples/api/build_failure_triage.py
"""

import json
import sys

from rondo import mcp_dispatch


def _out(msg: str) -> None:
    """Write output line."""
    sys.stdout.write(msg + "\n")


def dispatch(prompt: str, **kwargs: str | int) -> dict | None:
    """Dispatch prompt via Rondo inline subprocess (free on Max)."""
    raw = mcp_dispatch.rondo_run_file(
        prompt=prompt,
        model="",
        dry_run=False,
        timeout_sec=60,
        _session=object(),
        **kwargs,
    )
    data = json.loads(raw)
    tasks = data.get("tasks", [])
    if not tasks or tasks[0].get("status") == "error":
        return None
    output = tasks[0].get("raw_output", "")
    try:
        return json.loads(output)
    except json.JSONDecodeError:
        return {"result": output, "passed": None, "issues": [], "confidence": 0.0}


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
    {"test": "test_smart_return_fields", "file": "tests/test_smart_return.py", "error": "KeyError: 'confidence'"},
    {
        "test": "test_hook_ordering",
        "file": "tests/test_hooks.py",
        "error": "AssertionError: post_dispatch fired before pre_dispatch",
    },
]


def triage_failures(baseline: list[dict], current: list[dict]) -> dict:
    """Diff current failures against baseline, classify with AI."""
    baseline_tests = {b["test"] for b in baseline}
    current_tests = {c["test"] for c in current}
    known, regressions, fixed = [], [], []

    for failure in current:
        if failure["test"] in baseline_tests:
            since = next((b["since"] for b in baseline if b["test"] == failure["test"]), "?")
            known.append({**failure, "since": since})
            _out(f"    KNOWN: {failure['test']} (since {since})")
        else:
            regressions.append(failure)
            _out(f"    REGRESSION: {failure['test']}")

    for b in baseline:
        if b["test"] not in current_tests:
            fixed.append(b)
            _out(f"    FIXED: {b['test']} (was {b['since']})")

    ## AI classification of regressions
    for reg in regressions:
        result = dispatch(
            f"Is this a real regression or flaky test? {reg['test']}: {reg['error']}. Answer: regression or flaky.",
            rules="Classify test failures. One word answer: regression or flaky.",
        )
        if result:
            reg["ai_classification"] = str(result.get("result", ""))[:50]

    return {
        "known": len(known),
        "regressions": len(regressions),
        "fixed": len(fixed),
        "regression_list": regressions,
        "clean": len(regressions) == 0,
    }


def main() -> None:
    """Run build failure triage."""
    _out("=== Build Failure Triage ===")
    _out("")
    report = triage_failures(BASELINE, CURRENT_FAILURES)
    _out("")
    if report["clean"]:
        _out("-PASS- Clean sprint")
    else:
        _out(f"-WARNING- {report['regressions']} regression(s)")
    if report["fixed"] > 0:
        _out(f"-PASS- {report['fixed']} previously-known failure(s) now passing")


if __name__ == "__main__":
    main()


# -- sig: mgh-6201.cd.bd955f.ea23.1ea523
