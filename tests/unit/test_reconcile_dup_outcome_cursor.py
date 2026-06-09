# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Regression: reconcile SHALL NOT create a DUPLICATE OUTCOME — STD-110 req 018.

VER-001 verification matrix — RONDO-359 reconcile (cursor-review findings #5 + #6,
spec STD-110 req 018: "Reconciliation ... SHALL NOT create duplicate OUTCOME
records nor re-dispatch a dispatch already completed by another worker").

One code path (src/rondo/audit.py reconcile_stuck_intents → _reconcile_locked →
_scan_intents_and_outcomes), two race windows that each leave TWO OUTCOME records
for one dispatch_id — the exact thing req 018 forbids:

    Finding #5 (still-alive dispatch):
        AuditConfig.stuck_after_sec defaults to 300s, but a real cloud dispatch
        legitimately runs up to the cloud panel timeout (_CLOUD_PANEL_TIMEOUT_SEC
        = 600s, mcp_compose.py). A dispatch still alive at e.g. 400s ages past the
        300s threshold with no OUTCOME yet. A peer worker building a fresh
        AuditTrail auto-reconciles, sees the aged INTENT, and writes a synthetic
        'stuck' OUTCOME (error_code='ERR_RECONCILED_STUCK'). The real dispatch
        then completes and writes its GENUINE OUTCOME → TWO OUTCOME records for
        one dispatch_id. req 017 says an in-flight dispatch younger than the
        max dispatch timeout SHALL NEVER be declared stuck.

    Finding #6 (torn read):
        _scan_intents_and_outcomes reads the JSONL with read_text().splitlines()
        while holding ONLY the .reconcile.lock sidecar — NOT the JSONL append
        lock (req 016). A concurrent append can leave the final line torn;
        json.loads skips it. If the skipped line was the OUTCOME for an aged
        INTENT, reconcile concludes the dispatch is stuck and double-writes a
        synthetic OUTCOME on top of the genuine (torn) one.

These tests assert the OBSERVABLE guarantee — the count of OUTCOME records per
dispatch_id — NOT any internal method name, branch, or fix shape. Any correct fix
(age threshold lifted to the max dispatch timeout, append-lock-guarded read, or
torn-final-line tolerance) satisfies them.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta

from rondo.audit import AuditConfig, AuditRecord, AuditTrail

# -- The synthetic OUTCOME error_code reconcile stamps on a "stuck" INTENT.
_STUCK_ERROR_CODE = "ERR_RECONCILED_STUCK"

# -- The longest a genuine dispatch may legitimately run before it is truly
#    stuck: the cloud panel timeout (_CLOUD_PANEL_TIMEOUT_SEC in mcp_compose.py).
#    reconcile MUST NOT declare an INTENT younger than this as stuck (req 017).
_MAX_DISPATCH_TIMEOUT_SEC = 600

# -- A dispatch still alive at this age: past the 300s default stuck_after_sec
#    (so current code wrongly reconciles it) but well under the 600s real ceiling
#    (so it is genuinely still in flight, not stuck).
_ALIVE_AGE_SEC = 400


def _jsonl_path(audit_dir: str) -> str:
    """Absolute path of the audit JSONL inside audit_dir."""
    return os.path.join(audit_dir, "rondo_audit.jsonl")


def _append_raw(audit_dir: str, text: str) -> None:
    """Append one raw, newline-terminated line to the JSONL (bypasses AuditTrail).

    Newline-terminated even when `text` is deliberately torn JSON, so that a
    subsequent genuine append lands on its own line — this isolates the reconcile
    behaviour under test from any line-merging side effect of a missing newline.
    """
    os.makedirs(audit_dir, exist_ok=True)
    with open(_jsonl_path(audit_dir), "a", encoding="utf-8") as f:
        f.write(text + "\n")


def _seed_intent_line(audit_dir: str, dispatch_id: str, *, age_sec: float) -> None:
    """Write a valid INTENT record whose dispatched_at is `age_sec` in the past."""
    dispatched_at = (datetime.now(UTC) - timedelta(seconds=age_sec)).isoformat()
    rec = AuditRecord(
        dispatch_id=dispatch_id,
        task_name="genuine-task",
        round_name="r",
        model="m",
        status="INTENT",
        dispatched_at=dispatched_at,
    )
    _append_raw(audit_dir, json.dumps(rec.to_dict()))


def _records_for(audit_dir: str, dispatch_id: str) -> list[dict]:
    """All PARSEABLE records in the JSONL with the given dispatch_id."""
    out: list[dict] = []
    with open(_jsonl_path(audit_dir), encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("dispatch_id") == dispatch_id:
                out.append(rec)
    return out


def _outcome_records(audit_dir: str, dispatch_id: str) -> list[dict]:
    """OUTCOME records (terminal: status != 'INTENT') for a dispatch_id."""
    return [r for r in _records_for(audit_dir, dispatch_id) if r.get("status") != "INTENT"]


def _stuck_outcomes(audit_dir: str, dispatch_id: str) -> list[dict]:
    """Synthetic 'stuck' OUTCOME records reconcile manufactured for a dispatch_id."""
    return [r for r in _records_for(audit_dir, dispatch_id) if r.get("error_code") == _STUCK_ERROR_CODE]


def test_reconcile_then_genuine_outcome_yields_single_outcome(tmp_path) -> None:
    """Finding #5: a reconciled-stuck INTENT that then completes must not double-write.

    Seed an INTENT aged 400s (past the 300s default, under the 600s cloud ceiling),
    run reconcile under the PRODUCTION default threshold, then write the dispatch's
    GENUINE OUTCOME via record_outcome — the real "I was slow, not stuck" sequence.
    STD-110 req 018: there must be AT MOST ONE OUTCOME for that dispatch_id.

    Current code marks the 400s INTENT stuck (400 > 300) and then the genuine
    'done' OUTCOME lands too → TWO OUTCOME records → this fails. Any fix that keeps
    reconcile off an INTENT younger than the max dispatch timeout leaves exactly the
    one genuine OUTCOME.
    """
    audit_dir = str(tmp_path)
    dispatch_id = "dsp_slow_but_alive"
    _seed_intent_line(audit_dir, dispatch_id, age_sec=_ALIVE_AGE_SEC)

    # -- Default config => production stuck_after_sec (300s); reconcile with no
    #    argument resolves to that default (the path auto_reconcile takes).
    trail = AuditTrail(config=AuditConfig(audit_dir=audit_dir), auto_reconcile=False)
    trail.reconcile_stuck_intents()

    # -- The real dispatch finishes and records its genuine terminal OUTCOME.
    trail.record_outcome(dispatch_id=dispatch_id, status="done", exit_code=0)

    outcomes = _outcome_records(audit_dir, dispatch_id)
    assert len(outcomes) == 1, (
        f"STD-110 req 018: a slow-but-alive dispatch must have AT MOST ONE OUTCOME, "
        f"found {len(outcomes)} for {dispatch_id}: {[r.get('status') for r in outcomes]} "
        f"(reconcile manufactured a duplicate stuck OUTCOME for a dispatch still in flight)"
    )


def test_reconcile_leaves_dispatch_younger_than_cloud_timeout_alone(tmp_path) -> None:
    """Finding #5 (req 017): an INTENT younger than the max dispatch timeout is NOT stuck.

    A dispatch aged 400s is still legitimately in flight (the cloud panel timeout is
    600s). reconcile under the production default threshold MUST leave it alone — it
    SHALL NEVER declare a still-running peer dispatch stuck. Current code (default
    300s) wrongly stamps it ERR_RECONCILED_STUCK; this asserts none was written.
    """
    audit_dir = str(tmp_path)
    dispatch_id = "dsp_in_flight_under_ceiling"
    assert _ALIVE_AGE_SEC < _MAX_DISPATCH_TIMEOUT_SEC  # -- guard the premise
    _seed_intent_line(audit_dir, dispatch_id, age_sec=_ALIVE_AGE_SEC)

    trail = AuditTrail(config=AuditConfig(audit_dir=audit_dir), auto_reconcile=False)
    trail.reconcile_stuck_intents()

    stuck = _stuck_outcomes(audit_dir, dispatch_id)
    assert not stuck, (
        f"STD-110 req 017: a dispatch aged {_ALIVE_AGE_SEC}s (< {_MAX_DISPATCH_TIMEOUT_SEC}s "
        f"cloud timeout) is still in flight and must NEVER be declared stuck, but "
        f"reconcile wrote {len(stuck)} synthetic stuck OUTCOME(s) for {dispatch_id}"
    )


def test_reconcile_ignores_torn_final_outcome_line(tmp_path) -> None:
    """Finding #6: a torn final OUTCOME line must not provoke a duplicate stuck OUTCOME.

    Seed an aged INTENT and then a TORN (truncated, unparseable) final line that is
    the dispatch's genuine 'done' OUTCOME caught mid-append by a concurrent writer —
    the dispatch has in fact already completed. _scan_intents_and_outcomes reads with
    read_text().splitlines() under only the .reconcile.lock sidecar, so json.loads
    skips the torn line and reconcile sees an INTENT with no OUTCOME.

    Current code therefore manufactures a synthetic stuck OUTCOME on top of the
    genuine (torn) one — a duplicate, exactly what STD-110 req 018 forbids. A fix
    that reads under the append lock (req 016) or refuses to draw "stuck" conclusions
    from a torn snapshot writes no such record. stuck_after_sec=0 here isolates the
    torn-read fault from the age-threshold fault of Finding #5.
    """
    audit_dir = str(tmp_path)
    dispatch_id = "dsp_torn_outcome"
    _seed_intent_line(audit_dir, dispatch_id, age_sec=_ALIVE_AGE_SEC)

    # -- The genuine terminal OUTCOME, then truncated to simulate a torn append.
    genuine = AuditRecord(
        dispatch_id=dispatch_id,
        task_name="genuine-task",
        status="done",
        exit_code=0,
        completed_at=datetime.now(UTC).isoformat(),
    )
    full = json.dumps(genuine.to_dict())
    torn = full[: len(full) // 2]  # -- mid-record cut => json.loads will fail
    assert _is_unparseable(torn)  # -- guard: the planted line truly is torn
    _append_raw(audit_dir, torn)

    trail = AuditTrail(config=AuditConfig(audit_dir=audit_dir, stuck_after_sec=0), auto_reconcile=False)
    trail.reconcile_stuck_intents(stuck_after_sec=0)

    stuck = _stuck_outcomes(audit_dir, dispatch_id)
    assert not stuck, (
        f"STD-110 req 018: reconcile read a torn final line under the wrong lock, "
        f"missed the genuine OUTCOME for already-completed {dispatch_id}, and wrote "
        f"{len(stuck)} duplicate stuck OUTCOME(s)"
    )


def _is_unparseable(text: str) -> bool:
    """True if `text` is not valid JSON (used to guard the torn-line premise)."""
    try:
        json.loads(text)
    except json.JSONDecodeError:
        return True
    return False


# -- sig: mgh-6201.cd.bd955f.4320.efb791
