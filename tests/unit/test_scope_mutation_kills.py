# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Mutation kill-tests for rondo.scope — the scope guard, proven to bite.

VER-001: Product acceptance / mutation-adequacy coverage.

AUTHOR NOTE: Claude-authored — the MUTATION GATE is the independent referee
(RONDO-363). The cursor-authored regression suite (test_scope_guard_cursor.py)
asserts LOOSE bounds (score <= 1, score >= threshold), so the scoring
arithmetic and the threshold boundary survived mutation. These tests pin
EXACT scores so a flipped boundary, a broken clamp, or a changed operator
fails loudly. Measured sweep (bin/mutate --timeout-per-mutant 30, 2026-06-12):
5/10 -> 10/10 caught (100%). Every asserted score was computed from the live
function before being written — no guessed numbers.

The scope guard is an anti-lying primitive: a fat step has many places to
fudge, a one-thing step has none. If its scoring can be silently broken, the
guard can be silently disabled — hence the exact pins.
"""

from __future__ import annotations

from rondo.scope import is_over_threshold, scope_score


def test_threshold_boundary_is_inclusive_at_three() -> None:
    """A prompt scoring EXACTLY 3 is over threshold (kills L21 3->4 and L71 >= -> >)."""
    three_bullets = "- alpha\n- beta\n- gamma"
    assert scope_score(three_bullets)["score"] == 3
    assert is_over_threshold(three_bullets) is True


def test_no_paths_contributes_zero() -> None:
    """Zero file paths -> zero path contribution (kills the L61 max(0,...) -> max(1,...))."""
    res = scope_score("just refactor the helper function cleanly")
    assert res["score"] == 0
    assert res["signals"] == []


def test_two_paths_is_one_extra() -> None:
    """Two distinct paths -> exactly one EXTRA beyond the first (kills the L61 len-1 literal)."""
    # -- " and " is NOT a counted conjunction, so this isolates the path arithmetic
    res = scope_score("edit alpha.py and beta.py")
    assert res["score"] == 1


def test_score_is_additive_across_signal_kinds() -> None:
    """1 conjunction + 2 sub-tasks = 3, additively (kills the L65 + -> * / - arith mutant)."""
    # -- 1*2=2 and 1-2=-1 both differ from the additive 3
    prompt = "do the thing additionally fix it\n- step a\n- step b"
    res = scope_score(prompt)
    assert res["score"] == 3
    assert len(res["signals"]) == 2


# -- sig: mgh-6201.cd.bd955f.6499.a38a37
