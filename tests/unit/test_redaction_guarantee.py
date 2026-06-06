# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Redaction GUARANTEE tests — RONDO-321 (SOP-105 P1-7, Cursor pass).

Not function-level tests of sanitize_text — ARTIFACT-level proof: plant
key-shaped secrets at every ingress (prompt, error message, notification)
and sweep every file Rondo wrote. Zero survivors or the test fails.
"""

from __future__ import annotations

from pathlib import Path

import pytest

## -- fake secrets at REAL provider lengths (a too-short fake passes a
## -- correctly-strict pattern and proves nothing — first run's lesson:
## -- ghp_ wants exactly 36 trailing chars, AIza wants 35).
## -- All built by CONCATENATION so gitleaks never sees a key-shaped
## -- literal in source (it rightly blocked whole-string fakes at commit).
PLANTED = (
    "sk-ant-" + "api03-" + "FAKEFAKE" * 4 + "1234",
    "sk-proj-" + "FAKEFAKE" * 4 + "5678",
    "AKIA" + "FAKEFAKE" * 2,
    "ghp_" + "FAKEfake" * 4 + "1234",  # -- ghp_ + 36 chars (classic PAT length)
    "xoxb-" + "1111111111-2222222222-" + "FAKEfakeFAKE",
    "AIza" + "FAKEfake" * 4 + "123",  # -- AIza + 35 chars (Google key length)
)


def _sweep_tree(root: Path) -> list[str]:
    """Return every (file, secret) hit under root — the guarantee sweep."""
    hits: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for secret in PLANTED:
            if secret in text:
                hits.append(f"{path.name}: {secret[:14]}…")
    return hits


@pytest.fixture
def audit_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Hermetic audit home with RONDO_TEST_DIR pointed at it."""
    monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))
    return tmp_path


class TestAuditTrailGuarantee:
    """Secrets in prompts/errors never reach ANY audit artifact."""

    def test_prompt_secrets_never_reach_disk(self, audit_env: Path) -> None:
        from rondo.audit import AuditConfig, AuditTrail

        trail = AuditTrail(config=AuditConfig(audit_dir=str(audit_env / "audit")))
        prompt = "Review this config:\n" + "\n".join(f"key_{i} = {s}" for i, s in enumerate(PLANTED))
        trail.record_intent(task_name="t", round_name="r", model="sonnet", prompt=prompt)
        hits = _sweep_tree(audit_env)
        assert not hits, f"planted secrets survived into audit artifacts: {hits}"

    def test_error_message_secrets_never_reach_jsonl(self, audit_env: Path) -> None:
        from rondo.audit import AuditConfig, AuditTrail

        trail = AuditTrail(config=AuditConfig(audit_dir=str(audit_env / "audit")))
        rec = trail.record_intent(task_name="t", round_name="r", model="sonnet", prompt="hi")
        trail.record_outcome(
            dispatch_id=rec.dispatch_id,
            status="error",
            error_code="ERR_AUTH",
            error_message=f"401 for key {PLANTED[0]} — rejected",
            raw_output=f"server said: invalid token {PLANTED[3]}",
        )
        hits = _sweep_tree(audit_env)
        assert not hits, f"planted secrets survived into audit artifacts: {hits}"


class TestNotifyGuarantee:
    """Notification channels (file log, macOS string) never carry secrets."""

    def test_failure_notification_log_is_redacted(self, audit_env: Path) -> None:
        from rondo.notify import NotifyConfig, notify_failure

        log_file = audit_env / "notifications.log"
        notify_failure(
            task_name="t",
            error_code="ERR_AUTH",
            error_message=f"provider rejected {PLANTED[1]}",
            config=NotifyConfig(channels=["file"], log_file=str(log_file)),
        )
        hits = _sweep_tree(audit_env)
        assert not hits, f"planted secrets survived into notification log: {hits}"

    def test_watchdog_notification_log_is_redacted(self, audit_env: Path) -> None:
        from rondo.notify import NotifyConfig, notify_watchdog

        log_file = audit_env / "notifications.log"
        notify_watchdog(
            [f"drift check failed: 401 with {PLANTED[4]}"],
            config=NotifyConfig(channels=["file"], log_file=str(log_file)),
        )
        hits = _sweep_tree(audit_env)
        assert not hits, f"planted secrets survived into notification log: {hits}"
