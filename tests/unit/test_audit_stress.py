# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Cross-process audit state stress test — STD-110 req 020 (verify-first).

Finding #257 (Gemini+Grok rated HIGH): INTENT→OUTCOME transitions over a
shared JSONL with concurrent workers could mark valid in-flight dispatches
"stuck" and re-dispatch them. STD-113 reqs 017-019 added the age-threshold
mitigation; STD-110 reqs 016-019 spec a flock layer ON TOP — but the
campaign rule is VERIFY-FIRST: this test decides whether the flock layer
is built at all. If ≥25 concurrent workers cannot produce a false-stuck or
a duplicate/torn record, the heuristic stands and the flock work is closed
as not-needed (with this test as the permanent guard).

VER-001 verification matrix: concurrent audit writes stay uncorrupted.
"""

import json
import multiprocessing as mp
from pathlib import Path

WORKERS = 25
DISPATCHES_PER_WORKER = 8


def _worker(audit_dir: str, worker_id: int) -> int:
    """Each worker: record intents+outcomes while reconciling aggressively."""
    import sys

    sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
    from rondo.audit import AuditConfig, AuditTrail

    trail = AuditTrail(config=AuditConfig(audit_dir=audit_dir, stuck_after_sec=300))
    for n in range(DISPATCHES_PER_WORKER):
        rec = trail.record_intent(task_name=f"w{worker_id}-t{n}", round_name="stress", model="m", prompt="p")
        # -- reconcile mid-flight from EVERY worker: the Finding #257 attack —
        # -- a peer must NOT mark our young in-flight INTENT as stuck
        trail.reconcile_stuck_intents()
        trail.record_outcome(dispatch_id=rec.dispatch_id, status="done", cost_usd=0.001, duration_sec=0.01)
    return worker_id


class TestCrossProcessAuditStress:
    """STD-110 req 020: ≥20 concurrent workers, zero false-stuck, zero torn lines."""

    def test_concurrent_workers_no_false_stuck_no_torn_records(self, tmp_path: Path) -> None:
        audit_dir = str(tmp_path / "audit")
        ctx = mp.get_context("spawn")
        with ctx.Pool(processes=WORKERS) as pool:
            results = pool.starmap(_worker, [(audit_dir, w) for w in range(WORKERS)])
        assert len(results) == WORKERS

        # -- verify the shared JSONL with everything settled
        lines = (Path(audit_dir) / "rondo_audit.jsonl").read_text(encoding="utf-8").strip().split("\n")
        records = []
        torn = 0
        for line in lines:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                torn += 1
        assert torn == 0, f"{torn} torn/interleaved JSONL lines — flock layer IS needed"

        expected = WORKERS * DISPATCHES_PER_WORKER
        intents = [r for r in records if r.get("status") == "INTENT"]
        outcomes = [r for r in records if r.get("status") != "INTENT"]
        stuck = [r for r in outcomes if r.get("error_code") == "ERR_RECONCILED_STUCK"]
        done = [r for r in outcomes if r.get("status") == "done"]

        assert len(stuck) == 0, (
            f"{len(stuck)} FALSE-STUCK records under concurrency — Finding #257 reproduced, flock layer IS needed"
        )
        assert len(intents) == expected, f"intents {len(intents)} != {expected}"
        assert len(done) == expected, f"done {len(done)} != {expected}"

        # -- no duplicate OUTCOMEs per dispatch_id (idempotency under load)
        outcome_ids = [r["dispatch_id"] for r in outcomes]
        assert len(outcome_ids) == len(set(outcome_ids)), "duplicate OUTCOME records — flock layer IS needed"


# -- sig: mgh-6201.cd.bd955f.f1aa.st310a


# -- sig: mgh-6201.cd.bd955f.0f9e.d369b4
