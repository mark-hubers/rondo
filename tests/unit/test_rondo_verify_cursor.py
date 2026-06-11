# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Regression judges for Rondo-REQ-115 reqs 010-013: the rondo_verify loop-closer.

VER-001: Product acceptance / unit test coverage.

AUTHOR: gemini-2.5-pro via rondo_run, two parts (Cursor usage-limited;
separation of duties preserved — gemini authored, Claude implements).
rondo.verify and the rondo_run_file verify= argument DO NOT EXIST at
authoring time: import/TypeError REDs are the expected initial state.

THE CONTRACT: rondo_verify(dispatch_id) loads the verify block PERSISTED at
plan issuance, checks the world ITSELF (files + cmd exit), records a
verified/failed_verification audit record paired to the dispatch_id, writes
an evidence file with verified_at + sha256 — and answers "unverifiable"
honestly when no block was declared (recording nothing false).
"""

from __future__ import annotations

import json
import sys
import uuid

from rondo.mcp_dispatch import rondo_run_file
from rondo.verify import rondo_verify


def _run(tmp_path, monkeypatch, verify=None) -> str:
    """Issue an advisory dispatch (optionally with a verify block); return dispatch_id."""
    monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))
    kwargs = {
        "prompt": f"t-{uuid.uuid4().hex}",
        "model": "",
        "execution": "inline",
        "dry_run": False,
        "_session": object(),
    }
    if verify is not None:
        kwargs["verify"] = json.dumps(verify)
    return json.loads(rondo_run_file(**kwargs))["dispatch_id"]


def test_r010_file_check_verified(tmp_path, monkeypatch) -> None:
    """r010: declared file exists -> status verified."""
    target = tmp_path / "x.txt"
    target.write_text("BEFORE")
    did = _run(tmp_path, monkeypatch, {"files": [str(target)]})
    assert rondo_verify(did)["status"] == "verified"


def test_r010_missing_file_fails(tmp_path, monkeypatch) -> None:
    """r010: declared file missing -> status failed_verification."""
    target = tmp_path / "nope.txt"
    did = _run(tmp_path, monkeypatch, {"files": [str(target)]})
    assert rondo_verify(did)["status"] == "failed_verification"


def test_r010_cmd_exit_checked(tmp_path, monkeypatch) -> None:
    """r010: verify cmd exit code checked against expect_exit, both directions."""
    cmd = [sys.executable, "-c", "import sys; sys.exit(5)"]
    did1 = _run(tmp_path, monkeypatch, {"cmd": cmd, "expect_exit": 5})
    assert rondo_verify(did1)["status"] == "verified"
    did2 = _run(tmp_path, monkeypatch, {"cmd": cmd, "expect_exit": 0})
    assert rondo_verify(did2)["status"] == "failed_verification"


def test_r011_audit_records_status(tmp_path, monkeypatch) -> None:
    """r011: verified and failed_verification records land in the audit JSONL."""
    target = tmp_path / "x.txt"
    target.write_text("ok")
    did1 = _run(tmp_path, monkeypatch, {"files": [str(target)]})
    rondo_verify(did1)
    did2 = _run(tmp_path, monkeypatch, {"files": [str(tmp_path / "nope.txt")]})
    rondo_verify(did2)
    records = [json.loads(line) for line in (tmp_path / "audit" / "rondo_audit.jsonl").read_text().splitlines()]
    assert any(r.get("dispatch_id") == did1 and r.get("status") == "verified" for r in records)
    assert any(r.get("dispatch_id") == did2 and r.get("status") == "failed_verification" for r in records)


def test_r012_unverifiable_honest(tmp_path, monkeypatch) -> None:
    """r012: no verify block -> unverifiable, and NO false verification records."""
    did = _run(tmp_path, monkeypatch)
    assert rondo_verify(did)["status"] == "unverifiable"
    audit_file = tmp_path / "audit" / "rondo_audit.jsonl"
    if audit_file.exists():
        lines = [json.loads(line) for line in audit_file.read_text().splitlines()]
        bad = [
            r for r in lines if r.get("dispatch_id") == did and r.get("status") in ("verified", "failed_verification")
        ]
        assert not bad


def test_r012_reverify_appends(tmp_path, monkeypatch) -> None:
    """r012: re-verifying appends a second record (state may change; both are evidence)."""
    target = tmp_path / "target.txt"
    target.write_text("data")
    did = _run(tmp_path, monkeypatch, verify={"files": [str(target)]})
    rondo_verify(did)
    rondo_verify(did)
    lines = [json.loads(line) for line in (tmp_path / "audit" / "rondo_audit.jsonl").read_text().splitlines()]
    verified = [r for r in lines if r.get("dispatch_id") == did and r.get("status") == "verified"]
    assert len(verified) == 2


def test_r013_evidence_file_hashes(tmp_path, monkeypatch) -> None:
    """r013: evidence file carries verified_at + sha256 so later tampering is detectable."""
    target = tmp_path / "target.txt"
    target.write_text("data")
    did = _run(tmp_path, monkeypatch, verify={"files": [str(target)]})
    rondo_verify(did)
    evidence_file = tmp_path / "audit" / f"{did}.verify.json"
    assert evidence_file.exists()
    text = evidence_file.read_text()
    assert "verified_at" in text
    assert "sha256" in text


# -- sig: mgh-6201.cd.bd955f.0cb4.426fb5
