"""Rondo Real-World: Multi-AI Code Review -> Sprint Findings.

REAL WORKFLOW THIS REPLACES:
  Copy code to Cursor, paste findings back, fix, repeat. Every session.

SCRIPTED VERSION:
  Send code to Claude via Rondo -> parse structured findings ->
  optionally add cloud AI reviews -> consensus check -> create
  sprint findings for confirmed issues.

HOW TO RUN:
  python examples/api/code_review_to_findings.py
  RONDO_CLOUD=1 python examples/api/code_review_to_findings.py
"""

import json
import os
import sys

from rondo import mcp_dispatch


def _out(msg: str) -> None:
    """Write output line."""
    sys.stdout.write(msg + "\n")


def dispatch(prompt: str, model: str = "", **kwargs: str | int) -> dict | None:
    """Dispatch prompt via Rondo. Returns parsed JSON or None on failure.

    Default: inline subprocess (free on Max). Reads config from ~/.rondo/config.toml.
    Override with model='gemini:flash' for cloud, rules='...' for custom rules.
    """
    raw = mcp_dispatch.rondo_run_file(
        prompt=prompt,
        model=model,
        dry_run=False,
        timeout_sec=60,
        _session=object(),
        **kwargs,
    )
    data = json.loads(raw)
    tasks = data.get("tasks", [])
    if not tasks:
        return None
    task = tasks[0]
    if task.get("status") == "error":
        _out(f"  Error: {task.get('error_message', '')[:80]}")
        return None
    output = task.get("raw_output", "")
    try:
        return json.loads(output)
    except json.JSONDecodeError:
        return {"result": output, "passed": True, "issues": [], "confidence": 0.5}


## --- Code to Review (has known bugs) ---

CODE_SAMPLE = """def get_user(user_id):
    query = f"SELECT * FROM users WHERE id = {user_id}"
    return db.execute(query)

def update_email(user_id, new_email):
    db.execute(f"UPDATE users SET email = '{new_email}' WHERE id = {user_id}")
"""

LIVE_CLOUD = os.environ.get("RONDO_CLOUD", "").lower() in ("1", "true", "yes")

REVIEW_PROMPT = """Review this Python code for security issues.
Return JSON: {{"passed": false, "confidence": 0.9, "issues": ["issue 1"], "result": "summary"}}

Code:
{code}"""


## --- Consensus Logic ---


def issues_match(a: str, b: str) -> bool:
    """Check if two issues describe the same bug."""
    words_a = set(a.lower().split())
    words_b = set(b.lower().split())
    noise = {"the", "a", "an", "on", "in", "is", "of", "to", "and", "for"}
    return len((words_a & words_b) - noise) >= 2


def find_consensus(reviews: list[dict]) -> list[dict]:
    """Find issues that 2+ providers agree on."""
    all_issues: list[dict] = []
    names = ["claude", "gemini", "grok"]
    for i, review in enumerate(reviews):
        name = names[i] if i < len(names) else f"provider_{i}"
        for issue in review.get("issues", []):
            all_issues.append({"text": issue, "provider": name})

    findings: list[dict] = []
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
                "confidence": "CONFIRMED" if len(matches) >= 2 else "SINGLE",
                "providers": matches,
            }
        )
    return findings


## --- The Pipeline ---


def multi_ai_review(code: str) -> dict:
    """Send code to AI, find consensus, report findings."""
    reviews: list[dict] = []
    prompt = REVIEW_PROMPT.format(code=code)

    ## Step 1: Claude review (free on Max)
    _out("  Step 1: Claude review...")
    result = dispatch(prompt, rules="You are a security auditor. Return JSON only.")
    if result:
        _out(f"    passed={result.get('passed')}, issues={len(result.get('issues', []))}")
        reviews.append(result)
    else:
        return {"error": "dispatch failed", "findings": []}

    ## Step 2: Cloud reviews (optional)
    if LIVE_CLOUD:
        for provider in ["gemini:flash", "grok:grok-3"]:
            cloud = dispatch(prompt, model=provider)
            if cloud:
                _out(f"    {provider}: issues={len(cloud.get('issues', []))}")
                reviews.append(cloud)
    else:
        _out("    (Set RONDO_CLOUD=1 for multi-provider consensus)")

    ## Step 3: Consensus
    findings = find_consensus(reviews)
    confirmed = [f for f in findings if f["confidence"] == "CONFIRMED"]
    _out(f"  Step 2: {len(findings)} findings, {len(confirmed)} confirmed")

    return {"findings": findings, "providers": len(reviews)}


def main() -> None:
    """Run multi-AI code review with real dispatch."""
    _out("=== Multi-AI Code Review -> Sprint Findings ===")
    _out("")
    result = multi_ai_review(CODE_SAMPLE)
    _out("")
    if result.get("error"):
        _out(f"-ERROR- {result['error']}")
        return
    for f in result["findings"]:
        _out(f"  [{f['confidence']}] {f['issue'][:70]}")


if __name__ == "__main__":
    main()


# -- sig: mgh-6201.cd.bd955f.ea20.1ea520
