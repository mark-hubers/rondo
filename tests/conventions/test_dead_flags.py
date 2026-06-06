# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Dead-flag standing lock — RONDO-333.

VER-001 verification matrix: every CLI flag is exercised by at least one test.

The campaign's most repeated bug class: surface that parses but does
nothing. `--scores` was a dead flag for weeks; the matrix `judge:` field
was parsed-but-dead; req 611 was specced-but-unbuilt. This lock makes the
CLI-flag variant extinct: a flag nobody tests is a flag nobody can trust.
"""

from __future__ import annotations

import re
from pathlib import Path

RONDO_ROOT = Path(__file__).resolve().parents[2]
CLI_PY = RONDO_ROOT / "src" / "rondo" / "cli.py"
TEST_DIRS = [RONDO_ROOT / "tests"]

# -- Flags exempt from the lock, each WITH a reason. Keep this list short:
# -- every entry is a hole the lock can't see through.
EXEMPT: dict[str, str] = {
    "--version": "argparse built-in action; behavior is argparse's, not ours",
}

_FLAG_RE = re.compile(r"""add_argument\(\s*['"](--[a-z][a-z0-9-]*)['"]""")


def _dest_of(flag: str) -> str:
    return flag.lstrip("-").replace("-", "_")


def _collect_flags() -> list[str]:
    text = CLI_PY.read_text(encoding="utf-8")
    return sorted(set(_FLAG_RE.findall(text)))


def _test_corpus() -> str:
    chunks: list[str] = []
    for d in TEST_DIRS:
        for p in d.rglob("test_*.py"):
            if p.name == "test_dead_flags.py":
                continue
            chunks.append(p.read_text(encoding="utf-8", errors="ignore"))
    return "\n".join(chunks)


class TestNoDeadFlags:
    """Every CLI flag appears (literal or dest) somewhere in the test tree."""

    def test_every_flag_is_exercised(self) -> None:
        flags = _collect_flags()
        assert len(flags) >= 20, f"flag scan looks broken — only found {len(flags)}"
        corpus = _test_corpus()
        dead = []
        for flag in flags:
            if flag in EXEMPT:
                continue
            if flag in corpus or _dest_of(flag) in corpus:
                continue
            dead.append(flag)
        assert not dead, (
            f"DEAD-FLAG ALERT — no test exercises: {dead}\n"
            f"A flag nobody tests is a flag nobody can trust (the --scores lesson). "
            f"Add a test that uses it, or add to EXEMPT with a reason."
        )

    def test_exempt_list_stays_small(self) -> None:
        """Exemptions are holes — more than 3 means the lock is rotting."""
        assert len(EXEMPT) <= 3, f"EXEMPT has {len(EXEMPT)} entries — fix tests, don't grow the list"


# -- sig: mgh-6201.cd.bd955f.844f.035cda
