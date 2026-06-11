# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Verified execution — Rondo-REQ-115: rondo checks the work itself.

The trust inversion: a plan/step DECLARES what the world must look like
afterwards (files that must exist, an argv command that must exit clean) and
rondo verifies those claims in ITS OWN process. The model's success report is
never the load-bearing wall for anything observable.

Shared by:
- the pipeline engine (per-step verification, REQ-115 reqs 020-022)
- rondo_verify(dispatch_id) — the loop-closer for inline advisory plans
  (reqs 010-013): loads the verify block PERSISTED at plan issuance, checks
  it, records a verified/failed_verification audit record + evidence file.

Import direction: leaf-ish — stdlib + audit (records/dir) + sanitize
(evidence scrubbing). pipeline.py imports FROM here; never the reverse.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import subprocess  # nosec B404 -- verify cmds are locally-authored argv lists, shell=False
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

VERIFY_FIELDS = {"files", "cmd", "expect_exit", "within_sec"}
_STDOUT_TAIL_CAP = 2000  # -- req 010: evidence stdout capped + sanitized


class VerifyBlockError(ValueError):
    """A verify block is malformed — raised at validation time."""


def validate_verify_block(verify: Any, owner: str) -> dict[str, Any] | None:
    """REQ-115 reqs 001/003: shape-check a verify block. None passes through.

    cmd must be an argv LIST — a shell string is rejected (subprocess
    hygiene; the model never authors this block, but the LOCAL author gets
    loud errors too).
    """
    if verify is None:
        return None
    if not isinstance(verify, dict) or not set(verify) <= VERIFY_FIELDS or not verify:
        raise VerifyBlockError(f"{owner}: verify must use only {sorted(VERIFY_FIELDS)}")
    files = verify.get("files", [])
    if not isinstance(files, list) or not all(isinstance(f, str) for f in files):
        raise VerifyBlockError(f"{owner}: verify.files must be a list of paths")
    cmd = verify.get("cmd")
    if cmd is not None and (not isinstance(cmd, list) or not all(isinstance(c, str) for c in cmd)):
        raise VerifyBlockError(f"{owner}: verify.cmd must be an argv LIST (never a shell string)")
    expect_exit = verify.get("expect_exit", 0)
    if not isinstance(expect_exit, int):
        raise VerifyBlockError(f"{owner}: verify.expect_exit must be an int")
    within = verify.get("within_sec", 120)
    if not isinstance(within, int) or within <= 0:
        raise VerifyBlockError(f"{owner}: verify.within_sec must be a positive int")
    return {"files": files, "cmd": cmd, "expect_exit": expect_exit, "within_sec": within}


