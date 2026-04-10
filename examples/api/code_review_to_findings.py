"""Rondo Real-World: Multi-AI Code Review -> Sprint Findings.

REAL WORKFLOW THIS REPLACES:
  Mark builds code with Claude -> copies to Cursor -> pastes Cursor's
  findings back into Claude -> Claude fixes -> repeat. Every session.
  165 Cursor paste-backs in 90 days. Pure manual relay.

SCRIPTED VERSION:
  Send code to Claude via API -> parse structured findings ->
  optionally add cloud AI reviews -> consensus check -> create
  sprint findings automatically.

HOW TO RUN:
  python examples/api/code_review_to_findings.py
  RONDO_CLOUD=1 python examples/api/code_review_to_findings.py  # + Gemini/Grok

REQUIRES: ANTHROPIC_API_KEY env var or macOS Keychain entry.
"""

import json
import os
import sys

from rondo import smart_return

## Default model: Anthropic API (works from anywhere — inside Claude Code,
## terminal, CI). Haiku is cheap ($0.001/call). Override with RONDO_MODEL.
DEFAULT_MODEL = os.environ.get("RONDO_MODEL", "anthropic:claude-haiku-4-5")
LIVE_CLOUD = os.environ.get("RONDO_CLOUD", "").lower() in ("1", "true", "yes")

_mcp_dispatch = None


def _get_dispatch() -> object:
    """Lazy-load mcp_dispatch module."""
    global _mcp_dispatch  # noqa: PLW0603
    if _mcp_dispatch is None:
        from rondo import mcp_dispatch  # pylint: disable=import-outside-toplevel

        _mcp_dispatch = mcp_dispatch
    return _mcp_dispatch


def _out(msg: str) -> None:
    """Write output line."""
    sys.stdout.write(msg + "\n")


def _dispatch(prompt: str, model: str = "") -> dict | None:
    """Real AI dispatch via Rondo API. Always dispatches — no mocks."""
    use_model = model or DEFAULT_MODEL
    try:
        mod = _get_dispatch()
        raw = mod.rondo_run_file(  # type: ignore[union-attr]
            prompt=prompt,
            model=use_model,
            dry_run=False,
            timeout_sec=60,
        )
        data = json.loads(raw)
        if data.get("status") == "error":
            _out(f"  Dispatch error: {data.get('error', 'unknown')[:80]}")
            return None
        tasks = data.get("tasks", [])
        if not tasks or tasks[0].get("status") == "error":
            err = tasks[0].get("error_message", "unknown") if tasks else "no tasks"
            _out(f"  Task error: {err[:80]}")
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


def _dispatch_cloud(prompt: str, model: str = "gemini:flash") -> dict | None:
    """Cloud AI dispatch -- only with RONDO_CLOUD=1."""
    if not LIVE_CLOUD:
        return None
    return _dispatch(prompt, model)


## --- Review Prompt -----------------------------------------------

REVIEW_PROMPT = """Review this Python code for security issues.
Return your findings as JSON with this exact structure:
{{"passed": false, "confidence": 0.9, "issues": ["issue 1", "issue 2"], "result": "summary"}}
If no issues found, return: {{"passed": true, "confidence": 0.9, "issues": [], "result": "clean"}}

Code to review:
{code}"""

CODE_SAMPLE = '''def get_user(user_id):
    """Fetch user by ID from database."""
    query = f"SELECT * FROM users WHERE id = {user_id}"
    return db.execute(query)

def update_email(user_id, new_email):
    """Update user email -- no auth check."""
    db.execute(f"UPDATE users SET email = '{new_email}' WHERE id = {user_id}")
'''


## --- Consensus Logic (real -- not mocked) -------------------------


def _issues_match(issue_a: str, issue_b: str) -> bool:
    """Check if two issues describe the same bug (keyword overlap)."""
    words_a = set(issue_a.lower().split())
    words_b = set(issue_b.lower().split())
    noise = {"the", "a", "an", "on", "in", "is", "of", "to", "and", "for"}
    meaningful = (words_a & words_b) - noise
    return len(meaningful) >= 2


