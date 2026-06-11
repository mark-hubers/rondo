# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Regression judges for ROAD-TO-8 item R2-3: matrix cell outputs must be SCRUBBED.

VER-001: Product acceptance / unit test coverage.

AUTHOR: gemini-2.5-pro via rondo_run (Cursor usage-limited). Transcription
notes, documented not silent: (1) the author's fixture constant came back
"[REDACTED:...]" — rondo's own sanitize scrubbed the canonical fake key inside
the dispatch result again; restored. (2) The dispatch response TRUNCATED after
test 2's manifest assertion; the secret-sweep loop in test 2 is completed
following the author's identical loop in test 1 (mechanical completion).
(3) test_clean_rail is a LABELED Claude top-up (the rail, not the RED kill).

THE BUG (re-score finding #3, review-20260610-184904.md): _write_cell_output
persists raw model output verbatim — a secret echoed by a matrix model lands
in {stem}.txt unscrubbed (STD-114 r006 MUST).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from rondo.matrix import load_matrix, run_matrix

# -- the gitleaks-allowlisted canonical fake (AWS docs example key)
_AWS_EXAMPLE_KEY = "AKIAIOSFODNN7EXAMPLE"  # noqa: S105 -- fake; used to assert redaction

GOOD_YAML = """\
name: demo
prompt: "Reply with exactly: OK"
models: [anthropic:claude-opus-4-8, openai:gpt-5.5]
efforts: [low, max]
contexts:
  blind: none
replicates: 2
budget_usd: 1.00
"""


def _write_yaml(tmp_path: Path, text: str = GOOD_YAML) -> str:
    """Write the experiment YAML fixture and return its path."""
    p = tmp_path / "exp.yaml"
    p.write_text(text, encoding="utf-8")
    return str(p)


def test_matrix_scrubs_secrets_from_output(tmp_path: Path) -> None:
    """(a) Secrets in dispatch output are scrubbed before the cell file is written."""

    def my_dispatch(cell: dict, prompt: str) -> dict:  # noqa: ARG001
        return {
            "status": "done",
            "cost_usd": 0.01,
            "latency_sec": 1.0,
            "output": f"Here is the secret: {_AWS_EXAMPLE_KEY}",
            "self_rating": 8.0,
        }

    spec = load_matrix(_write_yaml(tmp_path))
    run_matrix(spec, dispatch=my_dispatch, effort_capable=lambda m: True, base_dir=str(tmp_path), estimate_ok=True)

    txt_files = list(Path(tmp_path).rglob("*.txt"))
    assert txt_files, "expected cell output files to be written"

    for txt_file in txt_files:
        content = txt_file.read_text(encoding="utf-8")
        assert _AWS_EXAMPLE_KEY not in content, f"secret leaked into {txt_file}"
        assert "[REDACTED" in content, f"expected redaction marker in {txt_file}"


def test_matrix_withholds_output_on_scrub_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """(b) Scrub failure: run completes, NO cell file contains the raw secret."""

    def failing_sanitize(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("Simulated scrubber failure")

    # -- raising=False: the symbol lands in rondo.matrix with the fix
    monkeypatch.setattr("rondo.matrix.sanitize_text", failing_sanitize, raising=False)

    def my_dispatch(cell: dict, prompt: str) -> dict:  # noqa: ARG001
        return {
            "status": "done",
            "cost_usd": 0.01,
            "latency_sec": 1.0,
            "output": f"Secret inside: {_AWS_EXAMPLE_KEY}",
            "self_rating": 8.0,
        }

    spec = load_matrix(_write_yaml(tmp_path))
    manifest = run_matrix(
        spec, dispatch=my_dispatch, effort_capable=lambda m: True, base_dir=str(tmp_path), estimate_ok=True
    )

    assert manifest is not None, "run must complete and return a manifest despite scrub failures"

    # -- completed per the author's test-1 loop (response truncated here)
    for txt_file in Path(tmp_path).rglob("*.txt"):
        content = txt_file.read_text(encoding="utf-8")
        assert _AWS_EXAMPLE_KEY not in content, f"raw secret persisted on scrub failure: {txt_file}"


# -- Claude top-up (labeled, RONDO-402): the clean rail — author's response
# -- truncated before test 3; the rail pins no-overreach, not the kill.
def test_matrix_clean_output_unchanged_and_0600(tmp_path: Path) -> None:
    """(c) Clean output round-trips unchanged; file born 0o600 (POSIX)."""

    def my_dispatch(cell: dict, prompt: str) -> dict:  # noqa: ARG001
        return {
            "status": "done",
            "cost_usd": 0.01,
            "latency_sec": 1.0,
            "output": "perfectly clean output text",
            "self_rating": 8.0,
        }

    spec = load_matrix(_write_yaml(tmp_path))
    run_matrix(spec, dispatch=my_dispatch, effort_capable=lambda m: True, base_dir=str(tmp_path), estimate_ok=True)

    txt_files = list(Path(tmp_path).rglob("*.txt"))
    assert txt_files, "expected cell output files"
    for txt_file in txt_files:
        content = txt_file.read_text(encoding="utf-8")
        assert content == "perfectly clean output text", "clean output must round-trip unchanged"
        assert "[REDACTED" not in content
        if os.name == "posix":
            assert txt_file.stat().st_mode & 0o777 == 0o600


# -- sig: mgh-6201.cd.bd955f.be0c.f642a7
