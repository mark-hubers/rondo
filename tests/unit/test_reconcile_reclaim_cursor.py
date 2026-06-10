# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Regression: auto-reconcile-on-init is once-per-PROCESS, not once-per-interval.

VER-001 verification matrix — holistic-review finding #3 (RONDO-371 follow-up).

THE BUG (observable failure this file pins):
    src/rondo/audit.py _claim_auto_reconcile() records each audit file in a
    process-global set (_auto_reconciled_files) FOREVER. The MCP server is a
    long-lived process: it reconciles the jsonl ONCE at the first AuditTrail
    construction, then never again for that file's lifetime. A dispatch that
    crashes mid-flight AFTER startup leaves an INTENT with no OUTCOME that
    auto-reconcile never touches until the server restarts — the STD-110/STD-113
    stuck-intent guarantee silently lapses for the primary deployment.

THE INTENDED CONTRACT (tested as OBSERVABLE behavior, not mechanism):
    auto-reconcile-on-init runs at most once per re-claim INTERVAL per audit
    file (a module constant the fix adds, e.g. _AUTO_RECONCILE_INTERVAL_SEC —
    monkeypatchable), instead of once per process lifetime. So:
      - a burst of AuditTrail constructions within the interval reconciles at
        most once (the RONDO-371 storm protection MUST be preserved);
      - after the interval elapses, a NEW AuditTrail construction reconciles
        AGAIN and catches intents that got stuck since the first scan.

