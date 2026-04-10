"""Rondo Real-World: Multi-Platform Publish Pipeline.

REAL WORKFLOW THIS REPLACES:
  After every essay, Mark needs LinkedIn (1500 chars), Facebook (300
  chars), and Substack subtitle (100 chars). 4,500+ messages.

SCRIPTED VERSION:
  Send essay thesis to Claude -> generate all platform variants ->
  quality-check each against platform rules -> regenerate if needed.

HOW TO RUN:
  python examples/api/multi_platform_publish.py
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
            parsed = {"passed": True, "result": output[:2000], "issues": [], "confidence": 0.5}
        return smart_return.normalize_response(parsed)
    except (FileNotFoundError, OSError, json.JSONDecodeError, TypeError, KeyError) as exc:
        _out(f"  Dispatch failed: {exc}")
        return None


## --- Platform Rules (Mark's REAL documented preferences) ----------

PLATFORM_RULES: dict[str, dict] = {
    "linkedin": {"max_chars": 1500, "voice": "professional but personal, first person, no em dashes"},
    "facebook": {"max_chars": 300, "voice": "casual community tone, include [link]"},
    "substack_subtitle": {"max_chars": 100, "voice": "compelling, not clickbait"},
}

SAMPLE_THESIS = (
    "Usher syndrome research is accelerating. Three gene therapy trials "
    "are now active in 2026, and RTx-015 just received RMAT designation "
    "from the FDA. This is personal -- I have USH2."
)

GENERATE_PROMPT = """Write a {platform} post based on this thesis.
Rules: {voice}. Maximum {max_chars} characters. Return ONLY the post text, nothing else.

Thesis: {thesis}"""


## --- Quality Check -----------------------------------------------


def _check_rules(text: str, platform: str) -> dict:
    """Check if text meets platform rules."""
    rules = PLATFORM_RULES.get(platform, {})
    max_chars = rules.get("max_chars", 9999)
    violations: list[str] = []
    if len(text) > max_chars:
        violations.append(f"Too long: {len(text)}/{max_chars}")
    return {"passed": len(violations) == 0, "length": len(text), "max_length": max_chars, "violations": violations}


## --- The Pipeline ------------------------------------------------


def generate_variants(thesis: str) -> dict:
    """Generate all platform variants from thesis via real AI."""
    variants: dict[str, dict] = {}

    for platform, rules in PLATFORM_RULES.items():
        _out(f"  Generating {platform}...")
        prompt = GENERATE_PROMPT.format(
            platform=platform.replace("_", " "),
            voice=rules["voice"],
            max_chars=rules["max_chars"],
            thesis=thesis,
        )
        result = _dispatch(prompt)
        if result is None:
            _out(f"    SKIP: dispatch failed for {platform}")
            continue

        text = result.get("result", "")
        check = _check_rules(text, platform)

        if check["passed"]:
            variants[platform] = {"text": text, "length": check["length"], "status": "READY"}
            _out(f"    -PASS- {check['length']}/{check['max_length']} chars")
        else:
            ## Regenerate with stricter constraint
            _out(f"    RETRY: {', '.join(check['violations'])}")
            retry_prompt = f"Rewrite shorter. HARD LIMIT {rules['max_chars']} characters:\n{text}"
            retry = _dispatch(retry_prompt)
            if retry:
                text = retry.get("result", text)
            variants[platform] = {
                "text": text,
                "length": len(text),
                "status": "READY" if len(text) <= rules["max_chars"] else "NEEDS_EDIT",
            }

    ready = [p for p, v in variants.items() if v["status"] == "READY"]
    return {"thesis": thesis[:60], "total": len(variants), "ready": len(ready), "variants": variants}


def main() -> None:
    """Demonstrate multi-platform publish pipeline."""
    _out("=== Multi-Platform Publish Pipeline ===")
    _out("")

    _out("(REAL dispatch -- Claude generates each variant)")
    _out("")
    result = generate_variants(SAMPLE_THESIS)
    _out("")

    for platform, variant in result["variants"].items():
        _out(f"  {platform} [{variant['status']}] ({variant['length']} chars):")
        _out(f"    {variant['text'][:80]}...")
        _out("")


if __name__ == "__main__":
    main()


# -- sig: mgh-6201.cd.bd955f.ea25.1ea525
