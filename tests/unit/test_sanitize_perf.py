# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Performance regression tests for sanitize_text — RONDO-293 (Finding #244).

VER-001: Product acceptance / unit test coverage.

Finding #244 claimed sanitize.py regex patterns would be a bottleneck on
1M+ token outputs. RONDO-293 benchmarked it and proved the claim was
theoretical, not empirical — actual behavior is linear time, no
catastrophic backtracking.

These tests lock in the observed linear scaling so future pattern changes
can't sneak in O(n^2) or worse:

Baseline (2026-04-20, Python 3.14.3, M-series Mac):
    100KB clean:  10ms
    500KB clean:  49ms  (~5x size -> ~5x time, linear)
    1MB clean:    100ms (~2x size -> ~2x time, linear)
    1MB mixed:    144ms (1MB with 500 secrets, adds ~45ms for replacements)

Test budgets are generous (2x-3x baseline) to account for slower CI boxes,
but catch any super-linear regression.
"""

from __future__ import annotations

import time

import pytest

from rondo.sanitize import sanitize_text


def _clean_text(kb: int) -> str:
    """Generate N KB of clean Latin text (no secrets, no homoglyphs)."""
    unit = "lorem ipsum dolor sit amet consectetur adipiscing elit sed "  # 60 chars
    return unit * (kb * 1024 // len(unit) + 1)


@pytest.mark.perf
class TestSanitizePerformance:
    """Linear-scaling regression tests. Skipped by default (use -m perf)."""

    def test_100kb_under_50ms(self) -> None:
        text = _clean_text(100)
        t0 = time.perf_counter()
        sanitize_text(text)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        assert elapsed_ms < 50, f"100KB took {elapsed_ms:.1f}ms, budget 50ms"

    def test_500kb_under_200ms(self) -> None:
        text = _clean_text(500)
        t0 = time.perf_counter()
        sanitize_text(text)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        assert elapsed_ms < 200, f"500KB took {elapsed_ms:.1f}ms, budget 200ms"

    def test_1mb_under_400ms(self) -> None:
        text = _clean_text(1024)
        t0 = time.perf_counter()
        sanitize_text(text)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        assert elapsed_ms < 400, f"1MB took {elapsed_ms:.1f}ms, budget 400ms"

    def test_scaling_is_linear_not_quadratic(self) -> None:
        """Ratio between 100KB and 500KB times must be ~5x, not ~25x.

        Catches regex patterns that introduce catastrophic backtracking
        (which would produce O(n^2) or worse scaling).
        """
        small = _clean_text(100)
        t0 = time.perf_counter()
        sanitize_text(small)
        small_ms = (time.perf_counter() - t0) * 1000

        large = _clean_text(500)
        t0 = time.perf_counter()
        sanitize_text(large)
        large_ms = (time.perf_counter() - t0) * 1000

        if small_ms <= 0:
            pytest.skip("Timer resolution too coarse for 100KB case")

        ratio = large_ms / small_ms
        ## Linear would be ~5x. Allow up to 10x for noise. Fail at >15x (super-linear).
        assert ratio < 15, (
            f"Super-linear scaling detected: 500KB/100KB ratio = {ratio:.1f}x "
            f"(small={small_ms:.1f}ms, large={large_ms:.1f}ms). Budget: 15x."
        )


# -- sig: mgh-6201.cd.bd955f.d244.f3b244
