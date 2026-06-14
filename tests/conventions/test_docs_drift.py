# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Standing docs-drift detector — REQ-111 req 611 (RONDO-326).

VER-001 verification matrix: stale model IDs in examples/docs caught in CI.

The scanner exists (RONDO-325); a detector nobody runs is no detector
(170 stale F-refs once survived 2 sessions undetected — the Session 81
lesson). This test makes the SUITE the standing detector: every test run
re-scans examples/ + docs/ against the live registry cache. Skips cleanly
on machines with no cache (CI without keys) — `rondo models --docs-drift`
covers those via its exit-1 contract.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from rondo.model_registry import docs_drift, load_cache

RONDO_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = RONDO_ROOT / "src" / "rondo"

# -- RONDO-432: ground-truth counters (cheap — read source, never run pytest).
# -- Same idioms the api-stability + generate_index locks already trust.
_ADD_PARSER_RE = re.compile(r"""add_parser\(\s*\n?\s*['"]([a-z][a-z0-9-]*)['"]""")


def _mcp_tool_count() -> int:
    """Authoritative MCP-tool count = @mcp.tool() registrations in mcp_server.py."""
    return len(re.findall(r"@mcp\.tool\(", (SRC_DIR / "mcp_server.py").read_text(encoding="utf-8")))


def _cli_command_count() -> int:
    """Authoritative CLI-subcommand count = add_parser() calls in cli.py."""
    return len(set(_ADD_PARSER_RE.findall((SRC_DIR / "cli.py").read_text(encoding="utf-8"))))


def _example_count() -> int:
    """Authoritative example count = EXPECTED_EXAMPLE_COUNT in generate_index.py (the existing lock)."""
    text = (RONDO_ROOT / "examples" / "generate_index.py").read_text(encoding="utf-8")
    m = re.search(r"EXPECTED_EXAMPLE_COUNT\s*=\s*(\d+)", text)
    assert m, "EXPECTED_EXAMPLE_COUNT not found — generate_index.py idiom changed"
    return int(m.group(1))


class TestDocsDriftStanding:
    """Every suite run re-proves the examples/docs reference live models."""

    def test_examples_and_docs_reference_served_models(self) -> None:
        cache = load_cache()
        if cache is None:
            pytest.skip("no registry cache on this machine — run: rondo providers --refresh")
        roots = [str(RONDO_ROOT / d) for d in ("examples", "docs") if (RONDO_ROOT / d).is_dir()]
        assert roots, "examples/ and docs/ both missing — wrong root resolution"
        hits = docs_drift(cache, roots)
        pretty = "\n  ".join(f"{h['file']}:{h['line']} {h['model']}" for h in hits)
        assert not hits, f"stale model IDs in docs/examples (req 611) — stale docs teach dead dispatches:\n  {pretty}"


class TestDocNumberDrift:
    """RONDO-432: every COUNT stated in a front-door doc must match ground truth.

    The 2026-06-14 truth-audit found docs claiming 85/92/107 examples, 23 MCP
    tools, 24 CLI commands while the code had 101/27/25. Names were locked
    (api-stability) and the example count was locked (generate_index), but the
    counts written in prose/headers were not — so they drifted across five files.
    This lock pins them: a hand-typed number that lies fails the build.

    Each claim = (relative file, single-group regex, ground-truth value, label).
    Every match of the regex in that file must equal the ground-truth value.
    """

    def _claims(self) -> list[tuple[str, str, int, str]]:
        mcp, cli, ex = _mcp_tool_count(), _cli_command_count(), _example_count()
        return [
            # -- MCP tool count (=27)
            ("docs/RONDO-REFERENCE.md", r"\*\*MCP Tools:\*\*\s*(\d+)", mcp, "REFERENCE header"),
            ("docs/RONDO-REFERENCE.md", r"##\s*MCP Tools\s*\((\d+)\)", mcp, "REFERENCE section"),
            ("docs/RONDO-REFERENCE.md", r"\|\s*MCP tools\s*\|\s*(\d+)\s*\|", mcp, "REFERENCE key-numbers"),
            ("docs/API-STABILITY.md", r"##\s*Stable surface 2: MCP tools\s*\((\d+)\)", mcp, "API-STABILITY header"),
            # -- CLI subcommand count (=25)
            ("docs/RONDO-REFERENCE.md", r"##\s*CLI Commands\s*\((\d+)\)", cli, "REFERENCE section"),
            ("docs/RONDO-REFERENCE.md", r"\|\s*CLI commands\s*\|\s*(\d+)\s*\|", cli, "REFERENCE key-numbers"),
            (
                "docs/API-STABILITY.md",
                r"##\s*Stable surface 1: CLI subcommands\s*\((\d+)\)",
                cli,
                "API-STABILITY header",
            ),
            # -- example count (=101)
            ("README.md", r"(\d+)\s+real, runnable files", ex, "README intro"),
            ("README.md", r"all\s+(\d+)\s+examples mapped", ex, "README index pointer"),
        ]

    def test_doc_counts_match_ground_truth(self) -> None:
        """No stated example/MCP/CLI count in the front-door docs may drift from the code."""
        mismatches: list[str] = []
        for rel, pattern, expected, label in self._claims():
            text = (RONDO_ROOT / rel).read_text(encoding="utf-8")
            found = re.findall(pattern, text)
            assert found, f"{rel} ({label}): pattern {pattern!r} matched nothing — doc idiom changed, lock is blind"
            for got in found:
                if int(got) != expected:
                    mismatches.append(f"{rel} ({label}): says {got}, ground truth is {expected}")
        assert not mismatches, "doc count drift (RONDO-432) — a hand-typed number lies:\n  " + "\n  ".join(mismatches)

    def test_ascii_diagram_counts_match(self) -> None:
        """The RONDO-REFERENCE architecture diagram's 'N commands  M tools' line must be current too."""
        text = (RONDO_ROOT / "docs" / "RONDO-REFERENCE.md").read_text(encoding="utf-8")
        m = re.search(r"(\d+)\s+commands\s+(\d+)\s+tools", text)
        assert m, "REFERENCE ascii diagram 'N commands M tools' line not found — idiom changed"
        cmds, tools = int(m.group(1)), int(m.group(2))
        assert cmds == _cli_command_count(), (
            f"REFERENCE diagram says {cmds} commands, ground truth {_cli_command_count()}"
        )
        assert tools == _mcp_tool_count(), f"REFERENCE diagram says {tools} tools, ground truth {_mcp_tool_count()}"


# -- sig: mgh-6201.cd.bd955f.2212.43f733
