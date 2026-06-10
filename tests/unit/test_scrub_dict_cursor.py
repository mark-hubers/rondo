# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Mutation-gate regression: _scrub_dict nested scrubbing must be asserted.

VER-001 verification matrix: nested secret-scrubbing in parsed_result.

Quality-checklist item 9 (mutation gate): sanitize_task_result() routes every
task's parsed_result through _scrub_dict (src/rondo/sanitize.py ~line 501).
_scrub_dict recurses dicts/lists and scrubs leaf strings, BUT the mutation gate
proved NO existing test asserts its output: mutants replacing its returns with
None survived every sanitize test. If nested scrubbing silently broke, secrets
would flow into spool/results/audit artifacts while the suite stayed green.

These tests assert OBSERVABLE outcomes on the scrubbed parsed_result so that a
mutant making _scrub_dict return None (or skip recursion) now FAILS:
parsed_result would become None / lose structure / leak the secret.

Credentials policy: only gitleaks-allowlisted example values. The bare AWS key
AKIAIOSFODNN7EXAMPLE is the proven-safe fixture already used across tests/. The
GitHub-PAT-shaped value is constructed at runtime (``"ghp_" + "A" * 40``), the
same gitleaks-safe pattern used by the integration tests, so no real-looking
novel key ever lands in this file.
"""

import json

from rondo.engine import TaskResult
from rondo.sanitize import sanitize_task_result

# -- Canonical AWS example key: matches the aws_access_key pattern
# -- (AKIA + 16 upper/digit chars) and is allowlisted by the repo's gitleaks
# -- pre-commit hook (reused verbatim from tests/unit/test_sanitize.py).
AWS_EXAMPLE_KEY = "AKIAIOSFODNN7EXAMPLE"

# -- GitHub-PAT-shaped value built at runtime so gitleaks never sees a literal
# -- 40-char token in source. ghp_ + 36+ chars is caught by the
# -- github_personal_access_token pattern.
GITHUB_PAT_SHAPED = "ghp_" + ("A" * 40)


class TestScrubDictNestedSecrets:
    """_scrub_dict must scrub secrets at any depth while preserving structure."""

    def test_nested_secrets_scrubbed_structure_preserved(self) -> None:
        """Nested AWS + GitHub secrets are redacted; clean text + shape survive."""
        tr = TaskResult(
            task_name="test",
            parsed_result={
                "config": {
                    "aws": AWS_EXAMPLE_KEY,
                    "list": [{"token": GITHUB_PAT_SHAPED}],
                },
                "ok": "clean text",
            },
        )
        sanitized_tr, sr = sanitize_task_result(tr)
        result = sanitized_tr.parsed_result
        dumped = json.dumps(result)

        # -- (5) kill the return-None mutant: result must be a usable dict,
        # -- not None, with the original top-level keys intact.
        assert isinstance(result, dict), "_scrub_dict returned non-dict (mutant?)"
        assert set(result.keys()) == {"config", "ok"}

        # -- (a) nested secrets are GONE from the scrubbed output.
        assert AWS_EXAMPLE_KEY not in dumped
        assert GITHUB_PAT_SHAPED not in dumped

        # -- (b) clean text survives untouched.
        assert result["ok"] == "clean text"

        # -- (c) dict/list STRUCTURE preserved at every level.
        assert isinstance(result["config"], dict)
        assert set(result["config"].keys()) == {"aws", "list"}
        assert isinstance(result["config"]["list"], list)
        assert len(result["config"]["list"]) == 1
        assert isinstance(result["config"]["list"][0], dict)
        assert set(result["config"]["list"][0].keys()) == {"token"}

        # -- (d) detections were recorded (API exposes them on SanitizeResult).
        assert sr.secrets_found >= 2
        assert len(sr.detections) >= 2

    def test_secret_three_levels_deep_still_scrubbed(self) -> None:
        """A secret in dict -> list -> dict (3+ levels deep) is still scrubbed."""
        tr = TaskResult(
            task_name="test",
            parsed_result={
                "outer": {
                    "items": [
                        {"deep": AWS_EXAMPLE_KEY},
                    ],
                },
            },
        )
        sanitized_tr, sr = sanitize_task_result(tr)
        result = sanitized_tr.parsed_result

        assert isinstance(result, dict), "_scrub_dict returned non-dict (mutant?)"
        assert AWS_EXAMPLE_KEY not in json.dumps(result)
        # -- structure to the leaf is preserved.
        deep = result["outer"]["items"][0]
        assert isinstance(deep, dict)
        assert set(deep.keys()) == {"deep"}
        assert AWS_EXAMPLE_KEY not in deep["deep"]
        assert sr.secrets_found >= 1

    def test_non_string_leaves_pass_through_unchanged(self) -> None:
        """ints/None/bools/floats in the structure survive intact (no crash)."""
        tr = TaskResult(
            task_name="test",
            parsed_result={
                "count": 42,
                "ratio": 3.14,
                "enabled": True,
                "disabled": False,
                "missing": None,
                "nested": {"items": [1, 2, None, True], "flag": False},
                "secret": AWS_EXAMPLE_KEY,
            },
        )
        sanitized_tr, _ = sanitize_task_result(tr)
        result = sanitized_tr.parsed_result

        assert isinstance(result, dict), "_scrub_dict returned non-dict (mutant?)"
        # -- non-string leaves pass through byte-for-byte.
        assert result["count"] == 42
        assert result["ratio"] == 3.14
        assert result["enabled"] is True
        assert result["disabled"] is False
        assert result["missing"] is None
        assert result["nested"]["items"] == [1, 2, None, True]
        assert result["nested"]["flag"] is False
        # -- and the string secret alongside them is still scrubbed.
        assert AWS_EXAMPLE_KEY not in json.dumps(result)

    def test_top_level_list_parsed_result_scrubbed(self) -> None:
        """A list-typed parsed_result is recursed and scrubbed, not nulled."""
        tr = TaskResult(
            task_name="test",
            parsed_result=[
                {"aws": AWS_EXAMPLE_KEY},
                "clean entry",
                7,
            ],
        )
        sanitized_tr, sr = sanitize_task_result(tr)
        result = sanitized_tr.parsed_result

        # -- kill the return-None mutant on the list branch too.
        assert isinstance(result, list), "_scrub_dict returned non-list (mutant?)"
        assert len(result) == 3
        assert isinstance(result[0], dict)
        assert AWS_EXAMPLE_KEY not in json.dumps(result)
        assert result[1] == "clean entry"
        assert result[2] == 7
        assert sr.secrets_found >= 1


# -- sig: mgh-6201.cd.bd955f.b541.848df4
