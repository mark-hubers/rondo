# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Mutation kill-tests for audit.py — the integrity core, proven to bite.

VER-001: Product acceptance / audit trail behavioral contract.

WHY: a mutation sweep (bin/mutate, 2026-06-12) measured audit.py at 47/133 — the
weakest module in the repo, far below verify/scope/pipeline/sanitize. The audit
trail is the honest record everything else trusts; its config defaults, retention
pruning, reconcile, and rotation logic were barely pinned. (Security perms are in
test_audit_perms_mutation.py.) These tests close the BEHAVIORAL clusters.

Every asserted value/shape was computed from the live code before being written
(probe runs, 2026-06-12) — no guessed numbers. Stateful module: each test uses an
isolated RONDO_TEST_DIR and auto_reconcile=False unless reconcile is under test.

MEASURED: audit.py 47/133 -> 103/133 (35% -> 77%) with this suite + the perms
suite. The ~30 residual are TRIAGED, not silent gaps — two legitimate buckets:

  DEGRADATION-RAIL return-value pins (need OS fault injection): the reconcile
  flock fallbacks (L784/791/837/842 `return self._reconcile_locked`), the
  EWOULDBLOCK peer-skip (L819), thread-local held flag (L852), and the lock-fail
  / OSError early-returns in rotate/reconcile (L574/608/867). The fallback
  BEHAVIOR (graceful single-writer, never crash) is covered by the degradation
  suite; what survives is the narrow "returns the count, not None" contract,
  which needs fcntl-unavailable / unwritable-fd injection. Left documented rather
  than forced with fragile fault-injection mocks.

  PROVABLE EQUIVALENTS (house rule: never tautology-tested): L505 indent=2
  (cosmetic); L564 mkdir mode/flags on an ALREADY-existing dir (mode ignored) +
  L585 exist_ok on a FRESH dir (both no-ops in the real call flow); L615/762/910
  getattr defaults the config attribute always supplies; L623 `<=`->`<` and L914
  `>=`->`>` at boundaries where the slice/branch is empty either way; L698/708
  compare flips that reach the same boolean via a different path; L722 the
  final_line_torn INIT value (overwritten before use); L361 the interval compare
  (needs now-last == INTERVAL exactly, unhittable on a monotonic clock); L187 the
  sanitize-failure fallback (sanitize_text would have to raise); L901 a log-only
  guard (the return value is pinned by test_reconcile_marks_stuck_intent).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from rondo.audit import (
    AuditConfig,
    AuditRecord,
    AuditTrail,
    _default_audit_dir,
    _forensic_snippet,
    _generate_dispatch_id,
    resolve_audit_dir,
)


@pytest.fixture
def _trail(tmp_path: Path, monkeypatch) -> AuditTrail:
    monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))
    return AuditTrail(config=AuditConfig(), auto_reconcile=False)


def _records(audit_dir: Path) -> list[dict]:
    """Parse JSONL records, tolerating torn/corrupt lines (as readers must)."""
    out: list[dict] = []
    text = (audit_dir / "rondo_audit.jsonl").read_text(encoding="utf-8")
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


# ── config + record defaults (kills L118/121/123/125/135, L230/231, L307) ──


def test_audit_config_defaults() -> None:
    """AuditConfig carries its documented operational defaults."""
    c = AuditConfig()
    assert c.enabled is True
    assert c.audit_retention_days == 0
    assert c.max_jsonl_bytes == 10 * 1024 * 1024  # -- 10485760
    assert c.archive_retention_months == 12
    assert c.stuck_after_sec == 900


def test_audit_record_numeric_defaults() -> None:
    """A fresh AuditRecord defaults tokens to 0 and status to INTENT."""
    r = AuditRecord()
    assert r.input_tokens == 0
    assert r.output_tokens == 0
    assert r.status == "INTENT"


def test_dispatch_id_format() -> None:
    """A dispatch id is 'dsp_' + 16 hex chars = 20 total (kills the L307 [:16])."""
    did = _generate_dispatch_id()
    assert did.startswith("dsp_")
    assert len(did) == 20
    assert len(did) - len("dsp_") == 16


