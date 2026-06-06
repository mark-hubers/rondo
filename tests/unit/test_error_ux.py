# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Error-UX contract — RONDO-335 (SOP-106 dimension 4).

VER-001 verification matrix: no raw tracebacks; every failure guides.

The live driver: `Unexpected error: 'dict' object has no attribute
'providers'` — no traceback (good) but also NO next step (bad). The
contract: every unexpected failure names a way forward (`rondo doctor`,
`--verbose`), and --verbose actually reveals the traceback for debugging.
"""

from __future__ import annotations

import pytest

from rondo.cli import EXIT_FAILURE, EXIT_USAGE, main


class TestSafetyNetGuidance:
    """The top-level net guides, never dumps, and --verbose opens the hood."""

    def _boom(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import rondo.cli as _cli

        def explode(args):  # noqa: ANN001, ANN202
            raise RuntimeError("synthetic internal failure")

        monkeypatch.setattr(_cli, "_dispatch_command", explode)

    def test_unexpected_error_guides_without_traceback(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        self._boom(monkeypatch)
        code = main(["doctor"])
        err = capsys.readouterr().err
        assert code == EXIT_FAILURE
        assert "Traceback" not in err  # -- never dump on users
        assert "synthetic internal failure" in err
        assert "rondo doctor" in err  # -- a way forward, always
        assert "--verbose" in err  # -- and the debug escape hatch

    def test_verbose_reveals_traceback(self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture) -> None:
        self._boom(monkeypatch)
        code = main(["doctor", "--verbose"])
        err = capsys.readouterr().err
        assert code == EXIT_FAILURE
        assert "Traceback" in err  # -- debugging is one flag away
        assert "RuntimeError" in err


class TestUserErrorPaths:
    """Known user mistakes exit cleanly with friendly messages."""

    def test_missing_round_file_friendly(self, capsys: pytest.CaptureFixture) -> None:
        code = main(["run", "/nope/missing.yaml"])
        err = capsys.readouterr().err
        assert code == EXIT_FAILURE
        assert "Traceback" not in err
        assert "not found" in err.lower()

    def test_unknown_subcommand_is_usage_error(self) -> None:
        ## -- single word → argparse path → usage exit, never a crash
        code = main(["definitely-not-a-command"])
        assert code in (EXIT_USAGE, EXIT_FAILURE)


class TestExitCodesDocumented:
    """SOP-106 dim 4: the exit-code contract is IN the --help text."""

    def test_help_epilog_lists_exit_codes(self, capsys: pytest.CaptureFixture) -> None:
        ## -- main() catches SystemExit by design (exit-code contract) — it
        ## -- RETURNS argparse's exit code rather than raising
        code = main(["--help"])
        out = capsys.readouterr().out
        assert code == 0
        assert "Exit codes" in out
        assert "130" in out  # -- the interrupt contract is spelled out


# -- sig: mgh-6201.cd.bd955f.ec1b.c3094d
