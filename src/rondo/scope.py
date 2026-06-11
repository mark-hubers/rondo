# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Scope guard — Rondo-REQ-116: one or two things per step, by default.

A lie needs ambiguity to hide in. A step that bundles ten tasks has ten
places to fudge; a step that asks for one has none. This module scores the
SHAPE of a step's ask so the pipeline can WARN on fat steps (default), BLOCK
them in opt-in strict mode, or exempt a genuinely-broad step (allow_broad).

It is a HEURISTIC, not comprehension — surface signals only, deterministic,
no I/O, no AI. The warn-default + override exist precisely because it is
fallible (REQ-116 §3). Leaf module: pure stdlib, no rondo imports.
"""

from __future__ import annotations

import re
from typing import TypedDict

# -- Above this score a step is "fat" — flagged (warn) or blocked (strict).
_SCOPE_THRESHOLD = 3


class ScopeScore(TypedDict):
    """Result of scope_score — typed so callers index score/signals cleanly."""

    score: int
    signals: list[str]


# -- Conjoined-imperative signals: a step chaining multiple actions.
_CONJUNCTIONS = (" and then ", " then ", " also ", " additionally ", " and also ")

# -- A path-like token: word(s) with a file extension (foo.py, src/bar.txt).
_PATH_RE = re.compile(r"\b[\w/.-]+\.[A-Za-z0-9]{1,6}\b")

# -- A numbered or bulleted sub-task line ("1. ...", "- ...", "* ...").
_SUBTASK_RE = re.compile(r"^\s*(?:\d+[.)]|[-*])\s+\S", re.MULTILINE)


def scope_score(prompt: str) -> ScopeScore:
    """Heuristic scope score for a step prompt — REQ-116 reqs 001-003.

    Returns {"score": int, "signals": [str]}. Higher = more bundled. A
    focused single task scores 0-1; a clearly multi-task ask clears the
    threshold. Deterministic and pure.
    """
    lowered = f" {prompt.lower()} "
    signals: list[str] = []

    conj_hits = sum(lowered.count(c) for c in _CONJUNCTIONS)
    if conj_hits:
        signals.append(f"{conj_hits} conjoined-action phrase(s) (and then / also / additionally)")

    subtasks = len(_SUBTASK_RE.findall(prompt))
    if subtasks:
        signals.append(f"{subtasks} numbered/bulleted sub-task line(s)")

    # -- distinct file paths BEYOND the first (one file = focused; many = fat)
    paths = {m.group(0) for m in _PATH_RE.finditer(prompt)}
    extra_paths = max(0, len(paths) - 1)
    if extra_paths:
        signals.append(f"{extra_paths} extra file path(s) beyond the first: {sorted(paths)}")

    score = conj_hits + subtasks + extra_paths
    return {"score": score, "signals": signals}


def is_over_threshold(prompt: str) -> bool:
    """True when a prompt's scope score clears _SCOPE_THRESHOLD."""
    return scope_score(prompt)["score"] >= _SCOPE_THRESHOLD


# -- sig: mgh-6201.cd.bd955f.8a7c.031313