# ── pure helpers (kills L182, L88/L110 resolvers) ──


def test_forensic_snippet_empty_returns_empty() -> None:
    """An empty forensic field returns '' (kills the L182 return-none)."""
    assert _forensic_snippet("") == ""


def test_default_audit_dir_without_test_dir(monkeypatch) -> None:
    """Without RONDO_TEST_DIR -> ~/.rondo/audit/{tenant}, a real string (kills L88/L110)."""
    monkeypatch.delenv("RONDO_TEST_DIR", raising=False)
    monkeypatch.delenv("RONDO_TENANT", raising=False)
    d = _default_audit_dir()
    assert isinstance(d, str)
    assert d.startswith("~/.rondo/audit/")
    assert "None" not in d  # -- a None tenant (L88 mutated) would render '.../None'


# ── record_outcome defaults + result storage (kills L432/437/438, L496) ──


def test_record_outcome_numeric_defaults(_trail: AuditTrail) -> None:
    """record_outcome with no exit_code/tokens persists 0s (kills L432/437/438 defaults)."""
    _trail.record_outcome(dispatch_id="d1", status="done")
    rec = next(r for r in _records(resolve_audit_dir()) if r["dispatch_id"] == "d1")
    assert rec["exit_code"] == 0
    assert rec["input_tokens"] == 0
    assert rec["output_tokens"] == 0


def test_result_file_written_only_with_storage_and_output(_trail: AuditTrail) -> None:
    """A result file is written iff result_storage AND raw_output (kills the L496 boolop)."""
    _trail.record_outcome(dispatch_id="has", status="done", raw_output="data")
    _trail.record_outcome(dispatch_id="empty", status="done", raw_output="")
    audit_dir = resolve_audit_dir()
    assert (audit_dir / "has.result.json").exists()  # -- both true -> written
    assert not (audit_dir / "empty.result.json").exists()  # -- empty raw -> not written


def test_get_failed_dispatches_empty_when_no_jsonl(tmp_path, monkeypatch) -> None:
    """No JSONL -> get_failed_dispatches returns [] (kills the L521 return-none)."""
    monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))
    trail = AuditTrail(config=AuditConfig(), auto_reconcile=False)
    assert trail.get_failed_dispatches() == []


# ── retention pruning (kills L615/616/623/624/626/627/631/636) ──


def test_prune_old_archives_keeps_retention(_trail: AuditTrail) -> None:
    """15 archives, retention 12 -> exactly 3 oldest deleted, 12 kept (kills the prune math)."""
    archive_dir = resolve_audit_dir() / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    for i in range(15):
        (archive_dir / f"2024-{i:02d}.jsonl").write_text("x", encoding="utf-8")
    deleted = _trail._prune_old_archives(archive_dir)
    assert deleted == 3  # -- len 15 - retention 12
    assert len(list(archive_dir.glob("*.jsonl"))) == 12
    # -- the OLDEST (sorted-first) were the ones removed
    assert not (archive_dir / "2024-00.jsonl").exists()
    assert (archive_dir / "2024-14.jsonl").exists()


def test_prune_retention_zero_keeps_everything(tmp_path, monkeypatch) -> None:
    """Retention <= 0 -> nothing pruned (kills the L616 `retention <= 0` compare)."""
    monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))
    trail = AuditTrail(config=AuditConfig(archive_retention_months=0), auto_reconcile=False)
    archive_dir = resolve_audit_dir() / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    for i in range(5):
        (archive_dir / f"2024-{i:02d}.jsonl").write_text("x", encoding="utf-8")
    assert trail._prune_old_archives(archive_dir) == 0
    assert len(list(archive_dir.glob("*.jsonl"))) == 5


def test_prune_under_retention_keeps_all(_trail: AuditTrail) -> None:
    """Files <= retention -> 0 deleted (kills the L623 `len(files) <= retention` boundary)."""
    archive_dir = resolve_audit_dir() / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    for i in range(12):  # -- exactly retention
        (archive_dir / f"2024-{i:02d}.jsonl").write_text("x", encoding="utf-8")
    assert _trail._prune_old_archives(archive_dir) == 0


