# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
# rondo-meta: mode=subprocess provider=anthropic category=option-c value="Replay previous dispatch and compare output via CLI"

"""Option C example 05: replay the last dispatch and compare."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from rondo.mcp_dispatch import rondo_run_file


def _latest_task_id(results_dir: Path) -> str:
    files = sorted(results_dir.glob("task-*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return ""
    return files[0].stem.replace("task-", "", 1)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--live", action="store_true", help="Run live dispatch before replay/compare")
    args = parser.parse_args()

    # -- Seed a dispatch so replay has a concrete target.
    _ = json.loads(
        rondo_run_file(
            prompt="Return JSON with result='OPTION_C_REPLAY_SEED_285'.",
            model="sonnet",
            execution="subprocess",
            dry_run=not args.live,
        )
    )

    results_dir = Path("reports/rondo-results")
    run_id = _latest_task_id(results_dir)
    if not run_id:
        print("-ERROR- No task-*.json files found for replay.", file=sys.stderr)
        return 1

    replay_cmd = ["rondo", "replay", run_id, "--json"]
    replay = subprocess.run(replay_cmd, capture_output=True, text=True, check=False)
    if replay.returncode not in (0, 1):
        print(f"-ERROR- replay failed: {replay.stderr}", file=sys.stderr)
        return 1

    compare_cmd = ["rondo", "compare", run_id, run_id, "--json"]
    compare = subprocess.run(compare_cmd, capture_output=True, text=True, check=False)
    if compare.returncode not in (0, 1):
        print(f"-ERROR- compare failed: {compare.stderr}", file=sys.stderr)
        return 1

    print("-PASS- Replay and compare commands completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

