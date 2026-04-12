# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
# rondo-meta: mode=subprocess provider=anthropic category=publish value="Generate multiple response variants for community replies"

"""Rondo example: draft a careful community reply from a single message.

What this demonstrates
------------------------
* A **multi-part** instruction (errors + reply) with a strict JSON shape.
* Handling **missing keys** and **non-JSON** without inventing success.

Out of scope (named honestly)
-------------------------------
* **Variant / ClinVar lookup** is not implemented. Production: call your genetics MCP
  or internal API *before* drafting, then pass structured facts into this prompt.

Uses **live** dispatch. Requires ``claude`` / Rondo to be configured.

Run::

    cd rondo && uv run python examples/api/community_reply_variant_lookup.py
"""

from __future__ import annotations

import argparse
from typing import Any

from example_dispatch import banner, run_prompt_json

SAMPLE_MESSAGE = (
    "Hi Mark, my daughter was diagnosed with Usher syndrome. They found "
    "c.2299delG in her USH2A gene. We were told both parents must be "
    "tested to confirm. Is her hearing loss going to get worse?"
)


def handle_message(message: str, *, timeout_sec: int) -> dict[str, Any]:
    """Return reply metadata; never silently drop dispatch errors."""
    prompt = (
        "A community member sent this about Usher syndrome. Do three things:\n"
        "1. List factual errors or imprecisions (empty list if none).\n"
        "2. Draft a short, warm reply correcting errors gently.\n"
        '3. Return JSON only: {"errors": ["..."], "reply": "draft text"}\n\n'
        f"Message:\n{message}"
    )
    try:
        _, parsed = run_prompt_json(
            prompt=prompt,
            model="",
            dry_run=False,
            timeout_sec=timeout_sec,
            rules="You help rare-disease families. Be accurate and kind. JSON only.",
        )
    except RuntimeError as exc:
        return {"error": str(exc), "reply": ""}

    if parsed.get("_non_json"):
        return {
            "error": "model_non_json",
            "reply": "",
            "snippet": str(parsed.get("snippet", ""))[:200],
        }

    errors = parsed.get("errors")
    if not isinstance(errors, list):
        errors = parsed.get("issues") if isinstance(parsed.get("issues"), list) else []
    reply = str(parsed.get("reply", parsed.get("result", "")))[:800]
    return {
        "reply": reply,
        "corrections": len(errors),
        "confidence": parsed.get("confidence"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--timeout", type=int, default=120, metavar="SEC")
    args = parser.parse_args()

    print(banner("Community reply draft (no variant DB)"))
    result = handle_message(SAMPLE_MESSAGE, timeout_sec=args.timeout)
    print()
    if result.get("error"):
        print(f"-ERROR- {result['error']}")
        if result.get("snippet"):
            print(f"  raw: {result['snippet'][:160]!r}")
        return 1
    print(f"Corrections flagged: {result['corrections']}")
    print(f"Reply:\n{result['reply'][:400]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
