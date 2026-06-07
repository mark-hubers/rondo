# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Tests for rondo doctor — RONDO-320 (REQ-103 reqs 030-036).

Preflight answers "can I dispatch right now". Doctor answers "is this
INSTALL healthy, and what exactly do I fix" — the first command support
asks a stranger to run. Zero dispatches, zero cost, never a traceback.

VER-001 verification matrix: install diagnosis, exit contract, redacted bundle.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from rondo.doctor import (
    DoctorCheck,
    build_support_bundle,
    doctor_exit_code,
    format_doctor_table,
    run_doctor,
)


def _row(name: str = "demo", result: str = "PASS", detail: str = "", fix: str = "") -> DoctorCheck:
    return DoctorCheck(name=name, result=result, detail=detail, fix=fix)


class TestRunDoctor:
    """req 030: composed checks; a crashing check is a FAIL row, not a crash."""

    def test_injected_checks_compose(self) -> None:
        checks = [lambda: _row("a"), lambda: _row("b", "WARN", "meh", "tighten it")]
        rows = run_doctor(checks=checks)
        assert [r.name for r in rows] == ["a", "b"]

    def test_crashing_check_becomes_fail_row(self) -> None:
        def boom() -> DoctorCheck:
            raise OSError("disk fell off")

        rows = run_doctor(checks=[boom])
        assert rows[0].result == "FAIL"
        assert "disk fell off" in rows[0].detail
        assert rows[0].fix  # -- req 031: even a crash carries a fix hint

    def test_real_default_checks_contract(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """UNMOCKED: the real default checks run end-to-end in a sandbox HOME.

        Offline-tolerant (req 036) — must complete and return well-formed
        rows even with no providers, no cache, no network.
        """
        monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))
        monkeypatch.setenv("HOME", str(tmp_path))
        rows = run_doctor()
        assert len(rows) >= 5
        for r in rows:
            assert r.result in ("PASS", "WARN", "FAIL"), r
            assert r.name
            if r.result != "PASS":
                assert r.fix, f"{r.name}: non-PASS row missing fix hint (req 031)"


class TestExitCode:
    """req 032: 0 = no FAIL, 1 = any FAIL; WARN never fails."""

    def test_all_pass(self) -> None:
        assert doctor_exit_code([_row(), _row("b")]) == 0

    def test_warn_does_not_fail(self) -> None:
        assert doctor_exit_code([_row(), _row("b", "WARN")]) == 0

    def test_any_fail_fails(self) -> None:
        assert doctor_exit_code([_row(), _row("b", "FAIL", fix="do x")]) == 1


class TestTable:
    """req 031: PASS/WARN/FAIL rows with actionable fix hints."""

    def test_table_shows_fix_hint(self) -> None:
        out = format_doctor_table([_row("keys", "FAIL", "no key for grok", "export XAI_API_KEY=...")])
        assert "FAIL" in out
        assert "export XAI_API_KEY" in out

    def test_table_summary_line(self) -> None:
        out = format_doctor_table([_row(), _row("b", "FAIL", fix="x")])
        assert "1 FAIL" in out


class TestBundle:
    """reqs 034-035: ONE redacted file; secrets never survive."""

    def test_bundle_contains_rows_and_versions(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))
        text = build_support_bundle([_row("config", "PASS", "ok")])
        assert "rondo support bundle" in text.lower()
        assert "config" in text

    def test_bundle_redacts_key_material(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))
        leaky = _row("keys", "WARN", "found sk-ant-api03-AAAABBBBccccDDDD1234 in env", "rotate it")
        text = build_support_bundle([leaky])
        assert "sk-ant-api03-AAAABBBBccccDDDD1234" not in text

    def test_bundle_never_includes_prompt_text(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Req 034: forensics carry error codes/messages, never prompts/outputs."""
        monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))
        text = build_support_bundle([_row()])
        assert "raw_output" not in text


class TestInstallFreshness:
    """RONDO-345: doctor warns when the installed tool's build stamp is stale.

    TWO live incidents in two days traced to a silently-stale installed
    binary (morning 404s; the USH 'Invalid model' panel ran a tool weeks
    behind the repo). Staleness must be VISIBLE in the first command
    support asks anyone to run.
    """

    def test_versions_warns_when_build_stamp_stale(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Build stamp older than 14 days → WARN with a reinstall hint."""
        import rondo.doctor as _doc

        monkeypatch.setattr(_doc, "_installed_version", lambda: "0.7.0+20260101.1")
        row = _doc._check_versions()
        assert row.result == "WARN", f"stale stamp must WARN, got {row.result}: {row.detail}"
        assert "reinstall" in (row.fix or "").lower()

    def test_versions_pass_when_stamp_fresh(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A recent build stamp stays PASS."""
        from datetime import UTC, datetime

        import rondo.doctor as _doc

        fresh = f"0.7.0+{datetime.now(UTC).strftime('%Y%m%d')}.1"
        monkeypatch.setattr(_doc, "_installed_version", lambda: fresh)
        row = _doc._check_versions()
        assert row.result == "PASS", f"fresh stamp must PASS, got {row.result}: {row.detail}"

    def test_versions_pass_when_no_stamp(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """No build stamp (plain PyPI install) → PASS, never punish strangers."""
        import rondo.doctor as _doc

        monkeypatch.setattr(_doc, "_installed_version", lambda: "0.7.0")
        row = _doc._check_versions()
        assert row.result == "PASS"


# -- sig: mgh-6201.cd.bd955f.ca74.5d0db3
