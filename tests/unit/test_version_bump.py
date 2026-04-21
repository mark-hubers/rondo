# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Unit tests for `bump_build()` and the `rondo version --bump` CLI — RONDO-290.

VER-001: Product acceptance / unit test coverage.

Finding #266: `bump_build()` was defined in _version.py but had zero callers.
RONDO-290 wires it into the `rondo version --bump` CLI command so ace-sprint
done hooks and CI pipelines can invoke it.

These tests cover:
    1. bump_build() increments same-day counter
    2. bump_build() resets to 1 on new day
    3. bump_build() writes counter file with correct shape
    4. CLI `rondo version` prints current version
    5. CLI `rondo version --bump` prints new version + writes counter
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from rondo import _version


class TestBumpBuild:
    """bump_build() — pure unit tests with isolated counter file."""

    def test_bump_increments_same_day(self, tmp_path: Path) -> None:
        counter_file = tmp_path / "counter.json"
        counter_file.write_text(json.dumps({"date": "20260101", "build": 5}))

        with (
            patch.object(_version, "_BUILD_FILE", counter_file),
            patch("rondo._version.datetime") as mock_dt,
        ):
            mock_dt.now.return_value.strftime.return_value = "20260101"
            result = _version.bump_build()

        assert result.endswith("+20260101.6"), f"got {result!r}"
        saved = json.loads(counter_file.read_text())
        assert saved == {"date": "20260101", "build": 6}

    def test_bump_resets_on_new_day(self, tmp_path: Path) -> None:
        counter_file = tmp_path / "counter.json"
        counter_file.write_text(json.dumps({"date": "20260101", "build": 42}))

        with (
            patch.object(_version, "_BUILD_FILE", counter_file),
            patch("rondo._version.datetime") as mock_dt,
        ):
            mock_dt.now.return_value.strftime.return_value = "20260102"
            result = _version.bump_build()

        assert result.endswith("+20260102.1"), f"got {result!r}"
        saved = json.loads(counter_file.read_text())
        assert saved == {"date": "20260102", "build": 1}

    def test_bump_starts_at_one_when_no_file(self, tmp_path: Path) -> None:
        counter_file = tmp_path / "counter.json"
        ## File does not exist

        with (
            patch.object(_version, "_BUILD_FILE", counter_file),
            patch("rondo._version.datetime") as mock_dt,
        ):
            mock_dt.now.return_value.strftime.return_value = "20260415"
            result = _version.bump_build()

        assert result.endswith("+20260415.1"), f"got {result!r}"
        assert counter_file.exists()

    def test_bump_returns_full_calver_plus_build_format(self, tmp_path: Path) -> None:
        counter_file = tmp_path / "counter.json"

        with (
            patch.object(_version, "_BUILD_FILE", counter_file),
            patch("rondo._version.datetime") as mock_dt,
        ):
            mock_dt.now.return_value.strftime.return_value = "20260415"
            result = _version.bump_build()

        ## Format: MAJOR.MINOR.PATCH+YYYYMMDD.BUILD
        assert "+" in result
        base, meta = result.split("+", 1)
        assert base.count(".") == 2  ## MAJOR.MINOR.PATCH
        assert "." in meta  ## date.build
        date_part, build_part = meta.split(".", 1)
        assert date_part == "20260415"
        assert build_part == "1"


class TestVersionCLICommand:
    """`rondo version` CLI — end-to-end with subprocess-free invocation."""

    def test_version_without_bump_prints_current(
        self, tmp_path: Path, capsys: object
    ) -> None:
        from rondo.cli_commands.infra import _cmd_version  # noqa: PLC0415

        counter_file = tmp_path / "counter.json"
        counter_file.write_text(json.dumps({"date": "20260101", "build": 7}))

        import argparse  # noqa: PLC0415

        args = argparse.Namespace(bump=False)
        with patch.object(_version, "_BUILD_FILE", counter_file):
            exit_code = _cmd_version(args)

        assert exit_code == 0
        out = capsys.readouterr().out  # type: ignore[attr-defined]
        assert "+20260101.7" in out

    def test_version_with_bump_increments_and_prints(
        self, tmp_path: Path, capsys: object
    ) -> None:
        from rondo.cli_commands.infra import _cmd_version  # noqa: PLC0415

        counter_file = tmp_path / "counter.json"
        counter_file.write_text(json.dumps({"date": "20260101", "build": 3}))

        import argparse  # noqa: PLC0415

        args = argparse.Namespace(bump=True)
        with (
            patch.object(_version, "_BUILD_FILE", counter_file),
            patch("rondo._version.datetime") as mock_dt,
        ):
            mock_dt.now.return_value.strftime.return_value = "20260101"
            exit_code = _cmd_version(args)

        assert exit_code == 0
        out = capsys.readouterr().out  # type: ignore[attr-defined]
        assert "+20260101.4" in out
        saved = json.loads(counter_file.read_text())
        assert saved["build"] == 4


# -- sig: mgh-6201.cd.bd955f.d266.f1b266
