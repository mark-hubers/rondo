"""Rondo Real-World: Community Reply + Variant Lookup.

REAL WORKFLOW THIS REPLACES:
  Community members message Mark about genetics, testing, trials.
  Mark pastes message, Claude fact-checks, drafts reply. 123+ times.

SCRIPTED VERSION:
  Incoming message -> ask Claude to fact-check + draft reply ->
  optionally look up variant via BioMCP -> return ready-to-send draft.

HOW TO RUN:
  python examples/api/community_reply_variant_lookup.py
"""

import json
import os
import sys

from rondo import smart_return

## Default model. Inside Claude Code: auto-falls back to Anthropic API.
## From terminal: dispatches via claude -p. Override with RONDO_MODEL env var.
DEFAULT_MODEL = os.environ.get("RONDO_MODEL", "sonnet")

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
            parsed = {"passed": True, "result": output[:2000], "issues": [], "confidence": 0.5}
        return smart_return.normalize_response(parsed)
    except (FileNotFoundError, OSError, json.JSONDecodeError, TypeError, KeyError) as exc:
        _out(f"  Dispatch failed: {exc}")
        return None


## --- Sample Message (based on real community messages) -----------

SAMPLE_MESSAGE = (
    "Hi Mark, my daughter was just diagnosed with Usher syndrome. "
    "They found c.2299delG in her USH2A gene. We were told both "
    "parents must be tested to confirm. Is her hearing loss going "
    "to get worse? Are there any trials she could join?"
)

REPLY_PROMPT = """A community member sent this message about Usher syndrome.
Do three things:

1. FACT-CHECK: Identify any factual errors in their message
2. CORRECTIONS: For each error, provide the correct information gently
3. DRAFT REPLY: Write a short, warm reply in first person (as someone who also has USH2).
   Correct errors gently, answer their questions, mention any relevant clinical trials.

Return JSON:
{{"errors_found": [{{"claim": "...", "correction": "..."}}],
  "reply": "the draft reply text",
  "confidence": 0.9}}

Their message:
{message}"""


## --- The Pipeline ------------------------------------------------


def handle_message(message: str) -> dict:
    """Process community message: fact-check + draft reply via real AI."""
    _out(f"  Message: {message[:60]}...")

    prompt = REPLY_PROMPT.format(message=message)
    result = _dispatch(prompt)

    if result is None:
        return {"error": "Dispatch failed", "reply": ""}

    reply = result.get("result", "")
    confidence = result.get("confidence", 0.5)
    errors = result.get("issues", [])

    _out(f"  Confidence: {confidence}")
    _out(f"  Errors found: {len(errors)}")
    _out(f"  Reply length: {len(reply)} chars")

    return {
        "reply": reply,
        "corrections": len(errors),
        "confidence": confidence,
        "reply_length": len(reply),
        "ready_to_send": len(reply) > 50,
    }


def main() -> None:
    """Demonstrate community reply pipeline."""
    _out("=== Community Reply + Variant Lookup ===")
    _out("")

    _out("(REAL dispatch -- Claude fact-checks and drafts reply)")
    _out("")
    result = handle_message(SAMPLE_MESSAGE)
    _out("")

    if result.get("error"):
        _out(f"-ERROR- {result['error']}")
        return

    _out("--- Draft Reply ---")
    _out(result["reply"][:500])
    _out("---")


if __name__ == "__main__":
    main()


# -- sig: mgh-6201.cd.bd955f.ea26.1ea526
