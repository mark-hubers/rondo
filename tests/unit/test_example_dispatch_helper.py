# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Unit tests for examples/api/example_dispatch.py helper normalization.

VER-001: Product acceptance / unit test coverage.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

EXAMPLE_API_DIR = Path(__file__).resolve().parents[2] / "examples" / "api"
if str(EXAMPLE_API_DIR) not in sys.path:
    sys.path.insert(0, str(EXAMPLE_API_DIR))

from example_dispatch import invoke_rondo  # noqa: E402


class TestInvokeRondoNormalization:
    """API helper should normalize envelope before edge-case branching."""

    def test_partial_task_payload_not_left_as_top_level_error(self) -> None:
        raw = json.dumps(
            {
                "status": "error",
                "tasks": [{"name": "t1", "status": "partial", "raw_output": '{"ok":true}'}],
                "done_count": 0,
                "error_count": 0,
                "partial_count": 1,
                "pending_count": 0,
                "total_cost_usd": 0.0,
                "duration_sec": 0.0,
                "dry_run": False,
            }
        )
        with patch("rondo.mcp_dispatch.rondo_run_file", return_value=raw):
            env = invoke_rondo(prompt="x", model="sonnet", execution="subprocess", dry_run=False)
        assert env["status"] == "partial"
        assert env["partial_count"] == 1


# -- sig: mgh-6201.cd.bd955f.f0d0.e27503
