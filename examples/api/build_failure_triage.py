# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Rondo example: deterministic triage + optional AI labels for new failures.

What this demonstrates
----------------------
* **Pure-Python** diff between baseline and current failures (regressions / known / fixed).
* **Optional** Rondo call per regression with a tiny classification prompt and ``rules=``.
* Clear separation so the script is useful even when API keys or ``claude`` are absent
  for the AI slice (catch :exc:`RuntimeError`).

Live AI calls use ``dry_run=False``. Use ``--no-ai`` for deterministic triage only (no spend).

Run::

    cd rondo && uv run python examples/api/build_failure_triage.py
    cd rondo && uv run python examples/api/build_failure_triage.py --no-ai
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

from example_dispatch import banner, run_prompt_json

BASELINE: list[dict[str, Any]] = [
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

CURRENT_FAILURES: list[dict[str, Any]] = [
    {"test": "test_subprocess_warning", "file": "tests/test_runner.py", "error": "DeprecationWarning: subprocess"},
    {"test": "test_smart_return_fields", "file": "tests/test_smart_return.py", "error": "KeyError: 'confidence'"},
    {
        "test": "test_hook_ordering",
        "file": "tests/test_hooks.py",
        "error": "AssertionError: post_dispatch fired before pre_dispatch",
    },
]


def triage_failures(
    baseline: list[dict[str, Any]],
    current: list[dict[str, Any]],
    *,
    use_ai: bool,
    timeout_sec: int,
) -> dict[str, Any]:
    """Diff + optional AI classification."""
    baseline_tests = {b["test"] for b in baseline}
    current_tests = {c["test"] for c in current}
    known, regressions, fixed = [], [], []

    print("  Deterministic triage:")
    for failure in current:
        if failure["test"] in baseline_tests:
            since = next((b["since"] for b in baseline if b["test"] == failure["test"]), "?")
            known.append({**failure, "since": since})
            print(f"    KNOWN: {failure['test']} (since {since})")
        else:
            regressions.append(dict(failure))
            print(f"    REGRESSION: {failure['test']}")

    for b in baseline:
        if b["test"] not in current_tests:
            fixed.append(b)
            print(f"    FIXED (was failing): {b['test']} ({b['since']})")

    if use_ai and regressions:
        print("  Optional AI labels (one short call per regression):")
        for reg in regressions:
            prompt = (
                f"Test failure: {reg['test']}\nError: {reg['error']}\n"
                f'Answer JSON only: {{"label": "regression" or "flaky", "reason": "one sentence"}}'
            )
            try:
                _, parsed = run_prompt_json(
                    prompt=prompt,
                    model="",
                    dry_run=False,
                    timeout_sec=timeout_sec,
                    rules='Reply JSON only: {"label":"regression"|"flaky","reason":"..."}',
                )
            except RuntimeError as exc:
                print(f"    -ERROR- {reg['test']}: {exc}", file=sys.stderr)
                reg["ai_classification"] = None
                continue

            if parsed.get("_non_json"):
                reg["ai_classification"] = None
                reg["ai_raw"] = str(parsed.get("snippet", ""))[:120]
                print(f"    {reg['test']}: non-JSON response (stored raw snippet on dict)")
            else:
                reg["ai_classification"] = parsed.get("label") or parsed.get("result")
                reg["ai_reason"] = str(parsed.get("reason", ""))[:200]
                print(f"    {reg['test']}: {reg.get('ai_classification')!r}")

    return {
        "known": len(known),
        "regressions": len(regressions),
        "fixed": len(fixed),
        "regression_list": regressions,
        "clean": len(regressions) == 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--no-ai", action="store_true", help="Deterministic triage only")
    parser.add_argument("--timeout", type=int, default=90, metavar="SEC")
    args = parser.parse_args()

    print(banner("Build failure triage (sample data)"))
    report = triage_failures(
        BASELINE,
        CURRENT_FAILURES,
        use_ai=not args.no_ai,
        timeout_sec=args.timeout,
    )
    print()
    if report["clean"]:
        print("-PASS- No regressions in sample set")
    else:
        print(f"-WARNING- {report['regressions']} regression(s) in sample set")
    if report["fixed"] > 0:
        print(f"-PASS- {report['fixed']} previously-known failure(s) cleared in sample")
    return 0 if report["clean"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
