# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""API-stability standing lock — RONDO-340.

VER-001 verification matrix: the declared stable surface in
docs/API-STABILITY.md is DERIVED from source, never hand-maintained.

SOP-106 dimension 9 (API stability) requires "stable surfaces declared;
deprecation policy". A stability doc that drifts from the real CLI/MCP
surface is worse than no doc: it is a promise nobody checks. This lock
makes the doc a contract — every CLI subcommand registered in cli.py and
every MCP tool registered in mcp_server.py MUST appear in the doc, and
the doc MUST state a deprecation policy.
"""

from __future__ import annotations

import re
from pathlib import Path

RONDO_ROOT = Path(__file__).resolve().parents[2]
CLI_PY = RONDO_ROOT / "src" / "rondo" / "cli.py"
MCP_SERVER_PY = RONDO_ROOT / "src" / "rondo" / "mcp_server.py"
STABILITY_DOC = RONDO_ROOT / "docs" / "API-STABILITY.md"

_CMD_RE = re.compile(r"""add_parser\(\s*\n?\s*['"]([a-z][a-z0-9-]*)['"]""")
_TOOL_RE = re.compile(r"""name=['"](rondo_[a-z_]+)['"]""")


def _cli_commands() -> list[str]:
    text = CLI_PY.read_text(encoding="utf-8")
    return sorted(set(_CMD_RE.findall(text)))


def _mcp_tools() -> list[str]:
    text = MCP_SERVER_PY.read_text(encoding="utf-8")
    return sorted(set(_TOOL_RE.findall(text)))


def _doc_text() -> str:
    assert STABILITY_DOC.exists(), (
        "docs/API-STABILITY.md is missing — SOP-106 dim 9 requires the stable surface to be declared (RONDO-340)"
    )
    return STABILITY_DOC.read_text(encoding="utf-8")


class TestApiStabilityLock:
    """The stability doc covers the REAL surface, derived from source."""

    def test_surface_is_nonempty(self) -> None:
        """Sanity: the regexes still match the source idiom."""
        assert len(_cli_commands()) >= 20, "CLI command regex matched too few — idiom changed?"
        assert len(_mcp_tools()) >= 20, "MCP tool regex matched too few — idiom changed?"

    def test_every_cli_command_is_declared(self) -> None:
        """Every registered CLI subcommand appears in API-STABILITY.md."""
        doc = _doc_text()
        missing = [c for c in _cli_commands() if not re.search(rf"`{re.escape(c)}`", doc)]
        assert not missing, (
            f"CLI commands missing from docs/API-STABILITY.md: {missing} — "
            "declare each as stable or experimental, never omit"
        )

    def test_every_mcp_tool_is_declared(self) -> None:
        """Every registered MCP tool appears in API-STABILITY.md."""
        doc = _doc_text()
        missing = [t for t in _mcp_tools() if t not in doc]
        assert not missing, (
            f"MCP tools missing from docs/API-STABILITY.md: {missing} — "
            "declare each as stable or experimental, never omit"
        )

    def test_deprecation_policy_is_stated(self) -> None:
        """The doc states the deprecation policy (warn one minor version)."""
        doc = _doc_text()
        assert "## Deprecation policy" in doc, "doc must have a '## Deprecation policy' section"
        assert "one minor version" in doc, "policy must state the warn window: 'one minor version' before removal"

    def test_exit_codes_are_declared_stable(self) -> None:
        """The exit-code contract (RONDO-335) is part of the stable surface."""
        doc = _doc_text()
        for code in ("0", "1", "2", "130"):
            assert re.search(rf"\b{code}\b", doc), f"exit code {code} missing from stability doc"


# -- sig: mgh-6201.cd.bd955f.e008.4ba3a0
