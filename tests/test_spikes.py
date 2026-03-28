# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Spike regression tests — permanent sentinels for CC flag behavior.

VER-001 verification matrix: spike results promoted to permanent tests.
Session 91: spikes S1-S8 validated CC flags. These tests ensure CC updates
don't silently break Rondo's dispatch assumptions.

These tests call the REAL claude CLI (not mocked) so they verify actual
CC behavior. They're marked slow and can be skipped with -m "not slow".
"""

import json
import shutil
import subprocess


import pytest


def _claude_available() -> bool:
    """Check if claude CLI is on PATH."""
    return shutil.which("claude") is not None


skip_no_claude = pytest.mark.skipif(
    not _claude_available(), reason="claude CLI not available"
)


@skip_no_claude
class TestCCFlagSpikes:
    """Regression tests from Session 91 spikes S1-S8.

    These verify CC CLI flags that Rondo depends on.
    If any fail, CC changed behavior — update Rondo dispatch.
    """

    def test_s1_bare_flag_exists(self):
        """S1: --bare flag in claude --help."""
        result = subprocess.run(
            ["claude", "--help"],
            capture_output=True, text=True, check=False, timeout=10,
        )
        assert "--bare" in result.stdout, "CC removed --bare flag"

    def test_s2_tools_flag_exists(self):
        """S2: --tools flag in claude --help."""
        result = subprocess.run(
            ["claude", "--help"],
            capture_output=True, text=True, check=False, timeout=10,
        )
        assert "--tools" in result.stdout, "CC removed --tools flag"

    def test_s6_max_budget_flag_exists(self):
        """S6: --max-budget-usd flag in claude --help."""
        result = subprocess.run(
            ["claude", "--help"],
            capture_output=True, text=True, check=False, timeout=10,
        )
        assert "--max-budget-usd" in result.stdout, "CC removed --max-budget-usd"

    def test_s7_json_schema_flag_exists(self):
        """S7: --json-schema flag in claude --help."""
        result = subprocess.run(
            ["claude", "--help"],
            capture_output=True, text=True, check=False, timeout=10,
        )
        assert "--json-schema" in result.stdout, "CC removed --json-schema"

    def test_s8_system_prompt_flag_exists(self):
        """S8: --system-prompt flag in claude --help."""
        result = subprocess.run(
            ["claude", "--help"],
            capture_output=True, text=True, check=False, timeout=10,
        )
        assert "--system-prompt" in result.stdout, "CC removed --system-prompt"

    def test_permission_mode_has_dontask(self):
        """Session 91: dontAsk mode in --permission-mode."""
        result = subprocess.run(
            ["claude", "--help"],
            capture_output=True, text=True, check=False, timeout=10,
        )
        assert "dontAsk" in result.stdout, "CC removed dontAsk permission mode"

    def test_cc_version_minimum(self):
        """Rondo requires CC >= 2.1.81 for --bare."""
        result = subprocess.run(
            ["claude", "--version"],
            capture_output=True, text=True, check=False, timeout=10,
        )
        version = result.stdout.strip().split()[0]
        parts = version.split(".")
        major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])
        assert (major, minor, patch) >= (2, 1, 81), (
            f"CC version {version} too old — Rondo needs >= 2.1.81"
        )


    def test_s9_rondo_can_load_round(self):
        """S9: Rondo can load and dry-run its own round definitions."""
        from rondo.engine import Round, Task
        from rondo.runner import run_round
        from rondo.config import RondoConfig

        r = Round(
            name="self-test",
            tasks=[Task(name="t1", instruction="do", done_when="done")],
        )
        config = RondoConfig(dry_run=True)
        result = run_round(r, config=config)
        assert result.round_name == "self-test"
        assert result.task_results[0].status == "skipped"  # dry-run


# -- sig: mgh-6201.cd.bd955f.e4a1.5a1ce1