The RECLAIM test FAILS on current code (the process-global set blocks the second
run forever) and PASSES once the interval-gated fix lands. The STORM test is the
rail: it PASSES before AND after the fix so the fix cannot reintroduce the
per-construction reconcile storm RONDO-371 removed. Seeding/reading patterns
mirror tests/unit/test_reconcile_scalability_cursor.py.
"""

import json
import threading
import time
from pathlib import Path
from unittest.mock import patch

import rondo.audit as audit_mod
from rondo.audit import AuditConfig, AuditTrail

_AUDIT_JSONL = "rondo_audit.jsonl"

# -- Generous timing margins: a tiny re-claim interval plus a sleep well past it
#    keeps the RECLAIM test deterministic on a loaded CI box without flaking.
_RECLAIM_INTERVAL_SEC = 0.05
_SLEEP_PAST_INTERVAL_SEC = 0.30

# -- Enough rapid constructions that "once per construction" (the bug RONDO-371
#    fixed) is unmistakably distinct from the bounded "<= 1 per interval" rail.
_BURST_COUNT = 6


def _reset_auto_reconcile_state() -> None:
    """Clear any process-global auto-reconcile bookkeeping under its guard.

    Defensive across the rename the fix may make: clears the current
    _auto_reconciled_files set AND any module-level set/dict whose name starts
    with '_auto_reconcile' (e.g. a timestamp map the fix introduces). The
    threading.Lock guard is skipped (it is neither a set nor a dict).
    """
    guard = getattr(audit_mod, "_auto_reconcile_guard", None)
    if guard is not None:
        guard.acquire()
    try:
        for name in dir(audit_mod):
            if not name.startswith("_auto_reconcile"):
                continue
            container = getattr(audit_mod, name)
            if isinstance(container, (set, dict)):
                container.clear()
    finally:
        if guard is not None:
            guard.release()


def _stuck_dispatch_ids(jsonl: Path) -> set[str]:
    """Return dispatch_ids that have a synthetic ERR_RECONCILED_STUCK outcome."""
    ids: set[str] = set()
    for line in jsonl.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        if rec.get("status") == "stuck" and rec.get("error_code") == "ERR_RECONCILED_STUCK":
            ids.add(rec.get("dispatch_id", ""))
    return ids


def _seed_stuck_intent(audit_dir: Path, *, task_name: str) -> str:
    """Append one INTENT with no OUTCOME (a crashed dispatch); return its id.

    Uses auto_reconcile=False so seeding neither reconciles nor claims the
    process-global slot — it only grows the jsonl with a stuck INTENT.
    """
    seed = AuditTrail(
        config=AuditConfig(audit_dir=str(audit_dir), stuck_after_sec=0),
        auto_reconcile=False,
    )
    rec = seed.record_intent(
        task_name=task_name,
        round_name="prior",
        model="sonnet",
        prompt=f"orphaned dispatch {task_name} with no outcome",
    )
    return rec.dispatch_id


def test_auto_reconcile_reclaims_after_interval(tmp_path, monkeypatch) -> None:
    """A post-interval AuditTrail MUST reconcile AGAIN, catching newly-stuck intents.

    Models the long-lived MCP server: the FIRST AuditTrail reconciles and claims
    the slot; a dispatch then crashes mid-flight (INTENT #2, no OUTCOME) AFTER
    that scan; the re-claim interval elapses; a NEW AuditTrail is constructed.
    With the interval-gated fix it reconciles again and writes
    ERR_RECONCILED_STUCK for INTENT #2. On current code the process-global set
    blocks the second run forever, INTENT #2 stays orphaned, and this FAILS —
    which is the regression this test pins.
    """
    audit_dir = tmp_path / "audit"
    jsonl = audit_dir / _AUDIT_JSONL

    _reset_auto_reconcile_state()
    # -- Shrink the re-claim interval. raising=False: the constant does not exist
    #    yet on current (buggy) code; the fix will add it as a module global.
    monkeypatch.setattr(audit_mod, "_AUTO_RECONCILE_INTERVAL_SEC", _RECLAIM_INTERVAL_SEC, raising=False)

    # -- INTENT #1 makes the jsonl exist so the first construction reconciles.
    _seed_stuck_intent(audit_dir, task_name="crashed-before-startup")

    # -- Trail A: first auto-reconcile construction — claims the slot and writes
    #    ERR_RECONCILED_STUCK for INTENT #1.
    trail_a = AuditTrail(
        config=AuditConfig(audit_dir=str(audit_dir), stuck_after_sec=0),
        auto_reconcile=True,
    )

    # -- A dispatch crashes mid-flight AFTER the first scan: INTENT #2, no OUTCOME.
    crashed = trail_a.record_intent(
        task_name="crashed-after-startup",
        round_name="live",
        model="sonnet",
        prompt="dispatch that crashed after the server already reconciled once",
    )

    # -- Let the re-claim interval lapse, then build a NEW AuditTrail (the next
    #    dispatch in the same long-lived process).
    time.sleep(_SLEEP_PAST_INTERVAL_SEC)
    AuditTrail(
        config=AuditConfig(audit_dir=str(audit_dir), stuck_after_sec=0),
        auto_reconcile=True,
    )

    reconciled = _stuck_dispatch_ids(jsonl)
    assert crashed.dispatch_id in reconciled, (
        "auto-reconcile-on-init is once-per-PROCESS: the first AuditTrail "
        "reconciled and claimed the slot forever, so a dispatch that got stuck "
        "AFTER that scan never receives its ERR_RECONCILED_STUCK outcome until "
        "the process restarts. After the re-claim interval a NEW AuditTrail must "
        "reconcile again and catch it (holistic-review finding #3)."
    )


def test_auto_reconcile_storm_protection_within_interval(tmp_path, monkeypatch) -> None:
    """Rail: a burst of constructions within the interval reconciles at most ONCE.

    Preserves RONDO-371 storm protection: with a LARGE re-claim interval, N rapid
    AuditTrail constructions over the same jsonl must fire reconcile_stuck_intents
    at most once (not once per construction). A thread-safe counting wrapper on
    AuditTrail.reconcile_stuck_intents measures it. Passes before AND after the
    interval-gated fix, so the fix cannot reintroduce the per-task scan storm.
    """
    audit_dir = tmp_path / "audit"

    _reset_auto_reconcile_state()
    # -- Large interval so EVERY construction in the burst falls inside one window.
    monkeypatch.setattr(audit_mod, "_AUTO_RECONCILE_INTERVAL_SEC", 3600, raising=False)

    # -- A stuck INTENT makes the jsonl exist so reconcile-on-init is eligible.
    _seed_stuck_intent(audit_dir, task_name="crashed")

    calls = {"n": 0}
    count_lock = threading.Lock()
    original = AuditTrail.reconcile_stuck_intents

    def _counting(self: AuditTrail, *args: object, **kwargs: object) -> int:
        with count_lock:
            calls["n"] += 1
        return original(self, *args, **kwargs)

    with patch.object(audit_mod.AuditTrail, "reconcile_stuck_intents", _counting):
        for _ in range(_BURST_COUNT):
            AuditTrail(
                config=AuditConfig(audit_dir=str(audit_dir), stuck_after_sec=0),
                auto_reconcile=True,
            )

    assert calls["n"] <= 1, (
        f"reconcile storm: reconcile_stuck_intents ran {calls['n']} times for "
        f"{_BURST_COUNT} AuditTrail constructions inside one re-claim interval — "
        "must be <= 1 (RONDO-371 storm protection must hold; holistic-review finding #3)"
    )


# -- sig: mgh-6201.cd.bd955f.c3f6.ad76be