# ── reset (kills L646/650) ──


def test_reset_removes_jsonl_and_result_files(_trail: AuditTrail) -> None:
    """Reset removes the JSONL + result files and counts them (kills the L646/650 increments)."""
    _trail.record_outcome(dispatch_id="r1", status="done", raw_output="hello")
    assert _trail.reset() == 2  # -- the JSONL + the one result file


# ── _intent_is_in_flight (kills L698/699/702/706/708) ──


def test_intent_in_flight_threshold_disabled(_trail: AuditTrail) -> None:
    """threshold_sec <= 0 -> not in-flight, always reconcilable (kills L698/699)."""
    now = datetime.now(UTC)
    fresh = {"dispatched_at": now.isoformat()}
    assert _trail._intent_is_in_flight(fresh, 0, now) is False


def test_intent_in_flight_fresh_vs_old(_trail: AuditTrail) -> None:
    """A fresh INTENT is in-flight; an old one is not (kills the L708 age compare)."""
    now = datetime.now(UTC)
    fresh = {"dispatched_at": now.isoformat()}
    old = {"dispatched_at": (now - timedelta(seconds=1000)).isoformat()}
    assert _trail._intent_is_in_flight(fresh, 500, now) is True
    assert _trail._intent_is_in_flight(old, 500, now) is False


def test_intent_in_flight_missing_and_malformed_timestamp(_trail: AuditTrail) -> None:
    """Missing or malformed dispatched_at -> not in-flight (kills L702/706)."""
    now = datetime.now(UTC)
    assert _trail._intent_is_in_flight({}, 500, now) is False
    assert _trail._intent_is_in_flight({"dispatched_at": "not-a-date"}, 500, now) is False


# ── reconcile end to end (kills L757/758 + the stuck-write path) ──


def test_reconcile_no_jsonl_returns_zero(tmp_path, monkeypatch) -> None:
    """No JSONL -> reconcile returns 0 (kills the L757/758 early return)."""
    monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))
    trail = AuditTrail(config=AuditConfig(), auto_reconcile=False)
    assert trail.reconcile_stuck_intents(stuck_after_sec=0) == 0


def test_reconcile_marks_stuck_intent(_trail: AuditTrail) -> None:
    """An INTENT with no OUTCOME -> one synthetic 'stuck' OUTCOME written + counted."""
    _trail.record_intent(task_name="x", round_name="r", model="m", prompt="p")
    n = _trail.reconcile_stuck_intents(stuck_after_sec=0)
    assert n == 1
    stuck = [r for r in _records(resolve_audit_dir()) if r.get("status") == "stuck"]
    assert len(stuck) == 1
    assert stuck[0]["error_code"] == "ERR_RECONCILED_STUCK"


# ── size-based auto-rotation (kills L910/911/914) ──


def test_maybe_rotate_triggers_on_size(tmp_path, monkeypatch) -> None:
    """A JSONL exceeding max_jsonl_bytes auto-rotates into an archive (kills L911/914)."""
    monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))
    trail = AuditTrail(config=AuditConfig(max_jsonl_bytes=50), auto_reconcile=False)
    for i in range(4):
        trail.record_outcome(dispatch_id=f"d{i}", status="done")
    archive_dir = resolve_audit_dir() / "archive"
    assert archive_dir.exists()
    assert len(list(archive_dir.glob("*.jsonl"))) >= 1


def test_no_rotation_when_max_bytes_zero(tmp_path, monkeypatch) -> None:
    """max_jsonl_bytes 0 -> rotation disabled, no archive (kills the L911 `not max_bytes`)."""
    monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))
    trail = AuditTrail(config=AuditConfig(max_jsonl_bytes=0), auto_reconcile=False)
    for i in range(4):
        trail.record_outcome(dispatch_id=f"d{i}", status="done")
    assert not (resolve_audit_dir() / "archive").exists()


# ── torn-line + empty-rotate + boundary literals (kills L722/729/875, L582, L698 int, L616 int) ──


