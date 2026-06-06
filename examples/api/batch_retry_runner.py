# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
# rondo-meta: mode=http provider=gemini,grok category=pipeline value="Run batch review, detect failed providers, and retry just failures."

"""Batch retry runner: execute a provider batch and retry failed providers once."""

from __future__ import annotations

import json

from example_dispatch import banner

from rondo.mcp_compose import rondo_multi_review


def main() -> int:
    print(banner("Batch retry runner"))
    first = json.loads(
        rondo_multi_review(
            prompt="Return 3 security checks for a Python API service.",
            providers=json.dumps(["gemini:gemini-flash-latest", "grok:grok-4.3"]),
            dry_run=False,
        )
    )
    failed = [p.get("provider", "") for p in first.get("per_provider", []) if p.get("status") == "error"]
    retried = 0
    if failed:
        retried = len(failed)
        second = json.loads(
            rondo_multi_review(
                prompt="Return 3 security checks for a Python API service.",
                providers=json.dumps(failed),
                dry_run=False,
            )
        )
        print(f"-WARNING- initial_failed={len(failed)} retry_status={second.get('status')}")
    else:
        print("-PASS- first batch completed without provider failures")
    print(f"-PASS- first_status={first.get('status')} retried={retried}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
