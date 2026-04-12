# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
# rondo-meta: mode=subprocess provider=anthropic category=review value="Run a PR-style review prompt and extract actionable findings."

"""PR review workflow: produce structured findings from a pull-request style prompt."""

from __future__ import annotations

from example_dispatch import banner, run_prompt_json


def main() -> int:
    print(banner("PR review workflow"))
    env, payload = run_prompt_json(
        prompt=(
            "Return JSON only: {"
            '"summary":"...",'
            '"must_fix":["..."],'
            '"nice_to_have":["..."]'
            "} for this PR description: adds async retries, introduces cache layer, and updates deployment script."
        ),
        model="sonnet",
        execution="subprocess",
        dry_run=False,
        timeout_sec=120,
    )
    must_fix = payload.get("must_fix", [])
    print(f"-PASS- status={env.get('status')} must_fix={len(must_fix)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
