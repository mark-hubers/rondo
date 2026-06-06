# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Rondo doctor — install diagnosis + redacted support bundle.

RONDO-320 (REQ-103 reqs 030-036; SOP-105 P2-0). Preflight answers "can I
dispatch RIGHT NOW"; doctor answers "is this INSTALL healthy, and if not,
what exactly do I fix" — the first command support asks a stranger to run.

Contract:
    - zero dispatches, zero cost (req 030)
    - every row: PASS/WARN/FAIL + actionable fix hint, never a traceback (031)
    - exit 0 = no FAIL, 1 = any FAIL; WARN never fails (032)
    - --bundle: ONE redacted file; secrets cannot survive (034-035)
    - offline-tolerant: missing network degrades to WARN (036)

Import direction:
    doctor.py → config, model_registry, retry_queue, sanitize (lazy)
"""

from __future__ import annotations

import os
import re
import shutil
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

# -- key-shaped material that must never survive into output/bundle (req 035)
_KEY_PATTERNS = (
    re.compile(r"\bsk-(?:ant-)?[A-Za-z0-9_-]{8,}"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{16,}"),
    re.compile(r"\bAIza[A-Za-z0-9_-]{20,}"),
    re.compile(r"\bxai-[A-Za-z0-9_-]{8,}"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._-]{12,}"),
)


@dataclass
class DoctorCheck:
    """One diagnosis row — req 031."""

    name: str
    result: str  # -- PASS | WARN | FAIL
    detail: str = ""
    fix: str = ""

    def to_dict(self) -> dict[str, Any]:
        """JSON-safe row for --json (req 033)."""
        return asdict(self)


def _redact(text: str) -> str:
    """Strip key-shaped material — req 035. Belt for every detail/bundle."""
    for pattern in _KEY_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text


def _rondo_home() -> Path:
    """~/.rondo, honoring RONDO_TEST_DIR (hermeticity, #292)."""
    test_dir = os.environ.get("RONDO_TEST_DIR")
    return Path(test_dir) if test_dir else Path("~/.rondo").expanduser()


def _check_config() -> DoctorCheck:
    """Config file parses and loads — req 030."""
    from rondo.config import get_rondo_config  # pylint: disable=import-outside-toplevel

    cfg = get_rondo_config()
    providers = cfg.get("providers", {})
    enabled = [n for n, c in providers.items() if c.get("enabled")]
    if not providers:
        return DoctorCheck(
            "config",
            "WARN",
            "no config file found — defaults active, no cloud providers",
            "run: rondo init --config   (creates ~/.rondo/config.toml from template)",
        )
    return DoctorCheck("config", "PASS", f"loaded; {len(enabled)} provider(s) enabled")


def _check_provider_keys() -> DoctorCheck:
    """Per enabled provider: key loadable? Shown as present + last-4 ONLY — req 035."""
    from rondo.adapters.auth import load_api_key  # pylint: disable=import-outside-toplevel
    from rondo.config import get_rondo_config  # pylint: disable=import-outside-toplevel

    providers = get_rondo_config().get("providers", {})
    enabled = [n for n, c in providers.items() if c.get("enabled")]
    if not enabled:
        return DoctorCheck(
            "provider keys",
            "WARN",
            "no providers enabled",
            "enable at least one [providers.*] block in ~/.rondo/config.toml",
        )
    missing: list[str] = []
    present: list[str] = []
    for name in enabled:
        try:
            key = load_api_key(name)
        except (OSError, ValueError, KeyError):
            key = ""
        if key:
            present.append(f"{name}(…{key[-4:]})")
        else:
            missing.append(name)
    if missing:
        return DoctorCheck(
            "provider keys",
            "FAIL",
            f"present: {', '.join(present) or 'none'}; MISSING: {', '.join(missing)}",
            f"add key(s) for {', '.join(missing)} (Keychain or env var) — see docs/GETTING-STARTED.md",
        )
    return DoctorCheck("provider keys", "PASS", f"{len(present)} key(s) loadable: {', '.join(present)}")


def _check_registry_cache() -> DoctorCheck:
    """Registry cache exists + drift summary (free, from cache) — req 030."""
    from rondo.config import get_rondo_config  # pylint: disable=import-outside-toplevel
    from rondo.model_registry import drift_report, load_cache  # pylint: disable=import-outside-toplevel

    cache = load_cache()
    if cache is None:
        return DoctorCheck(
            "model registry",
            "WARN",
            "no registry cache — drift detection inactive",
            "run: rondo providers --refresh   (free catalog fetch)",
        )
    entries = drift_report(cache, get_rondo_config().get("providers", {}))
    stale = [e for e in entries if e.get("state") == "STALE"]
    if stale:
        names = ", ".join(f"{e['provider']}:{e['model']}" for e in stale[:3])
        return DoctorCheck(
            "model registry",
            "FAIL",
            f"{len(stale)} configured model(s) no longer served: {names}",
            "fix ~/.rondo/config.toml (rondo never auto-edits); see: rondo providers --drift",
        )
    return DoctorCheck("model registry", "PASS", f"cache present ({cache.get('fetched_at', '?')[:10]}), no stale tiers")


def _check_dirs() -> DoctorCheck:
    """audit/spool/retry dirs writable — req 030."""
    home = _rondo_home()
    bad: list[str] = []
    for sub in ("audit", "spool", "retry"):
        d = home / sub
        try:
            d.mkdir(parents=True, exist_ok=True, mode=0o700)
            probe = d / ".doctor-probe"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
        except OSError:
            bad.append(str(d))
    if bad:
        return DoctorCheck("data dirs", "FAIL", f"not writable: {', '.join(bad)}", "check permissions/disk on ~/.rondo")
    return DoctorCheck("data dirs", "PASS", f"audit/spool/retry writable under {home}")


def _check_claude_binary() -> DoctorCheck:
    """Claude CLI present (needed for subprocess dispatch only) — req 030."""
    path = shutil.which("claude")
    if not path:
        return DoctorCheck(
            "claude binary",
            "WARN",
            "claude CLI not on PATH — subprocess dispatch unavailable (API adapters unaffected)",
            "install Claude Code, or use provider:model API dispatch only",
        )
    return DoctorCheck("claude binary", "PASS", path)


def _check_versions() -> DoctorCheck:
    """Rondo + Python versions — req 030 (every support thread starts here)."""
    from rondo._version import get_version  # pylint: disable=import-outside-toplevel

    py = ".".join(str(v) for v in sys.version_info[:3])
    return DoctorCheck("versions", "PASS", f"rondo {get_version()} on python {py}")


DEFAULT_CHECKS: tuple[Callable[[], DoctorCheck], ...] = (
    _check_versions,
    _check_config,
    _check_provider_keys,
    _check_registry_cache,
    _check_dirs,
    _check_claude_binary,
)


def run_doctor(checks: list[Callable[[], DoctorCheck]] | None = None) -> list[DoctorCheck]:
    """Run every check; a crashing check is a FAIL row, never a crash — req 031."""
    rows: list[DoctorCheck] = []
    for check in checks if checks is not None else list(DEFAULT_CHECKS):
        try:
            row = check()
        except Exception as exc:  # noqa: BLE001 -- diagnosis tool: any crash becomes a row
            row = DoctorCheck(
                name=getattr(check, "__name__", "check").removeprefix("_check_"),
                result="FAIL",
                detail=f"{type(exc).__name__}: {exc}",
                fix="this check itself crashed — include this row in a bug report (rondo doctor --bundle)",
            )
        row.detail = _redact(row.detail)
        rows.append(row)
    return rows


def doctor_exit_code(rows: list[DoctorCheck]) -> int:
    """Req 032: 0 = no FAIL, 1 = any FAIL. WARN never fails."""
    return 1 if any(r.result == "FAIL" for r in rows) else 0


def format_doctor_table(rows: list[DoctorCheck]) -> str:
    """Human table with fix hints — req 031."""
    lines = [f"  {'CHECK':<16} {'RESULT':<7} DETAIL"]
    for r in rows:
        lines.append(f"  {r.name:<16} {r.result:<7} {r.detail[:90]}")
        if r.fix and r.result != "PASS":
            lines.append(f"  {'':<16} {'':<7} → FIX: {r.fix[:100]}")
    fails = sum(1 for r in rows if r.result == "FAIL")
    warns = sum(1 for r in rows if r.result == "WARN")
    lines.append(f"  {len(rows)} checks: {fails} FAIL, {warns} WARN")
    return "\n".join(lines)


def _recent_failures(limit: int = 5) -> list[str]:
    """Last N failure forensics: codes + sanitized messages, NEVER prompts — req 034."""
    import json  # pylint: disable=import-outside-toplevel

    log = _rondo_home() / "audit" / "rondo_audit.jsonl"
    if not log.exists():
        return []
    out: list[str] = []
    for line in reversed(log.read_text(encoding="utf-8").splitlines()):
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if rec.get("status") in ("done", "INTENT", "partial"):
            continue
        out.append(
            f"{rec.get('completed_at', '?')[:19]} {rec.get('model', '?')} "
            f"{rec.get('error_code') or rec.get('status')}: {(rec.get('error_message') or '')[:120]}"
        )
        if len(out) >= limit:
            break
    return out


def build_support_bundle(rows: list[DoctorCheck]) -> str:
    """ONE redacted text blob for issue reports — reqs 034-035.

    Aborts (raises ValueError) if key-shaped material survives redaction —
    a leaky bundle must never reach disk.
    """
    parts = ["# Rondo support bundle (redacted)", "", "## Doctor", format_doctor_table(rows), ""]
    failures = _recent_failures()
    if failures:
        parts += ["## Last failures (codes + sanitized messages only)", *[f"- {f}" for f in failures], ""]
    bundle = _redact("\n".join(parts))
    for pattern in _KEY_PATTERNS:
        if pattern.search(bundle):
            raise ValueError("key-shaped material survived redaction — bundle NOT written (req 035)")
    return bundle


# -- sig: mgh-6201.cd.bd955f.1deb.e9cf65
