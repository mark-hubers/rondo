"""Rondo Real-World: Community Reply + Variant Lookup.

REAL WORKFLOW THIS REPLACES:
  Community members message about genetics/testing/trials. Mark pastes
  message, Claude fact-checks, drafts reply. 123+ times.

SCRIPTED VERSION:
  Incoming message -> ask Claude to fact-check + draft reply.

HOW TO RUN:
  python examples/api/community_reply_variant_lookup.py
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
        return {"result": output, "passed": True, "issues": [], "confidence": 0.5}


SAMPLE_MESSAGE = (
    "Hi Mark, my daughter was diagnosed with Usher syndrome. They found "
    "c.2299delG in her USH2A gene. We were told both parents must be "
    "tested to confirm. Is her hearing loss going to get worse?"
)


def handle_message(message: str) -> dict:
    """Process community message: fact-check + draft reply via real AI."""
    _out(f"  Message: {message[:60]}...")
    result = dispatch(
        f"A community member sent this about Usher syndrome. Do three things:\n"
        f"1. Identify factual errors in their message\n"
        f"2. Draft a short, warm reply correcting errors gently\n"
        f'3. Return JSON: {{"errors": ["..."], "reply": "draft text"}}\n\n'
        f"Message: {message}",
        rules="You help Usher syndrome families. Correct gently. Short reply. Return JSON.",
    )
    if result is None:
        return {"error": "dispatch failed", "reply": ""}
    return {
        "reply": str(result.get("result", result.get("reply", "")))[:500],
        "corrections": len(result.get("errors", result.get("issues", []))),
        "confidence": result.get("confidence", 0.5),
    }


def main() -> None:
    """Run community reply pipeline."""
    _out("=== Community Reply + Variant Lookup ===")
    _out("")
    result = handle_message(SAMPLE_MESSAGE)
    _out("")
    if result.get("error"):
        _out(f"-ERROR- {result['error']}")
        return
    _out(f"Corrections: {result['corrections']}")
    _out(f"Reply: {result['reply'][:200]}")


if __name__ == "__main__":
    main()


# -- sig: mgh-6201.cd.bd955f.ea26.1ea526
