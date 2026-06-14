# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Cross-vendor jury — Rondo's thesis as a first-class capability (REQ-118, RONDO-431).

The moat single-vendor tools structurally can't copy: the model that WROTE an
artifact does NOT get to certify it; DIFFERENT vendors independently judge it, and
DISAGREEMENT is surfaced as the signal (it's the bug nobody else would have
caught). `controlled_review_loop.py` hand-wired this; `jury_review` makes it
reusable, testable, and callable (MCP tool `rondo_jury`).

Verdict channel = the smart-return `passed` field, which rondo normalizes across
vendors (a custom key goes missing on some — see RONDO-419 git log). A juror that
errors or returns no parseable verdict is INCONCLUSIVE (never a silent "no").

Import direction: leaf-ish — stdlib + rondo.verify (extract_json_object) + a lazy
guarded-dispatch import; tests inject the dispatch seam (the matrix pattern).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from rondo.verify import extract_json_object

JurorDispatch = Callable[[str, str], dict[str, Any]]

DEFAULT_JURORS = ["gemini:high", "grok:grok-4.3"]


def _review_prompt(artifact: str, question: str) -> str:
    """The juror prompt: judge BEHAVIORAL correctness, answer on the `passed` channel."""
    return (
        f"You are a code reviewer from a DIFFERENT team than the author. Review this artifact:\n\n"
        f"```\n{artifact}\n```\n\n{question}\n"
        "Judge BEHAVIORAL correctness only (ignore style). Set passed=true ONLY if it is "
        "actually correct for ALL reasonable inputs; else passed=false with the flaw. "
        'Respond with ONLY JSON: {"passed": true|false, "result": "one-line reason"}'
    )


def _one_verdict(model: str, artifact: str, question: str, dispatch: JurorDispatch) -> dict[str, Any]:
    """Get one juror's verdict: {model, reached, passed, why}. Unreachable -> reached=False."""
    raw = dispatch(_review_prompt(artifact, question), model)
    if raw.get("status") != "done":
        return {"model": model, "reached": False, "passed": False, "why": "unreachable"}
    verdict = extract_json_object(str(raw.get("raw_output", "")))
    if verdict is None or "passed" not in verdict:
        return {"model": model, "reached": False, "passed": False, "why": "no parseable verdict"}
    return {
        "model": model,
        "reached": True,
        "passed": bool(verdict.get("passed")),
        "why": str(verdict.get("result", "")),
    }


def _default_dispatch(prompt: str, model: str) -> dict[str, Any]:
    """Production dispatch — the guarded path (audit/sanitize/envelopes apply)."""
    from rondo.mcp_dispatch import rondo_run_file  # noqa: PLC0415  # pylint: disable=import-outside-toplevel

    envelope = json.loads(rondo_run_file(prompt=prompt, model=model, dry_run=False))
    task = (envelope.get("tasks") or [{}])[0]
    return {"status": task.get("status", "error"), "raw_output": task.get("raw_output", "")}


def jury_review(
    artifact: str,
    question: str,
    jurors: list[str] | None = None,
    dispatch: JurorDispatch | None = None,
) -> dict[str, Any]:
    """Convene a cross-vendor jury on an artifact — the thesis gate.

    Each juror (a DIFFERENT vendor) independently reviews; accepted ONLY if at least
    one juror was reached AND every reached juror agrees (passed). Returns the full
    verdict set, the counts, and the DISAGREEMENT (the objecting jurors) — the
    disagreement is the product. An unreachable/unparseable juror is inconclusive,
    never a silent no-vote.
    """
    jurors = jurors or DEFAULT_JURORS
    dispatch = dispatch or _default_dispatch
    verdicts = [_one_verdict(m, artifact, question, dispatch) for m in jurors]
    reached = [v for v in verdicts if v["reached"]]
    agree = [v for v in reached if v["passed"]]
    disagreement = [v for v in reached if not v["passed"]]
    accepted = len(reached) >= 1 and len(agree) == len(reached)
    return {
        "accepted": accepted,
        "reached": len(reached),
        "agree": len(agree),
        "verdicts": verdicts,
        "disagreement": disagreement,
    }


# -- sig: mgh-6201.cd.bd955f.4ae7.d1a19d
