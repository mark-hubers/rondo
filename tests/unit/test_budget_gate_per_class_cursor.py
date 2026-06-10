# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Regression: _BudgetGate must estimate PER provider-class, cap GLOBALLY.

VER-001 verification matrix — ROAD-TO-8 item 8.4, re-score finding R4.

THE DISEASE (src/rondo/parallel.py _BudgetGate, today): ONE global _estimate
float + ONE _have_sample bool. In a mixed round (free Claude max-auth tasks +
paid gemini/openai tasks) a $0 free success calls settle(cost=0, ok=True) →
_estimate=0.0, _have_sample=True. Every PAID task thereafter admits with est 0.0
and there is NO cold-start probe for the paid class (have_sample is already
True), so paid tasks fan out blind and the cap only bites AFTER money is spent —
under-enforcement of IFS-101 r028 / STD-107 r018 / STD-101 r212 (all MUST) in
exactly the mixed-round case rondo ships as a feature (RONDO-342 per-task cloud
routing).

THE NEW CONTRACT these tests pin (estimates per class, accounting global):
  (a) try_admit/settle take a class key (provider class string).
  (b) Estimates and sampled-state are PER class — a $0 free sample must NOT zero
      the estimate used to admit a paid-class task.
  (c) Cold-start probe is PER class — the first task of an unsampled class runs
      alone for that class; tasks of already-sampled classes are unaffected.
  (d) Estimate update is MAX-KEEP within the gate's lifetime — a later, cheaper
      paid sample never lowers a class's estimate (the $0-success rule still
      applies only when ok and cost==0, so a free class may legitimately be 0.0).
  (e) Cap accounting (spent + reserved) stays GLOBAL — one cap per round.
  (f) cap=None still disables everything.

NEW API under test (the tests DEFINE it; today's gate has the OLD no-class
signature, so most of these RED with a TypeError until the fix lands — an
acceptable RED per the item brief):
    try_admit(class_key: str) -> float | None
    settle(class_key: str, reserved: float, cost: float, ok: bool = True) -> None

