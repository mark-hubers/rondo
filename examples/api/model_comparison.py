# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
# rondo-meta: mode=http provider=anthropic,gemini,grok category=review value="Compare model outputs side-by-side for one review prompt."

"""Model comparison: run one prompt across multiple models and compare outputs."""

from __future__ import annotations

import json

from example_dispatch import banner

from rondo.mcp_compose import rondo_multi_review


def main() -> int:
    print(banner("Model comparison"))
    result = json.loads(
        rondo_multi_review(
            prompt="Give two maintainability risks for a monolithic Python service.",
            providers=json.dumps(["sonnet", "gemini:gemini-2.5-flash", "grok:grok-3"]),
            dry_run=False,
        )
    )
    per_provider = result.get("per_provider", [])
    done = sum(1 for item in per_provider if item.get("status") in ("done", "partial", "skipped"))
    print(f"-PASS- status={result.get('status')} providers={len(per_provider)} non-error={done}")
    return 0 if per_provider else 1


if __name__ == "__main__":
    raise SystemExit(main())
