# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Round-file trust model — RONDO-330 (SOP-105 P1-3, all 4 AIs ranked top).

VER-001 verification matrix: .py rounds gated behind explicit opt-in.

"A downloaded round file = running code." Declarative YAML/JSON rounds are
the safe shareable format; loading a .py round must be an explicit, loud
decision — never a silent import of someone else's executable.
"""

from __future__ import annotations

from pathlib import Path

import pytest

PY_ROUND = '''
from rondo.engine import Round, Task

def build_round():
    return Round(name="r", tasks=[Task(name="t", instruction="x", done_when="d")])
'''


@pytest.fixture
def py_round(tmp_path: Path) -> str:
    p = tmp_path / "downloaded_round.py"
    p.write_text(PY_ROUND)
    return str(p)


@pytest.fixture
def no_config_allow(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Hermetic: no live config can grant the allowance."""
    monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))
    from rondo import round_loader

    monkeypatch.setattr(round_loader, "_config_allows_python_rounds", lambda: False)


class TestPythonRoundGate:
    """P1-3: .py rounds refused by default; explicit opt-ins only."""

    def test_py_round_refused_by_default(self, py_round: str, no_config_allow) -> None:
        from rondo.round_loader import PythonRoundBlockedError, load_round

        with pytest.raises(PythonRoundBlockedError) as exc:
            load_round(py_round)
        msg = str(exc.value)
        assert "running code" in msg  # -- the WHY, not just a refusal
        assert "--allow-python-rounds" in msg  # -- the fix, right there
        assert "yaml" in msg.lower()  # -- the safe alternative

    def test_py_round_allowed_with_explicit_flag(self, py_round: str, no_config_allow) -> None:
        from rondo.round_loader import load_round

        loaded = load_round(py_round, allow_python=True)
        assert loaded.tasks[0].name == "t"

    def test_py_round_allowed_via_config(self, py_round: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """[security] allow_python_rounds = true → one-line permanent allow."""
        monkeypatch.setenv("RONDO_TEST_DIR", str(tmp_path))
        from rondo import round_loader

        monkeypatch.setattr(round_loader, "_config_allows_python_rounds", lambda: True)
        loaded = round_loader.load_round(py_round)
        assert loaded.tasks[0].name == "t"

    def test_yaml_rounds_never_gated(self, tmp_path: Path, no_config_allow) -> None:
        """Declarative formats are the SAFE path — zero friction."""
        from rondo.round_loader import load_round

        p = tmp_path / "r.yaml"
        p.write_text("name: r\ntasks:\n  - name: t\n    instruction: x\n    done_when: d\n")
        loaded = load_round(str(p))
        assert loaded.tasks[0].name == "t"

    def test_blocked_error_is_err_invalid_input_class(self, py_round: str, no_config_allow) -> None:
        """The gate refuses with a typed error callers can branch on."""
        from rondo.round_loader import PythonRoundBlockedError

        assert issubclass(PythonRoundBlockedError, ValueError)


# -- sig: mgh-6201.cd.bd955f.37cd.325254
