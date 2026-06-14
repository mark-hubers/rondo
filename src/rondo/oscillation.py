# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Oscillation detection — Rondo-STD-116 (minimal).

A retry loop that keeps producing the EXACT same observable result is not making
progress — the model is repeating itself ("fix A breaks B, fix B breaks A", or
just re-emitting the same wrong output). rondo's bounded retries + budget already
stop it from running forever; this adds the missing SIGNAL: name the thrash
(ERR_OSCILLATION) and let the caller break early instead of burning the last retry.

Deliberately MINIMAL (cross-vendor decision 2026-06-13: grok judged a heavy
circuit-breaker redundant with capped retries; gemini judged a deterministic
round-signature cheap + field-rare). Pure stdlib leaf — no rondo imports.
"""

from __future__ import annotations

import hashlib


def round_signature(error: str, raw_output: str) -> str:
    """Deterministic signature of one retry round's OBSERVABLE result.

    Hashes (error, raw_output) with a separator so ('a','bc') != ('ab','c'). Two
    rounds with the same signature means the loop reproduced an identical result —
    the marker of thrash, not progress.
    """
    h = hashlib.sha256()
    h.update((error or "").encode("utf-8"))
    h.update(b"\x00")  # -- field separator: prevent boundary collisions
    h.update((raw_output or "").encode("utf-8"))
    return h.hexdigest()


def detect_repeat(signatures: list[str]) -> int | None:
    """If the LATEST signature equals an earlier one, return that earlier index.

    Checks only the most recent round (we decide per new round whether THIS round
    reverted to a prior state). Returns None when the latest is novel, or when
    there are fewer than two rounds.
    """
    if len(signatures) < 2:
        return None
    last = signatures[-1]
    for i in range(len(signatures) - 1):
        if signatures[i] == last:
            return i
    return None


# -- sig: mgh-6201.cd.bd955f.a909.94c03b