def _find_consensus(reviews: list[dict]) -> list[dict]:
    """Find issues that 2+ providers agree on."""
    all_issues: list[dict] = []
    provider_names = ["claude", "gemini", "grok"]
    for i, review in enumerate(reviews):
        name = provider_names[i] if i < len(provider_names) else f"provider_{i}"
        for issue in review.get("issues", []):
            all_issues.append({"text": issue, "provider": name})

    findings: list[dict] = []
    used: set[int] = set()
    for i, issue_a in enumerate(all_issues):
        if i in used:
            continue
        matches = [issue_a["provider"]]
        used.add(i)
        for j, issue_b in enumerate(all_issues):
            if j in used or j == i:
                continue
            if _issues_match(issue_a["text"], issue_b["text"]):
                matches.append(issue_b["provider"])
                used.add(j)

        findings.append(
            {
                "issue": issue_a["text"],
                "confidence": "CONFIRMED" if len(matches) >= 2 else "SINGLE",
                "providers": matches,
                "provider_count": len(matches),
            }
        )
    return findings


def _create_finding(finding: dict, sprint_id: str = "EXAMPLE-001") -> dict:
    """Create a sprint finding record."""
    return {
        "sprint": sprint_id,
        "issue": finding["issue"],
        "confidence": finding["confidence"],
        "providers": finding["providers"],
        "action": "CREATED" if finding["confidence"] == "CONFIRMED" else "FLAGGED",
    }


## --- The Pipeline ------------------------------------------------


def multi_ai_review(code: str, sprint_id: str = "EXAMPLE-001") -> dict:
    """Send code to AI providers, find consensus, create findings."""
    reviews: list[dict] = []

    ## Step 1: Claude review via API (always — works everywhere)
    _out("  Step 1: Claude review...")
    prompt = REVIEW_PROMPT.format(code=code)
    claude_result = _dispatch(prompt)
    if claude_result:
        _out(f"    Claude: passed={claude_result['passed']}, issues={len(claude_result['issues'])}")
        reviews.append(claude_result)
    else:
        _out("    Claude dispatch failed")
        return {"total_findings": 0, "actions": [], "error": "dispatch failed"}

    ## Step 2: Cloud AI reviews (optional)
    gemini_result = _dispatch_cloud(prompt, model="gemini:flash")
    if gemini_result:
        _out(f"    Gemini: passed={gemini_result['passed']}, issues={len(gemini_result['issues'])}")
        reviews.append(gemini_result)

    grok_result = _dispatch_cloud(prompt, model="grok:grok-3")
    if grok_result:
        _out(f"    Grok: passed={grok_result['passed']}, issues={len(grok_result['issues'])}")
        reviews.append(grok_result)

    if not LIVE_CLOUD:
        _out("    (Set RONDO_CLOUD=1 for multi-provider consensus)")

    ## Step 3: Consensus
    _out(f"  Step 2: Consensus across {len(reviews)} provider(s)...")
    findings = _find_consensus(reviews)
    confirmed = [f for f in findings if f["confidence"] == "CONFIRMED"]
    single = [f for f in findings if f["confidence"] == "SINGLE"]
    _out(f"    CONFIRMED={len(confirmed)}, SINGLE={len(single)}")

    ## Step 4: Create findings
    _out("  Step 3: Creating sprint findings...")
    actions: list[dict] = []
    for finding in findings:
        action = _create_finding(finding, sprint_id)
        actions.append(action)
        _out(f"    [{finding['confidence']}] {finding['issue'][:60]}")

    return {
        "total_findings": len(findings),
        "confirmed": len(confirmed),
        "single": len(single),
        "providers_used": len(reviews),
        "actions": actions,
    }


def main() -> None:
    """Run multi-AI code review with REAL dispatch."""
    _out("=== Multi-AI Code Review -> Sprint Findings ===")
    _out(f"(Model: {DEFAULT_MODEL})")
    _out("")

    result = multi_ai_review(CODE_SAMPLE)
    _out("")

    if result.get("error"):
        _out(f"-ERROR- {result['error']}")
        return

    _out(f"Result: {result['total_findings']} findings from {result['providers_used']} provider(s)")
    for action in result["actions"]:
        _out(f"  [{action['confidence']}] {action['issue'][:70]}")


if __name__ == "__main__":
    main()


# -- sig: mgh-6201.cd.bd955f.ea20.1ea520
