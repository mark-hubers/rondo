# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""REQ-115 req 002 — the TAMPER test the spec claimed but lacked (RONDO-421).

VER-001: Product acceptance / verify-block tamper resistance.

HONESTY NOTE: a self-audit (2026-06-13) found REQ-115 req 002 marked MUST with
verification "Tamper test", but no dedicated test existed — the persistence was
only INDIRECTLY exercised by the rondo_verify tests. That was an overclaim of
conformance. This file closes it with the real tamper properties:

  1. The verify block is PERSISTED at issuance as {dispatch_id}.verifyspec.json
     (locally authored, never model output) and rondo_verify loads EXACTLY that.
  2. A path-bearing dispatch_id cannot make rondo_verify load an arbitrary
     .verifyspec.json (the _is_safe_dispatch_id traversal guard, F1).

No mocks — drives the real inline dispatch + rondo_verify against RONDO_TEST_DIR.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from rondo.mcp_dispatch import rondo_run_file
from rondo.verify import _is_safe_dispatch_id, _load_persisted_verify, rondo_verify


def _dispatch(tmp_path: Path, monkeypatch, verify: dict) -> str:
    """One inline advisory dispatch with a verify block; returns its dispatch_id."""
    monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))
    return json.loads(
        rondo_run_file(
            prompt=f"t-{uuid.uuid4().hex}",
            model="",
            execution="inline",
            dry_run=False,
            _session=object(),
            verify=json.dumps(verify),
        )
    )["dispatch_id"]


def test_verify_block_is_persisted_and_is_the_only_source(tmp_path, monkeypatch) -> None:
    """Req 002: the block is persisted at issuance and rondo_verify loads EXACTLY it."""
    good = tmp_path / "out.txt"
    good.write_text("real", encoding="utf-8")
    did = _dispatch(tmp_path, monkeypatch, {"files": [str(good)]})

    # -- the spec was persisted as a locally-authored file (not buried in model output)
    spec_path = tmp_path / "audit" / f"{did}.verifyspec.json"
    assert spec_path.is_file(), "verify block was not persisted at issuance"
    assert json.loads(spec_path.read_text())["files"] == [str(good)]

    # -- rondo_verify loads THAT persisted block and checks it in rondo's own process
    assert _load_persisted_verify(did) == {
        "files": [str(good)],
        "cmd": None,
        "expect_exit": 0,
        "within_sec": 120,
        "contains": [],
        "min_bytes": 0,
    }
    assert rondo_verify(did)["status"] == "verified"


def test_rondo_verify_loads_persisted_spec_even_if_world_changes(tmp_path, monkeypatch) -> None:
    """The persisted spec is authoritative: delete the declared file -> failed_verification.

    Proves the verdict comes from rondo re-checking the PERSISTED postconditions,
    not from any claim the dispatch returned.
    """
    target = tmp_path / "deleted.txt"
    target.write_text("here", encoding="utf-8")
    did = _dispatch(tmp_path, monkeypatch, {"files": [str(target)]})
    target.unlink()  # -- the world no longer matches the persisted spec
    assert rondo_verify(did)["status"] == "failed_verification"


def test_path_traversal_dispatch_id_is_rejected(tmp_path, monkeypatch) -> None:
    """F1: a path-bearing dispatch_id cannot load an arbitrary .verifyspec.json."""
    monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))
    # -- plant a malicious spec OUTSIDE the safe-id namespace
    evil_dir = tmp_path / "audit"
    evil_dir.mkdir(parents=True, exist_ok=True)
    (evil_dir / "evil.verifyspec.json").write_text(json.dumps({"cmd": ["echo", "pwned"], "expect_exit": 0}))

    for bad in ["../../etc/passwd", "a/b/c", "a.b", "dsp_x/../evil", "", "x" * 65]:
        assert _is_safe_dispatch_id(bad) is False, f"guard wrongly accepted {bad!r}"
        assert rondo_verify(bad)["status"] == "unverifiable", f"traversal id {bad!r} was not blocked"


def test_safe_dispatch_id_shape_is_accepted() -> None:
    """The real 'dsp_'+hex shape (and plain identifiers) pass the guard."""
    assert _is_safe_dispatch_id("dsp_0123456789abcdef") is True
    assert _is_safe_dispatch_id("dsp_abc-DEF_123") is True


# -- sig: mgh-6201.cd.bd955f.bced.ec5773
