"""Rondo Real-World: Multi-Platform Publish Pipeline.

REAL WORKFLOW THIS REPLACES:
  After every essay, draft LinkedIn + Facebook + Substack separately.

SCRIPTED VERSION:
  Send thesis to Claude -> generate one variant per platform ->
  check length against platform rules. In production: regenerate
  with stricter rules if too long (not implemented in this example).

HOW TO RUN:
  python examples/api/multi_platform_publish.py
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


PLATFORM_RULES = {
    "linkedin": {"max_chars": 1500, "voice": "professional, first person, no em dashes"},
    "facebook": {"max_chars": 300, "voice": "casual community tone, include [link]"},
    "substack_subtitle": {"max_chars": 100, "voice": "compelling, not clickbait"},
}

SAMPLE_THESIS = (
    "Usher syndrome research is accelerating. Three gene therapy trials "
    "are active in 2026, and RTx-015 received RMAT designation from the FDA."
)


def generate_variants(thesis: str) -> dict:
    """Generate all platform variants from thesis via real AI."""
    variants: dict[str, dict] = {}
    for platform, rules in PLATFORM_RULES.items():
        _out(f"  Generating {platform}...")
        result = dispatch(
            f"Write a {platform.replace('_', ' ')} post. {rules['voice']}. "
            f"Max {rules['max_chars']} chars. Return ONLY the post text.\n\nThesis: {thesis}",
            rules=f"You write social media posts. Max {rules['max_chars']} chars. Return text only.",
        )
        if result is None:
            _out("    SKIP")
            continue
        text = str(result.get("result", ""))
        length = len(text)
        status = "READY" if length <= rules["max_chars"] else "NEEDS_EDIT"
        variants[platform] = {"text": text, "length": length, "status": status}
        _out(f"    {status}: {length}/{rules['max_chars']} chars")

    return {
        "total": len(variants),
        "ready": len([v for v in variants.values() if v["status"] == "READY"]),
        "variants": variants,
    }


def main() -> None:
    """Run multi-platform publish pipeline."""
    _out("=== Multi-Platform Publish ===")
    _out("")
    result = generate_variants(SAMPLE_THESIS)
    _out("")
    for platform, v in result["variants"].items():
        _out(f"  {platform} [{v['status']}] ({v['length']} chars): {v['text'][:60]}...")


if __name__ == "__main__":
    main()


# -- sig: mgh-6201.cd.bd955f.ea25.1ea525
