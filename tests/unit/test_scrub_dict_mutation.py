# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Mutation kill-tests for sanitize._scrub_dict — the recursive structure scrubber.

VER-001: Product acceptance / sanitization structural contract.

WHY: a mutation sweep (bin/mutate, 2026-06-12) left _scrub_dict's four return
paths surviving — the existing sanitize tests verify a secret is DETECTED but
not that the scrubbed STRUCTURE is returned intact. A regression making
_scrub_dict `return None` would DROP every scrubbed field (parsed_result,
command_sent, context_data in sanitize_task_result) and still pass — silent
data loss, violating both the scrub contract and "never lose data".

This pins the contract: secrets scrubbed, non-secrets preserved, dict/list
structure preserved, non-string scalars passed through. Only the
gitleaks-allowlisted example key is used. Behavior verified live before asserting.

After this suite the sanitize.py sweep is 35/36. The lone survivor is a
DOCUMENTED EQUIVALENT (house rule): the `repr=False` bool in
`compiled: re.Pattern = field(init=False, repr=False)` — flipping it changes only
the dataclass repr() text, which no contract asserts. (Its twin `init=False`->True
IS caught: it breaks construction at import. Verified, not assumed.)
"""

from __future__ import annotations

from rondo.sanitize import _scrub_dict

_FAKE_KEY = "AKIAIOSFODNN7EXAMPLE"  # -- gitleaks-allowlisted example AWS key
_REDACTED = "[REDACTED:aws_access_key]"


def test_scrub_dict_returns_intact_scrubbed_structure() -> None:
    """The scrubbed structure is RETURNED (kills the L535/537/539/540 return-none mutants)."""
    detections: list = []
    obj = {
        "key": _FAKE_KEY,  # -- secret string: L535 scrubs + returns
        "safe": "hello",  # -- non-secret string preserved
        "nested": {"n": 42, "tok": _FAKE_KEY},  # -- L537 dict recursion + L540 int passthrough
        "lst": ["plain", _FAKE_KEY],  # -- L539 list recursion
        "flag": True,  # -- L540 non-string scalar passthrough
    }
    out = _scrub_dict(obj, detections=detections)

    # -- structure preserved (None would fail every one of these)
    assert isinstance(out, dict)
    assert out["key"] == _REDACTED  # -- L535: the str branch returns the scrubbed text
    assert out["safe"] == "hello"  # -- non-secret untouched
    assert isinstance(out["nested"], dict)  # -- L537: dict comprehension returns a dict
    assert out["nested"]["tok"] == _REDACTED
    assert out["nested"]["n"] == 42  # -- L540: int passed through unchanged
    assert out["lst"] == ["plain", _REDACTED]  # -- L539: list comprehension returns the list
    assert out["flag"] is True  # -- L540: bool passed through unchanged
    # -- and the secret was actually found (3 occurrences)
    assert len(detections) == 3


def test_scrub_dict_scalar_passthrough_is_identity() -> None:
    """A bare non-container scalar is returned unchanged (kills L540 `return obj` -> None)."""
    detections: list = []
    assert _scrub_dict(42, detections=detections) == 42
    assert _scrub_dict(True, detections=detections) is True
    assert _scrub_dict(None, detections=detections) is None
    assert detections == []  # -- nothing to scrub in a scalar


# -- sig: mgh-6201.cd.bd955f.c321.9ee791