def test_reconcile_skips_on_torn_final_line(_trail: AuditTrail) -> None:
    """A torn final JSONL line -> reconcile skips (returns 0), never double-writes (kills L722/729/875)."""
    _trail.record_intent(task_name="x", round_name="r", model="m", prompt="p")
    with (resolve_audit_dir() / "rondo_audit.jsonl").open("a", encoding="utf-8") as f:
        f.write("{ this line is torn\n")  # -- mid-append / corruption signal
    assert _trail.reconcile_stuck_intents(stuck_after_sec=0) == 0  # -- snapshot untrusted -> skip
    # -- and NO synthetic stuck OUTCOME was written
    assert not [r for r in _records(resolve_audit_dir()) if r.get("status") == "stuck"]


def test_rotate_empty_content_unlinks_and_returns_zero(tmp_path, monkeypatch) -> None:
    """An existing but blank JSONL -> rotate returns 0 and unlinks it (kills the L582 return 0)."""
    monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))
    trail = AuditTrail(config=AuditConfig(), auto_reconcile=False)
    (resolve_audit_dir() / "rondo_audit.jsonl").write_text("   \n", encoding="utf-8")
    assert trail.rotate() == 0
    assert not (resolve_audit_dir() / "rondo_audit.jsonl").exists()


def test_intent_in_flight_threshold_one_boundary(_trail: AuditTrail) -> None:
    """A fresh INTENT with threshold_sec=1 is in-flight (kills the L698 `<= 0` literal `0`)."""
    # -- with `<= 1` (mutant), threshold 1 would short-circuit to False; `<= 0` lets it through
    now = datetime.now(UTC)
    assert _trail._intent_is_in_flight({"dispatched_at": now.isoformat()}, 1, now) is True


def test_prune_retention_one_keeps_newest(tmp_path, monkeypatch) -> None:
    """Retention 1 with 3 files -> 2 oldest deleted (kills the L616 `<= 0` literal `0`)."""
    monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))
    trail = AuditTrail(config=AuditConfig(archive_retention_months=1), auto_reconcile=False)
    archive_dir = resolve_audit_dir() / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    for i in range(3):
        (archive_dir / f"2024-{i:02d}.jsonl").write_text("x", encoding="utf-8")
    assert trail._prune_old_archives(archive_dir) == 2


# ── auto-reconcile on init + the once-per-interval claim (kills L322/339, L361/362/364) ──


def test_auto_reconcile_runs_on_init_by_default(tmp_path, monkeypatch) -> None:
    """A default-constructed AuditTrail reconciles a pre-existing stuck INTENT (kills L322/339)."""
    monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))
    # -- seed a stuck INTENT with NO auto-reconcile (so the key stays unclaimed)
    seed = AuditTrail(config=AuditConfig(), auto_reconcile=False)
    seed.record_intent(task_name="x", round_name="r", model="m", prompt="p")
    # -- a DEFAULT construction (auto_reconcile=True) must reconcile it on init
    AuditTrail(config=AuditConfig(stuck_after_sec=0))
    stuck = [r for r in _records(resolve_audit_dir()) if r.get("status") == "stuck"]
    assert len(stuck) == 1


def test_claim_auto_reconcile_is_once_per_interval(_trail: AuditTrail) -> None:
    """First claim True, an immediate second claim False (kills L361 arith+compare, L362, L364)."""
    # -- the _trail fixture is auto_reconcile=False on a unique dir, so the key starts unclaimed
    assert _trail._claim_auto_reconcile() is True  # -- first claim wins
    assert _trail._claim_auto_reconcile() is False  # -- within the interval -> declined


def test_prune_on_non_directory_returns_zero(_trail: AuditTrail) -> None:
    """Prune against a non-directory -> glob OSError caught, returns 0 (kills the L621 return-none).

    A real filesystem condition (a file where a dir is expected), NOT a mock.
    """
    not_a_dir = resolve_audit_dir() / "archive_is_a_file"
    not_a_dir.write_text("x", encoding="utf-8")
    assert _trail._prune_old_archives(not_a_dir) == 0


# -- sig: mgh-6201.cd.bd955f.74df.c4d911
