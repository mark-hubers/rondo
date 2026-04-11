# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Rondo example: one generation pass per platform with explicit length QA.

What this demonstrates
----------------------
* **Different system rules per platform** via the ``rules=`` argument.
* Post-processing **quality gate** (character budget) separate from the model.
* Honest scope: **no auto-regenerate** loop here — that belongs in your editor or a second pass.

Uses **live** dispatch. Requires ``claude`` / Rondo to be configured.

Run::

    cd rondo && uv run python examples/api/multi_platform_publish.py
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

from example_dispatch import banner, run_prompt_json

PLATFORM_RULES: dict[str, dict[str, Any]] = {
    "linkedin": {"max_chars": 1500, "voice": "professional, first person, no em dashes"},
    "facebook": {"max_chars": 300, "voice": "casual community tone, include [link] placeholder"},
    "substack_subtitle": {"max_chars": 100, "voice": "compelling, not clickbait"},
}

SAMPLE_THESIS = (
    "Usher syndrome research is accelerating. Three gene therapy trials "
    "are active in 2026, and RTx-015 received RMAT designation from the FDA."
)


def generate_variants(thesis: str, *, timeout_sec: int) -> dict[str, Any]:
    """Produce one draft per platform key in PLATFORM_RULES."""
    variants: dict[str, dict[str, Any]] = {}
    for platform, rules in PLATFORM_RULES.items():
        print(f"  {platform} …")
        prompt = (
            f"Write a {platform.replace('_', ' ')} post.\n"
            f"Voice: {rules['voice']}\n"
            f"Hard limit: {rules['max_chars']} characters (count yourself).\n"
            f'Return JSON only: {{"text": "the post body only"}}\n\nThesis:\n{thesis}'
        )
        per_rules = f"You write social posts. Stay under {rules['max_chars']} characters. JSON only with key 'text'."
        try:
            env, parsed = run_prompt_json(
                prompt=prompt,
                model="",
                dry_run=False,
                timeout_sec=timeout_sec,
                rules=per_rules,
            )
        except RuntimeError as exc:
            print(f"    -ERROR- {exc}", file=sys.stderr)
            variants[platform] = {"text": "", "length": 0, "status": "ERROR", "detail": str(exc)[:120]}
            continue

        if parsed.get("_non_json"):
            variants[platform] = {
                "text": "",
                "length": 0,
                "status": "NON_JSON",
                "snippet": str(parsed.get("snippet", ""))[:120],
            }
            print("    -WARNING- Non-JSON output")
            continue

        text = str(parsed.get("text", parsed.get("result", "")))
        length = len(text)
        max_c = int(rules["max_chars"])
        status = "READY" if 0 < length <= max_c else "NEEDS_EDIT"
        variants[platform] = {
            "text": text,
            "length": length,
            "max": max_c,
            "status": status,
            "round_status": env.get("status"),
        }
        print(f"    {status}: {length}/{max_c} chars")

    ready = sum(1 for v in variants.values() if v.get("status") == "READY")
    return {"total": len(variants), "ready": ready, "variants": variants}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--timeout", type=int, default=120, metavar="SEC")
    args = parser.parse_args()

    print(banner("Multi-platform drafts (length QA)"))
    result = generate_variants(SAMPLE_THESIS, timeout_sec=args.timeout)
    print()
    for platform, v in result["variants"].items():
        snippet = (v.get("text") or "")[:72]
        print(f"  {platform:18} [{v.get('status')}] {v.get('length', 0)}/{v.get('max', '?')} — {snippet!r}")
    return 0 if result.get("ready", 0) == result.get("total", 0) else 1


if __name__ == "__main__":
    raise SystemExit(main())
