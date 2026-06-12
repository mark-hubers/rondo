# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Inline loop control — the verified control loop (RONDO-414).

VER-001: Product acceptance / unit test coverage.

AUTHOR: gemini-2.5-pro via rondo_run (Cursor usage-limited; separation of
duties preserved). These strengthen the INLINE CONTROL LOOP — plan -> execute
-> rondo_verify -> branch on the verdict -> next — the unit the "loop
engineering" pattern (Claude Code's creator, The New Stack 2026-06-10) is
built on. They exercise the EXISTING rondo_verify + verify= machinery under
loop/branching usage.

Transcription notes (documented, not silent): (1) test 5's audit filter used
a non-existent "action" field — re-pointed to the real shape (status=="verified"
+ engine=="verify"); (2) added `-> None` return hints. Assertions untouched.
"""

from __future__ import annotations

import json
import sys
import uuid

from rondo.mcp_dispatch import rondo_run_file
from rondo.verify import rondo_verify


def _run(tmp_path, monkeypatch, verify=None) -> str:
    """One inline advisory dispatch (optionally with a verify block); return dispatch_id."""
    monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))
    kwargs = {
        "prompt": f"t-{uuid.uuid4().hex}",
        "model": "",
        "execution": "inline",
        "dry_run": False,
        "_session": object(),
    }
    if verify:
        kwargs["verify"] = json.dumps(verify)
    return json.loads(rondo_run_file(**kwargs))["dispatch_id"]


def test_loop_advances_only_on_verified(tmp_path, monkeypatch) -> None:
    """A 3-iteration loop advances only while each iteration verifies."""
    statuses = []
    for i in range(3):
        f = tmp_path / f"f{i}.txt"
        f.write_text("data")
        did = _run(tmp_path, monkeypatch, verify={"files": [str(f)]})
        res = rondo_verify(did)
        statuses.append(res["status"])
        if res["status"] != "verified":
            break
    assert statuses == ["verified", "verified", "verified"]


def test_loop_halts_on_failed_verification(tmp_path, monkeypatch) -> None:
    """Iteration 2 declares a file it never creates -> the loop STOPS before 3."""
    statuses = []
    for i in range(3):
        f = tmp_path / f"halt{i}.txt"
        if i != 1:
            f.write_text("data")
        did = _run(tmp_path, monkeypatch, verify={"files": [str(f)]})
        res = rondo_verify(did)
        statuses.append(res["status"])
        if res["status"] != "verified":
            break
    assert statuses == ["verified", "failed_verification"]
    assert not (tmp_path / "halt2.txt").exists()


def test_retry_branch_until_verified(tmp_path, monkeypatch) -> None:
    """A fix-retry loop: first verify fails, the fix creates the file, second passes."""
    statuses = []
    f = tmp_path / "retry.txt"
    did1 = _run(tmp_path, monkeypatch, verify={"files": [str(f)]})
    res1 = rondo_verify(did1)
    statuses.append(res1["status"])
    if res1["status"] == "failed_verification":
        f.write_text("fixed")
        did2 = _run(tmp_path, monkeypatch, verify={"files": [str(f)]})
        statuses.append(rondo_verify(did2)["status"])
    assert statuses == ["failed_verification", "verified"]


def test_cmd_gate_drives_branch(tmp_path, monkeypatch) -> None:
    """A verify cmd drives the branch: expect 0 but the command exits 1 -> failed."""
    cmd = [sys.executable, "-c", "import sys; sys.exit(1)"]
    did = _run(tmp_path, monkeypatch, verify={"cmd": cmd, "expect_exit": 0})
    res = rondo_verify(did)
    assert res["status"] == "failed_verification"


def test_each_iteration_independently_audited(tmp_path, monkeypatch) -> None:
    """A 3-iteration verified loop writes 3 distinct verified records to the JSONL."""
    dids = []
    for i in range(3):
        f = tmp_path / f"audit{i}.txt"
        f.write_text("data")
        did = _run(tmp_path, monkeypatch, verify={"files": [str(f)]})
        rondo_verify(did)
        dids.append(did)
    lines = (tmp_path / "audit" / "rondo_audit.jsonl").read_text().splitlines()
    records = [json.loads(line) for line in lines]
    # -- re-point: the verify outcome record is status=="verified" + engine=="verify"
    verified = sum(
        1
        for r in records
        if r.get("status") == "verified" and r.get("engine") == "verify" and r.get("dispatch_id") in dids
    )
    assert verified == 3


def test_unverifiable_iteration_does_not_falsely_advance(tmp_path, monkeypatch) -> None:
    """An iteration dispatched WITHOUT a verify block is 'unverifiable', never a false 'verified'."""
    did = _run(tmp_path, monkeypatch, verify=None)
    res = rondo_verify(did)
    assert res["status"] == "unverifiable"


def test_evidence_chain_across_loop(tmp_path, monkeypatch) -> None:
    """Both iterations leave an evidence file carrying sha256 — a verifiable chain."""
    dids = []
    for i in range(2):
        f = tmp_path / f"ev{i}.txt"
        f.write_text("data")
        did = _run(tmp_path, monkeypatch, verify={"files": [str(f)]})
        rondo_verify(did)
        dids.append(did)
    for did in dids:
        ev_file = tmp_path / "audit" / f"{did}.verify.json"
        assert ev_file.exists()
        assert "sha256" in ev_file.read_text()


# -- sig: mgh-6201.cd.bd955f.70c3.15c4b3