These are pure-unit tests against _BudgetGate directly (no live dispatch); the
end-to-end run_parallel regimes are already pinned by
tests/unit/test_budget_gate_regimes_cursor.py and are intentionally not
duplicated here.
"""

import threading

import pytest

from rondo.parallel import _BudgetGate

# -- Float headroom for reserve/estimate equality (costs here are all >= 0.05,
# -- well above any 0.001 sample floor, so equality is exact bar fp noise).
_EPS = 1e-9


def _admit_into(gate: _BudgetGate, key: str, label: str, sink: dict, done: threading.Event) -> None:
    """Thread body: call try_admit(key), record the result under label, signal done."""
    try:
        result = gate.try_admit(key)
    finally:
        sink[label] = result
        done.set()


def test_mixed_round_free_sample_does_not_uncap_paid() -> None:
    """KILL: a $0 free success must not let paid tasks admit blind past the cap.

    cap=1.0. The free class settles $0 ok. On TODAY's global-estimate code that
    flips _have_sample True and pins _estimate 0.0, so paid tasks skip the probe
    and admit at est 0. Under the new contract the paid class is its OWN
    unsampled class: its first task is a probe (admitted alone at est 0), and
    once that probe settles at $0.60 a second paid admission must be REFUSED
    (0.60 spent + 0.60 est > 1.00 cap).
    """
    gate = _BudgetGate(cap=1.0)

    free_reserve = gate.try_admit("free")
    gate.settle("free", free_reserve, 0.0, ok=True)

    paid_probe = gate.try_admit("paid")
    assert paid_probe == pytest.approx(0.0, abs=_EPS), (
        f"paid class is unsampled — its first task must be a probe (est 0 reserve), got {paid_probe}"
    )
    gate.settle("paid", paid_probe, 0.60, ok=True)

    second_paid = gate.try_admit("paid")
    assert second_paid is None, (
        f"paid must be refused after its sample: 0.60 spent + 0.60 est > 1.00 cap, got reserve {second_paid} "
        f"— the free $0 sample leaked into paid admission (R4 under-enforcement)"
    )


def test_per_class_isolation_unsampled_class_probes() -> None:
    """A sample for one class must not become the blind estimate for another.

    gemini settles at $0.30. openai has never been sampled, so its first
    try_admit must behave as a probe (est 0 reserve), NOT a blind est-0.30
    admit borrowed from gemini's class.
    """
    gate = _BudgetGate(cap=10.0)

    gemini_probe = gate.try_admit("gemini")
    gate.settle("gemini", gemini_probe, 0.30, ok=True)

    openai_first = gate.try_admit("openai")
    assert openai_first == pytest.approx(0.0, abs=_EPS), (
        f"openai is unsampled — its first admit must probe at est 0, not inherit gemini's 0.30 (got {openai_first})"
    )


def test_estimate_is_max_keep_not_last_write() -> None:
    """A later cheaper paid sample must not lower a class's estimate.

    The paid class samples $0.50, then $0.05. MAX-KEEP means the next admission
    reserves 0.50 (the running max), never the cheaper 0.05 last-write.
    """
    gate = _BudgetGate(cap=10.0)

    first = gate.try_admit("paid")
    gate.settle("paid", first, 0.50, ok=True)

    second = gate.try_admit("paid")
    gate.settle("paid", second, 0.05, ok=True)

    third = gate.try_admit("paid")
    assert third == pytest.approx(0.50, abs=_EPS), (
        f"MAX-KEEP: estimate must stay at the 0.50 high-water mark, not drop to the 0.05 last sample (got {third})"
    )


def test_zero_success_zeroes_only_its_own_class() -> None:
    """A $0 ok sample zeroes ITS class's estimate and no other.

    free settles $0 ok (genuinely free); paid samples $0.40. A paid admit must
    reserve 0.40 while a free admit reserves 0.0 — the free zero never touches
    paid's estimate.
    """
    gate = _BudgetGate(cap=10.0)

    free_probe = gate.try_admit("free")
    gate.settle("free", free_probe, 0.0, ok=True)

    paid_probe = gate.try_admit("paid")
    gate.settle("paid", paid_probe, 0.40, ok=True)

    paid_again = gate.try_admit("paid")
    assert paid_again == pytest.approx(0.40, abs=_EPS), (
        f"paid must reserve its own 0.40 estimate, not the free class's 0.0 (got {paid_again})"
    )

    free_again = gate.try_admit("free")
    assert free_again == pytest.approx(0.0, abs=_EPS), (
        f"free must reserve 0.0 (genuinely free), not paid's 0.40 (got {free_again})"
    )


def test_cap_accounting_is_global_across_classes() -> None:
    """The cap is ONE round budget shared across all classes.

    cap=1.0. Class 'a' spends 0.70 and class 'b' samples 0.40. b's next
    admission must be refused because GLOBAL spent + b's estimate exceeds the
    cap — per-class estimates do NOT mean per-class caps.
    """
    gate = _BudgetGate(cap=1.0)

    a_probe = gate.try_admit("a")
    gate.settle("a", a_probe, 0.70, ok=True)

    b_probe = gate.try_admit("b")
    gate.settle("b", b_probe, 0.40, ok=True)

    b_again = gate.try_admit("b")
    assert b_again is None, (
        f"b must be refused: global spend (0.70 a + 0.40 b) + 0.40 b-est exceeds the 1.00 cap "
        f"— accounting must be global, got reserve {b_again}"
    )


def test_cap_none_disables_everything_for_any_class() -> None:
    """cap=None: try_admit returns 0.0 for any class and settle is a no-op.

    No budget set means no gating — every class admits at est 0 and settle must
    never raise or accumulate state that could later refuse.
    """
    gate = _BudgetGate(cap=None)

    assert gate.try_admit("gemini") == pytest.approx(0.0, abs=_EPS)
    assert gate.try_admit("openai") == pytest.approx(0.0, abs=_EPS)

    gate.settle("gemini", 0.0, 5.0, ok=True)
    gate.settle("openai", 0.0, 99.0, ok=False)

    assert gate.try_admit("gemini") == pytest.approx(0.0, abs=_EPS), (
        "cap=None must keep admitting at 0.0 regardless of settled costs"
    )


def test_probe_wait_is_per_class_threaded() -> None:
    """Cold-start probe serializes ONLY the probing class, not its peers.

    Two paid tasks start with no paid sample: exactly one admits immediately as
    the probe; the second blocks until the probe settles. A concurrent free task
    that already has a free sample admits WITHOUT waiting on paid's probe.
    Synchronization is via threading.Event with sub-2s timeouts — no sleeps.
    """
    gate = _BudgetGate(cap=2.0)

    # -- Seed the free class with a sample so it is NOT in cold-start.
    free_seed = gate.try_admit("free")
    gate.settle("free", free_seed, 0.0, ok=True)

    sink: dict[str, float | None] = {}

    # -- Probe: first paid task admits immediately, alone for the paid class.
    probe_done = threading.Event()
    probe_thread = threading.Thread(target=_admit_into, args=(gate, "paid", "probe", sink, probe_done))
    probe_thread.start()
    assert probe_done.wait(2.0), "the paid probe must admit immediately (it is the lone cold-start task)"
    assert sink["probe"] == pytest.approx(0.0, abs=_EPS), "the probe reserves est 0 (no sample yet)"

    # -- Second paid task must BLOCK while the probe is in flight (unsettled).
    waiter_done = threading.Event()
    waiter_thread = threading.Thread(target=_admit_into, args=(gate, "paid", "waiter", sink, waiter_done))
    waiter_thread.start()
    assert not waiter_done.wait(0.2), "a second paid task must wait on the in-flight probe, not admit blind"

    # -- A free task (already sampled) must admit WITHOUT waiting on paid.
    free_done = threading.Event()
    free_thread = threading.Thread(target=_admit_into, args=(gate, "free", "free", sink, free_done))
    free_thread.start()
    assert free_done.wait(1.0), "an already-sampled free task must not block on another class's probe"
    assert sink["free"] == pytest.approx(0.0, abs=_EPS), "the free task reserves its own 0.0 estimate"

    # -- Settling the probe releases the paid waiter (0.50 spent + 0.50 est <= 2.00 cap).
    gate.settle("paid", sink["probe"], 0.50, ok=True)
    assert waiter_done.wait(2.0), "the paid waiter must admit once the probe settles"
    assert sink["waiter"] is not None, "the paid waiter fits under the cap and must be admitted, not refused"

    probe_thread.join(2.0)
    waiter_thread.join(2.0)
    free_thread.join(2.0)


# -- sig: mgh-6201.cd.bd955f.32c4.26a6f6