def _check_files(verify: dict[str, Any], result: dict[str, Any]) -> None:
    """File existence + sha256 evidence (full digest — req 013 tamper detection)."""
    for path_str in verify.get("files", []):
        path = Path(path_str)
        if not path.is_file():
            result["ok"] = False
            result["error"] = f"ERR_VERIFICATION: declared file missing: {path_str}"
            result["checked_files"].append({"path": path_str, "exists": False})
            continue
        data = path.read_bytes()
        result["checked_files"].append(
            {"path": path_str, "exists": True, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        )


def _check_cmd(verify: dict[str, Any], result: dict[str, Any], cwd: str) -> None:
    """Run the declared argv command — rondo's own observation of the world."""
    cmd = verify.get("cmd")
    if not cmd:
        return
    try:
        proc = subprocess.run(  # nosec B603 -- argv list from the LOCAL author, never the model
            cmd,
            capture_output=True,
            text=True,
            check=False,
            timeout=verify.get("within_sec", 120),
            cwd=cwd or None,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        result["ok"] = False
        result["error"] = f"ERR_VERIFICATION: verify cmd failed to run: {exc}"
        return
    result["exit_code"] = proc.returncode
    # -- req 010: stdout tail capped + SANITIZED before it can be persisted
    from rondo.sanitize import sanitize_text  # noqa: PLC0415  # pylint: disable=import-outside-toplevel

    result["stdout_tail"] = sanitize_text(proc.stdout[-_STDOUT_TAIL_CAP:]).sanitized_text
    if proc.returncode != verify.get("expect_exit", 0):
        result["ok"] = False
        result["error"] = (
            f"ERR_VERIFICATION: verify cmd exited {proc.returncode}, expected {verify.get('expect_exit', 0)}"
        )


def run_verification(verify: dict[str, Any], cwd: str = "") -> dict[str, Any]:
    """REQ-115 r020/r010: check declared files + cmd. Returns the evidence dict.

    {"ok", "exit_code", "checked_files", "stdout_tail"?, "error"} — the
    model's claims play no part in any of it.
    """
    result: dict[str, Any] = {"ok": True, "exit_code": None, "checked_files": [], "error": ""}
    _check_files(verify, result)
    if result["ok"]:
        _check_cmd(verify, result, cwd)
    return result


def extract_json_object(raw: str) -> dict[str, Any] | None:
    """Best-effort JSON object extraction (direct → fenced → raw_decode scan).

    Moved here from pipeline.py (RONDO-410) — shared by contract checks,
    smart-return unwrapping, and persisted-plan loading.
    """
    text = raw.strip()
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except (json.JSONDecodeError, ValueError):
        pass
    fenced = re.findall(r"```(?:json)?\s*\n(.*?)\n\s*```", raw, re.DOTALL)
    for block in reversed(fenced):
        try:
            parsed = json.loads(block.strip())
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(parsed, dict):
            return parsed
    decoder = json.JSONDecoder()
    last: dict[str, Any] | None = None
    idx = 0
    while True:
        start = raw.find("{", idx)
        if start == -1:
            break
        try:
            parsed, end = decoder.raw_decode(raw, start)
        except ValueError:
            idx = start + 1
            continue
        if isinstance(parsed, dict):
            last = parsed
        idx = max(end, start + 1)
    return last


_SAFE_DISPATCH_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _is_safe_dispatch_id(dispatch_id: str) -> bool:
    """RONDO-411 (hostile review F1, HIGH): reject path-bearing dispatch_ids.

    rondo_verify is a PUBLIC tool/API — an unvalidated dispatch_id let
    '../../x' resolve to an arbitrary .verifyspec.json (then its cmd runs).
    Real dispatch_ids are 'dsp_'+hex; this allows that shape and nothing with
    separators, dots, or NULs.
    """
    return bool(_SAFE_DISPATCH_ID.fullmatch(dispatch_id))


def _load_persisted_verify(dispatch_id: str) -> dict[str, Any] | None:
    """Req 002: the verify block PERSISTED at plan issuance — tamper-proof source.

    Stored as its own UNSCRUBBED spec file: the block is locally authored
    (never model output), and the sanitizer's [PATH] redaction inside the
    scrubbed plan copy corrupted argv paths (found live by the judge suite).
    """
    if not _is_safe_dispatch_id(dispatch_id):
        return None
    from rondo.audit import resolve_audit_dir  # noqa: PLC0415  # pylint: disable=import-outside-toplevel

    spec_path = resolve_audit_dir() / f"{dispatch_id}.verifyspec.json"
    if not spec_path.is_file():
        return None
    try:
        raw = json.loads(spec_path.read_text(encoding="utf-8"))
        return validate_verify_block(raw, f"dispatch {dispatch_id}")
    except (json.JSONDecodeError, OSError, VerifyBlockError):
        return None  # -- missing/malformed → honestly unverifiable


def rondo_verify(dispatch_id: str) -> dict[str, Any]:
    """REQ-115 reqs 010-013: verify a dispatched plan's declared postconditions.

    Loads the verify block persisted at plan issuance (the model never had a
    write path to it), checks files + cmd in rondo's own process, appends a
    `verified` / `failed_verification` audit record, and writes an evidence
    file with verified_at + sha256 so later tampering is detectable.
    No block declared → status "unverifiable", and NOTHING false is recorded.
    """
    verify = _load_persisted_verify(dispatch_id)
    if verify is None:
        return {"status": "unverifiable", "evidence": {"reason": "no verify block persisted for this dispatch"}}

    evidence = run_verification(verify)
    status = "verified" if evidence["ok"] else "failed_verification"
    verified_at = datetime.now(UTC).isoformat()

    # -- req 013: evidence file (atomic, born 0o600 via audit.atomic_write)
    from rondo.audit import (  # noqa: PLC0415  # pylint: disable=import-outside-toplevel
        AuditConfig,
        AuditTrail,
        atomic_write,
        resolve_audit_dir,
    )

    evidence_record = {"dispatch_id": dispatch_id, "status": status, "verified_at": verified_at, "evidence": evidence}
    try:
        atomic_write(resolve_audit_dir() / f"{dispatch_id}.verify.json", json.dumps(evidence_record, indent=2))
    except OSError as exc:
        logger.warning("-WARNING- verify evidence file write failed (%s) — audit record still appended", exc)

    # -- req 011: audit record paired to the dispatch_id. raw_output stays
    # -- EMPTY on purpose: a non-empty value would overwrite the persisted
    # -- plan result file and destroy the req-002 tamper-proof source.
    try:
        trail = AuditTrail(config=AuditConfig(), auto_reconcile=False)
        trail.record_outcome(
            dispatch_id=dispatch_id,
            task_name="verify",
            round_name="verify",
            status=status,
            exit_code=0 if evidence["ok"] else 1,
            error_message=evidence["error"] or f"verified: {len(evidence['checked_files'])} file check(s) passed",
            engine="verify",
        )
    except Exception as exc:  # noqa: BLE001  -- STD-113 §20: audit failure never blocks the answer
        logger.warning("-WARNING- verify audit append failed (%s) — evidence file is the record", exc)

    return {"status": status, "evidence": evidence, "verified_at": verified_at}


# -- sig: mgh-6201.cd.bd955f.8161.ccd0fd
