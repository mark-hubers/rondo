# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Rondo example: multi-provider code review and lightweight consensus.

What this demonstrates
------------------------
* **Default model** (empty or shorthand) + :mod:`example_dispatch` routing → subprocess.
* **Per-call** ``rules=`` → ``--system-prompt`` (see ``rondo_run_file`` / ``claude_p_rules``).
* **Optional second/third opinions** via provider-prefixed models (HTTP adapters).
* **Structured JSON** from the model, parsed and merged for a simple overlap heuristic.

What this does *not* do
-----------------------
* It does not open your repo or run static analysis tools; it reviews the **in-memory** sample.
* ``find_consensus`` uses token overlap on issue strings — a teaching aid, not production deduping.

All invocations use **live** dispatch (``dry_run=False``). Ensure ``claude`` and, with
``--cloud``, provider API keys are configured.

Run::

    cd rondo && uv run python examples/api/code_review_to_findings.py
    cd rondo && uv run python examples/api/code_review_to_findings.py --cloud
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

from example_dispatch import banner, run_prompt_json

CODE_SAMPLE = """def get_user(user_id):
    query = f"SELECT * FROM users WHERE id = {user_id}"
    return db.execute(query)

def update_email(user_id, new_email):
    db.execute(f"UPDATE users SET email = '{new_email}' WHERE id = {user_id}")
"""

REVIEW_PROMPT = """Review this Python code for security issues.
Return JSON only with this shape (no markdown fences):
{{"passed": false, "confidence": 0.9, "issues": ["short issue 1", "short issue 2"], "result": "one-line summary"}}

Code:
{code}"""


def issues_match(a: str, b: str) -> bool:
    """Very small overlap heuristic: two issues are the same if enough tokens overlap."""
    words_a = set(a.lower().split())
    words_b = set(b.lower().split())
    noise = {"the", "a", "an", "on", "in", "is", "of", "to", "and", "for", "sql", "code"}
    return len((words_a & words_b) - noise) >= 2


def find_consensus(reviews: list[dict[str, Any]], labels: list[str]) -> list[dict[str, Any]]:
    """Cluster issues that likely refer to the same finding across providers."""
    all_issues: list[dict[str, Any]] = []
    for i, review in enumerate(reviews):
        label = labels[i] if i < len(labels) else f"provider_{i}"
        for issue in review.get("issues", []) or []:
            if isinstance(issue, str) and issue.strip():
                all_issues.append({"text": issue.strip(), "provider": label})

    findings: list[dict[str, Any]] = []
    used: set[int] = set()
    for i, a in enumerate(all_issues):
        if i in used:
            continue
        matches = [a["provider"]]
        used.add(i)
        for j, b in enumerate(all_issues):
            if j not in used and issues_match(a["text"], b["text"]):
                matches.append(b["provider"])
                used.add(j)
        findings.append(
            {
                "issue": a["text"],
                "confidence": "CONFIRMED" if len(set(matches)) >= 2 else "SINGLE",
                "providers": list(dict.fromkeys(matches)),
            }
        )
    return findings


def one_review(
    *,
    prompt: str,
    model: str,
    timeout_sec: int,
    rules: str,
) -> dict[str, Any] | None:
    """Run a single review; return parsed model JSON or None on hard failure."""
    try:
        env, parsed = run_prompt_json(
            prompt=prompt,
            model=model,
            dry_run=False,
            timeout_sec=timeout_sec,
            rules=rules,
        )
    except RuntimeError as exc:
        print(f"  -ERROR- {exc}", file=sys.stderr)
        return None

    if parsed.get("_non_json"):
        print("  -WARNING- Model did not return JSON; skipping this provider.", file=sys.stderr)
        return None

    cost = env.get("total_cost_usd")
    if cost is not None:
        print(f"    round cost (USD): {cost:.4f}" if isinstance(cost, (int, float)) else f"    round cost: {cost}")
    return parsed


def multi_ai_review(code: str, *, timeout_sec: int, include_cloud: bool) -> dict[str, Any]:
    """Primary Claude review, optional cloud reviews, then consensus."""
    prompt = REVIEW_PROMPT.format(code=code)
    reviews: list[dict[str, Any]] = []
    labels: list[str] = []

    print("  Step 1: primary review (default model routing)…")
    primary = one_review(
        prompt=prompt,
        model="",
        timeout_sec=timeout_sec,
        rules="You are a security auditor. Reply with JSON only, no markdown.",
    )
    if not primary:
        return {"error": "primary review failed", "findings": []}
    print(f"    issues={len(primary.get('issues', []) or [])}, passed={primary.get('passed')!r}")
    reviews.append(primary)
    labels.append("primary")

    if include_cloud:
        print("  Step 2: cross-check with cloud providers (HTTP adapters)…")
        for provider in ("gemini:gemini-2.5-flash", "grok:grok-3"):
            label = provider.split(":", 1)[0]
            got = one_review(
                prompt=prompt,
                model=provider,
                timeout_sec=timeout_sec,
                rules="You are a security auditor. Reply with JSON only, no markdown.",
            )
            if got:
                print(f"    {label}: issues={len(got.get('issues', []) or [])}")
                reviews.append(got)
                labels.append(label)
    else:
        print("  (Omit --cloud for primary only; add --cloud for Gemini + Grok cross-check.)")

    findings = find_consensus(reviews, labels)
    confirmed = [f for f in findings if f["confidence"] == "CONFIRMED"]
    print(f"  Step 3: {len(findings)} clustered finding(s), {len(confirmed)} multi-provider CONFIRMED")
    return {"findings": findings, "providers": len(reviews)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--cloud", action="store_true", help="Also call gemini + grok (needs API keys)")
    parser.add_argument("--timeout", type=int, default=120, metavar="SEC", help="Per-invocation timeout")
    args = parser.parse_args()

    print(banner("Multi-provider code review → consensus"))
    try:
        result = multi_ai_review(CODE_SAMPLE, timeout_sec=args.timeout, include_cloud=args.cloud)
    except RuntimeError as exc:
        print(f"-ERROR- {exc}", file=sys.stderr)
        return 1

    print()
    if result.get("error"):
        print(f"-ERROR- {result['error']}")
        return 1

    for f in result["findings"]:
        print(f"  [{f['confidence']}] {f['issue'][:72]}")
        print(f"      providers: {', '.join(f['providers'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
