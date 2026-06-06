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

from pathlib import Path

import pytest

from rondo.model_registry import docs_drift, load_cache

RONDO_ROOT = Path(__file__).resolve().parents[2]


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


# -- sig: mgh-6201.cd.bd955f.2212.0d6640
