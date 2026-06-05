# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Tests for rondo.retry_queue — STD-108 reqs 015-018 (RONDO-303).

Driver: 50 stale files in ~/.rondo/retry/, 60% ERR_SUBPROCESS_FOOTGUN
(permanent blocks that can NEVER succeed on retry). The queue was a
write-only bin: no classification, no aging, no alerting.
"""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from rondo.retry_queue import (
    DEAD_LETTER_DIRNAME,
    classify_retryability,
    list_queue,
    queue_depth_alert,
    sweep_retry_queue,
)

# -- ──────────────────────────────────────────────────────────────
# --  Helpers
# -- ──────────────────────────────────────────────────────────────

NOW = datetime(2026, 6, 5, 12, 0, tzinfo=UTC)


def _write_entry(retry_dir: Path, dispatch_id: str, error_code: str, age_days: float = 0.0) -> Path:
    """Write a retry entry with a given error class and age."""
    retry_dir.mkdir(parents=True, exist_ok=True)
    path = retry_dir / f"{dispatch_id}.json"
    saved_at = (NOW - timedelta(days=age_days)).isoformat()
    payload = {
        "dispatch_id": dispatch_id,
        "saved_at": saved_at,
        "tasks": [{"task_name": "t1", "status": "error", "error_code": error_code}],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


# -- ──────────────────────────────────────────────────────────────
# --  Req 015: classification at enqueue/sweep time
# -- ──────────────────────────────────────────────────────────────


class TestClassification:
    """STD-108 req 015: transient vs permanent — permanent never retries."""

    def test_footgun_is_permanent(self) -> None:
        assert classify_retryability("ERR_SUBPROCESS_FOOTGUN") == "permanent"

    def test_auth_is_permanent(self) -> None:
        assert classify_retryability("ERR_AUTH") == "permanent"

    def test_timeout_is_transient(self) -> None:
        assert classify_retryability("ERR_TIMEOUT") == "transient"

    def test_rate_limit_is_transient(self) -> None:
        assert classify_retryability("ERR_RATE_LIMIT") == "transient"

    def test_provider_down_is_transient(self) -> None:
        assert classify_retryability("ERR_PROVIDER_DOWN") == "transient"

    def test_unknown_defaults_transient(self) -> None:
        """Unknown codes default transient — never silently dead-letter new codes."""
        assert classify_retryability("ERR_SOMETHING_NEW") == "transient"


# -- ──────────────────────────────────────────────────────────────
# --  Reqs 015-016: sweep — dead-letter permanent + expired entries
# -- ──────────────────────────────────────────────────────────────


class TestSweep:
    """STD-108 reqs 015-016: permanent → dead-letter; aged-out → dead-letter."""

    def test_permanent_entry_moves_to_dead_letter(self, tmp_path: Path) -> None:
        retry_dir = tmp_path / "retry"
        _write_entry(retry_dir, "dsp_perm", "ERR_SUBPROCESS_FOOTGUN")
        report = sweep_retry_queue(str(retry_dir), now=NOW)
        assert report.dead_lettered_permanent == 1
        assert not (retry_dir / "dsp_perm.json").exists()
        assert (retry_dir / DEAD_LETTER_DIRNAME / "dsp_perm.json").exists()

    def test_transient_fresh_entry_stays(self, tmp_path: Path) -> None:
        retry_dir = tmp_path / "retry"
        _write_entry(retry_dir, "dsp_fresh", "ERR_TIMEOUT", age_days=1)
        report = sweep_retry_queue(str(retry_dir), now=NOW)
        assert report.remaining == 1
        assert (retry_dir / "dsp_fresh.json").exists()

    def test_aged_out_entry_dead_letters_as_expired(self, tmp_path: Path) -> None:
        """STD-108 req 016: older than retry_max_age_days → dead-letter 'expired'."""
        retry_dir = tmp_path / "retry"
        _write_entry(retry_dir, "dsp_old", "ERR_TIMEOUT", age_days=10)
        report = sweep_retry_queue(str(retry_dir), max_age_days=7, now=NOW)
        assert report.dead_lettered_expired == 1
        assert (retry_dir / DEAD_LETTER_DIRNAME / "dsp_old.json").exists()

    def test_dead_letter_records_reason(self, tmp_path: Path) -> None:
        retry_dir = tmp_path / "retry"
        _write_entry(retry_dir, "dsp_perm", "ERR_AUTH")
        sweep_retry_queue(str(retry_dir), now=NOW)
        moved = json.loads((retry_dir / DEAD_LETTER_DIRNAME / "dsp_perm.json").read_text(encoding="utf-8"))
        assert moved["dead_letter_reason"] == "permanent:ERR_AUTH"

    def test_missing_dir_is_empty_report(self, tmp_path: Path) -> None:
        report = sweep_retry_queue(str(tmp_path / "nope"), now=NOW)
        assert report.remaining == 0


# -- ──────────────────────────────────────────────────────────────
# --  Req 017: depth alert
# -- ──────────────────────────────────────────────────────────────


class TestDepthAlert:
    """STD-108 req 017: silent queue growth is forbidden."""

    def test_below_threshold_no_alert(self) -> None:
        assert queue_depth_alert(3, threshold=10) is None

    def test_above_threshold_alerts(self) -> None:
        msg = queue_depth_alert(15, threshold=10)
        assert msg is not None
        assert "15" in msg


# -- ──────────────────────────────────────────────────────────────
# --  Req 018: list with age + class + reason
# -- ──────────────────────────────────────────────────────────────


class TestListQueue:
    """STD-108 req 018: queue is inspectable — age, class, one-line reason."""

    def test_list_shows_age_class_reason(self, tmp_path: Path) -> None:
        retry_dir = tmp_path / "retry"
        _write_entry(retry_dir, "dsp_a", "ERR_TIMEOUT", age_days=2)
        entries = list_queue(str(retry_dir), now=NOW)
        assert len(entries) == 1
        entry = entries[0]
        assert entry["dispatch_id"] == "dsp_a"
        assert entry["error_class"] == "transient"
        assert 1.9 < entry["age_days"] < 2.1
        assert "ERR_TIMEOUT" in entry["reason"]

    def test_list_empty_dir(self, tmp_path: Path) -> None:
        assert list_queue(str(tmp_path / "nope"), now=NOW) == []


# -- sig: mgh-6201.cd.bd955f.f1a7.rq303a
