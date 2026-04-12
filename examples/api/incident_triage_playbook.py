# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
# rondo-meta: mode=subprocess provider=anthropic category=triage value="Generate incident severity, owner, and first-response actions."

"""Incident triage playbook: produce structured incident response guidance."""

from __future__ import annotations

from example_dispatch import banner, run_prompt_json


def main() -> int:
    print(banner("Incident triage playbook"))
    env, payload = run_prompt_json(
        prompt=(
            "Return JSON only: {"
            '"severity":"P1|P2|P3",'
            '"owner":"team name",'
            '"actions":["...","..."]'
            "} for this incident: CI deploy pipeline failing with authentication errors."
        ),
        model="sonnet",
        execution="subprocess",
        dry_run=False,
        timeout_sec=120,
    )
    severity = payload.get("severity", "unknown")
    owner = payload.get("owner", "unassigned")
    actions = payload.get("actions", [])
    print(f"-PASS- status={env.get('status')} severity={severity} owner={owner} actions={len(actions)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
