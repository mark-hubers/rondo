# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Mutation-gate regression: spool.py path/TTL/filter contracts must be asserted.

VER-001 verification matrix: result-spool security and lifecycle behaviors.

Quality-checklist item 14 (mutation gate): src/rondo/spool.py is the worst module
in the repo — 36 of 58 mutants SURVIVE the entire spool test surface. Almost all
survivors are REAL: the behaviors are production-reachable yet completely
unasserted, so a regression would ship while the suite stayed green.

These tests pin the OBSERVABLE outcomes the survivors depend on, mirroring
tests/unit/test_scrub_dict_cursor.py in spirit. They PASS against current code —
their proof is RED-vs-MUTANTS: with them landed, bin/mutate on spool.py kills the
listed survivors.

Survivor groups covered (A-H):
    A _safe_task_slug      — path-segment hardening (security)
    B _validated_spool_path — traversal/escape rejection (security)
    C write_result         — input + writability rejections
    D clean_expired        — TTL semantics + default ttl_days
    E export_since         — date-prefix include/exclude filter
    F _extract_task_name   — both parse branches (NB: see note below)
    G list_pending         — entry fields + newest-first ordering
    H SpoolConfig          — tenant-scoped default dir STRING (never created)

NB (group F): the docstring example in spool.py implies a 17-char timestamp
prefix (``...T031400-name``) is stripped, but the real code tests ``parts[16] ==
"-"`` — the separator after a 17-char prefix sits at index 17, so a 17-char
prefix actually returns AS-IS. Only a 16-char prefix trips the slice branch.
These tests pin the ACTUAL current behavior of both branches (per the hard
constraint that they pass against current source), not the misleading example.
"""

import hashlib
import os
import re
import time
from pathlib import Path

import pytest

import rondo.spool as spool_mod
from rondo.spool import (
    SpoolConfig,
    SpoolManager,
    _extract_task_name,
    _safe_task_slug,
    _validated_spool_path,
)

# -- ──────────────────────────────────────────────────────────────
# --  A. _safe_task_slug — builds filesystem path segments (SECURITY)
# -- ──────────────────────────────────────────────────────────────


class TestSafeTaskSlug:
    """_safe_task_slug must never emit empty, traversing, or separator-bearing slugs."""

    @pytest.mark.parametrize("raw", ["", "   ", "\t\n  "])
    def test_empty_or_whitespace_returns_unnamed(self, raw: str) -> None:
        """Blank/whitespace task names collapse to the literal 'unnamed' sentinel."""
        # -- kills the return-None mutant on the empty branch.
        assert _safe_task_slug(raw) == "unnamed"

    @pytest.mark.parametrize("raw", ["///", "...", "..", "/", "._-"])
    def test_all_junk_falls_back_to_sha256_slug(self, raw: str) -> None:
        """All-separator/dot input yields a stable 'task_<12-hex>' digest slug."""
        result = _safe_task_slug(raw)
        # -- exact digest pins prefix, hashing input, and the [:12] slice length.
        expected = "task_" + hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()[:12]
        assert result == expected
        assert re.fullmatch(r"task_[0-9a-f]{12}", result), result

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("../../etc/passwd", "etc_passwd"),
            ("a/b\\c", "a_b_c"),
            ("a\x00b", "ab"),
            ("..\\..\\windows", "windows"),
        ],
    )
    def test_traversal_and_separators_sanitized(self, raw: str, expected: str) -> None:
        """Traversal, slashes, backslashes, and NULs are stripped from the slug."""
        result = _safe_task_slug(raw)
        assert result == expected
        # -- defense-in-depth: no escape primitive survives into a path segment.
        assert "/" not in result
        assert "\\" not in result
        assert ".." not in result
        assert "\x00" not in result

    def test_length_capped_at_120(self) -> None:
        """An over-long all-valid name is truncated to exactly _MAX_TASK_SLUG_LEN (120)."""
        result = _safe_task_slug("a" * 200)
        # -- exact length+content kills off-by-one mutants on the slice bound.
        assert result == "a" * 120
        assert len(result) == 120


# -- ──────────────────────────────────────────────────────────────
# --  B. _validated_spool_path — reject escapes (SECURITY)
# -- ──────────────────────────────────────────────────────────────


class TestValidatedSpoolPath:
    """_validated_spool_path must reject anything but a bare in-dir filename."""

    @pytest.mark.parametrize(
        "filename",
        ["sub/file.json", "/etc/passwd", "..", "../x.json", "a/../b.json", ""],
    )
    def test_non_bare_or_parent_rejected(self, filename: str, tmp_path: Path) -> None:
        """Non-bare names, absolute paths, and '..' segments resolve to None."""
        # -- kills the return-candidate mutants on every rejection branch.
        assert _validated_spool_path(tmp_path, filename) is None

    def test_legit_existing_file_resolved(self, tmp_path: Path) -> None:
        """A bare filename for an existing file returns its resolved Path."""
        target = tmp_path / "2026-06-10T101010-ok.json"
        target.write_text("{}", encoding="utf-8")
        result = _validated_spool_path(tmp_path, "2026-06-10T101010-ok.json")
        # -- kills the "always None" mutant on the success path.
        assert result == target.resolve()
        assert result is not None and result.is_file()

    def test_bare_but_missing_file_returns_none(self, tmp_path: Path) -> None:
        """A valid bare name with no file on disk still returns None (is_file gate)."""
        assert _validated_spool_path(tmp_path, "nope.json") is None

    def test_existing_nested_file_still_rejected(self, tmp_path: Path) -> None:
        """A non-bare name is rejected even when the nested file genuinely exists.

        This is the case where the bare-filename guard must hold: if the boolop
        degraded from `or` to `and`, the resolvable existing nested file would
        leak back as a Path instead of None.
        """
        nested = tmp_path / "sub"
        nested.mkdir()
        (nested / "file.json").write_text("{}", encoding="utf-8")
        assert _validated_spool_path(tmp_path, "sub/file.json") is None


# -- ──────────────────────────────────────────────────────────────
# --  C. SpoolManager.write_result — input + writability rejections
# -- ──────────────────────────────────────────────────────────────


class TestWriteResultRejections:
    """write_result must return None (never raise, never write) on bad inputs."""

    def test_non_dict_result_rejected(self, tmp_path: Path) -> None:
        """A non-dict result is rejected with None and nothing is spooled."""
        mgr = SpoolManager(config=SpoolConfig(spool_dir=str(tmp_path)))
        assert mgr.write_result(task_name="ok", result=["not", "a", "dict"]) is None  # type: ignore[arg-type]
        assert list(tmp_path.glob("*.json")) == []

    @pytest.mark.parametrize("task_name", ["", "   ", "\t"])
    def test_empty_task_name_rejected(self, task_name: str, tmp_path: Path) -> None:
        """Empty/whitespace task_name is rejected with None and no file written."""
        mgr = SpoolManager(config=SpoolConfig(spool_dir=str(tmp_path)))
        assert mgr.write_result(task_name=task_name, result={"k": "v"}) is None
        assert list(tmp_path.glob("*.json")) == []

    def test_unwritable_dir_rejected(self, tmp_path: Path) -> None:
        """A spool_dir that points at a FILE makes _ensure_dir fail -> None."""
        blocker = tmp_path / "iam-a-file"
        blocker.write_text("x", encoding="utf-8")
        mgr = SpoolManager(config=SpoolConfig(spool_dir=str(blocker)))
        # -- mkdir over a regular file raises OSError -> _ensure_dir False -> None.
        assert mgr.write_result(task_name="ok", result={"k": "v"}) is None

    def test_ensure_dir_returns_false_when_dir_is_a_file(self, tmp_path: Path) -> None:
        """_ensure_dir reports False (not None/True) when the path is a file.

        Pins the exact False return on the OSError branch so a mutant flipping it
        to True/None — which would let write_result proceed past the guard — dies.
        """
        blocker = tmp_path / "regular-file"
        blocker.write_text("x", encoding="utf-8")
        mgr = SpoolManager(config=SpoolConfig(spool_dir=str(blocker)))
        assert mgr._ensure_dir() is False

    def test_valid_write_returns_path(self, tmp_path: Path) -> None:
        """Sanity anchor: a valid dict + name DOES produce a real spool file."""
        mgr = SpoolManager(config=SpoolConfig(spool_dir=str(tmp_path)))
        out = mgr.write_result(task_name="code-review", result={"k": "v"})
        assert out is not None and out.is_file()


# -- ──────────────────────────────────────────────────────────────
# --  D. clean_expired — TTL semantics + default ttl_days
# -- ──────────────────────────────────────────────────────────────


class TestCleanExpired:
    """clean_expired must drop files older than ttl_days and keep younger ones."""

    def test_ttl_boundary_old_removed_at_cutoff_and_fresh_kept(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """With time frozen, only the strictly-older file is removed.

        Three files straddle the cutoff so every cutoff-math mutant dies:
          * old  = cutoff - 1s  -> removed (a +1 to the 86400 literal would keep it;
                                   flipping the cutoff subtraction to + would remove all)
          * edge = cutoff       -> KEPT under strict `<` (a `<` -> `<=` flip removes it)
          * fresh = cutoff + 100 -> always kept
        """
        # -- freeze the clock so the cutoff is exact and integer-valued.
        frozen = 1_000_000_000.0
        monkeypatch.setattr(spool_mod.time, "time", lambda: frozen)
        cutoff = frozen - 7 * 86400  # -- 999395200.0, exactly representable

        mgr = SpoolManager(config=SpoolConfig(spool_dir=str(tmp_path), ttl_days=7))
        old = tmp_path / "2026-01-01T000000-old.json"
        edge = tmp_path / "2026-02-02T020202-edge.json"
        fresh = tmp_path / "2026-06-10T101010-fresh.json"
        for f in (old, edge, fresh):
            f.write_text("{}", encoding="utf-8")
        os.utime(old, (cutoff - 1, cutoff - 1))
        os.utime(edge, (cutoff, cutoff))
        os.utime(fresh, (cutoff + 100, cutoff + 100))

        removed = mgr.clean_expired()
        # -- exact count AND survivor identities (kills arith/int-literal/compare).
        assert removed == 1
        assert not old.exists()
        assert edge.exists()
        assert fresh.exists()

    def test_default_ttl_is_seven_days(self) -> None:
        """SpoolConfig defaults ttl_days to 7 (the cutoff multiplier)."""
        assert SpoolConfig(spool_dir="/tmp/never-created").ttl_days == 7

    def test_missing_dir_returns_zero(self, tmp_path: Path) -> None:
        """clean_expired on a non-existent spool dir returns 0, not an error."""
        mgr = SpoolManager(config=SpoolConfig(spool_dir=str(tmp_path / "ghost")))
        assert mgr.clean_expired() == 0


# -- ──────────────────────────────────────────────────────────────
# --  E. export_since — filename date-prefix include/exclude filter
# -- ──────────────────────────────────────────────────────────────


class TestExportSince:
    """export_since includes files whose date prefix >= since_date, excludes older."""

    def test_date_prefix_includes_exact_and_excludes_older(self, tmp_path: Path) -> None:
        """Newer + exact-date files are returned; older is dropped.

        The exact-date file (prefix == since_date) MUST be included, which pins
        the `>=` comparison: a `>=` -> `>` mutant would wrongly drop it.
        """
        recent = tmp_path / "2026-03-20T031400-recent.json"
        edge = tmp_path / "2026-03-01T000000-edge.json"  # -- prefix == since_date
        stale = tmp_path / "2026-01-01T000000-stale.json"
        recent.write_text('{"v": 1}', encoding="utf-8")
        edge.write_text('{"v": 9}', encoding="utf-8")
        stale.write_text('{"v": 2}', encoding="utf-8")

        mgr = SpoolManager(config=SpoolConfig(spool_dir=str(tmp_path)))
        out = mgr.export_since("2026-03-01")

        spool_files = {r["_spool_file"] for r in out}
        # -- both >= matches included (one strictly newer, one exactly equal).
        assert spool_files == {
            "2026-03-20T031400-recent.json",
            "2026-03-01T000000-edge.json",
        }
        # -- _spool_file annotation is attached and payload preserved.
        by_file = {r["_spool_file"]: r for r in out}
        assert by_file["2026-03-20T031400-recent.json"]["v"] == 1
        assert by_file["2026-03-01T000000-edge.json"]["v"] == 9
        assert "2026-01-01T000000-stale.json" not in spool_files

    def test_prefix_compared_at_exactly_ten_chars(self, tmp_path: Path) -> None:
        """Only the first 10 chars (the date) are compared, not 11.

        A since_date of "2026-03-20T" must EXCLUDE a same-day file, because
        fname[:10] == "2026-03-20" < "2026-03-20T". Were the slice [:11], the
        file's "2026-03-20T" would compare equal and wrongly include it.
        """
        sameday = tmp_path / "2026-03-20T031400-x.json"
        sameday.write_text('{"v": 1}', encoding="utf-8")
        mgr = SpoolManager(config=SpoolConfig(spool_dir=str(tmp_path)))
        assert mgr.export_since("2026-03-20T") == []

    def test_missing_dir_returns_empty(self, tmp_path: Path) -> None:
        """export_since on a non-existent spool dir returns [], not None/error."""
        mgr = SpoolManager(config=SpoolConfig(spool_dir=str(tmp_path / "ghost")))
        assert mgr.export_since("2026-01-01") == []


# -- ──────────────────────────────────────────────────────────────
# --  F. _extract_task_name — both parse branches (actual behavior)
# -- ──────────────────────────────────────────────────────────────


class TestExtractTaskName:
    """_extract_task_name's slice branch vs as-is branch must both be pinned."""

    def test_sixteen_char_prefix_is_stripped(self) -> None:
        """A 16-char prefix puts '-' at index 16 -> the suffix is returned."""
        # -- this is the ONLY shape that trips `parts[16] == "-"` -> parts[17:].
        assert _extract_task_name("2026-03-20T03140-code-review.json") == "code-review"

    def test_seventeen_char_prefix_returned_as_is(self) -> None:
        """Real write_result names (17-char prefix) hit the as-is branch unchanged."""
        # -- documents the genuine off-by-one: separator is at index 17, not 16.
        assert _extract_task_name("2026-03-20T031400-code-review.json") == "2026-03-20T031400-code-review"

    @pytest.mark.parametrize(("filename", "expected"), [("short.json", "short"), ("abc.json", "abc")])
    def test_short_name_returned_as_is(self, filename: str, expected: str) -> None:
        """A short name (no 17-char prefix) returns its stem via the else branch."""
        assert _extract_task_name(filename) == expected

    def test_only_last_json_suffix_stripped(self) -> None:
        """Only ONE trailing '.json' is stripped (maxsplit=1), inner ones kept.

        Pins the maxsplit literal: a bump to 2 would over-split 'x.json.json'
        down to 'x' instead of the correct 'x.json'.
        """
        assert _extract_task_name("x.json.json") == "x.json"

    def test_exactly_seventeen_char_stem_uses_as_is_branch(self) -> None:
        """A stem of length exactly 17 takes the else branch (len > 17 is strict).

        '2026-03-20T03140-' has a '-' at index 16, so a `> 17` -> `>= 17` mutant
        would slice parts[17:] (empty string); strict `>` returns the stem intact.
        """
        assert _extract_task_name("2026-03-20T03140-.json") == "2026-03-20T03140-"


# -- ──────────────────────────────────────────────────────────────
# --  G. list_pending — entry fields + newest-first ordering
# -- ──────────────────────────────────────────────────────────────


class TestListPending:
    """list_pending must report sane per-file fields, newest first."""

    def test_entry_fields_and_newest_first(self, tmp_path: Path) -> None:
        """Each entry carries filename/task_name/age_sec/size_bytes/path, newest first."""
        newer = tmp_path / "2026-06-10T101010-newtask.json"
        older = tmp_path / "2026-06-09T101010-oldtask.json"
        newer.write_text('{"a": 1}', encoding="utf-8")
        older.write_text('{"bb": 22}', encoding="utf-8")

        now = time.time()
        os.utime(newer, (now, now))
        os.utime(older, (now - 5000, now - 5000))

        mgr = SpoolManager(config=SpoolConfig(spool_dir=str(tmp_path)))
        entries = mgr.list_pending()

        assert len(entries) == 2
        # -- newest first (kills the reverse= ordering mutant).
        assert entries[0]["filename"] == "2026-06-10T101010-newtask.json"
        assert entries[1]["filename"] == "2026-06-09T101010-oldtask.json"

        first = entries[0]
        # -- every field is present and meaningful (kills the field-drop mutants).
        assert set(first) == {"filename", "age_sec", "size_bytes", "task_name", "path"}
        assert first["task_name"] == _extract_task_name("2026-06-10T101010-newtask.json")
        assert first["size_bytes"] == len(b'{"a": 1}')
        assert first["path"] == str(newer)
        # -- fresh file age is a small positive number, NOT ~2*now (kills now + mtime).
        assert 0 <= first["age_sec"] < 120

        # -- age_sec tracks os.utime aging within a tight window (kills now + mtime).
        aged = entries[1]
        assert aged["size_bytes"] == len(b'{"bb": 22}')
        assert 4900 < aged["age_sec"] < 5100

    def test_missing_dir_returns_empty(self, tmp_path: Path) -> None:
        """list_pending on a non-existent spool dir returns [] rather than erroring."""
        mgr = SpoolManager(config=SpoolConfig(spool_dir=str(tmp_path / "ghost")))
        assert mgr.list_pending() == []


# -- ──────────────────────────────────────────────────────────────
# --  H. SpoolConfig default — tenant-scoped dir STRING (never created)
# -- ──────────────────────────────────────────────────────────────


class TestDefaultConfigShape:
    """SpoolConfig() with no spool_dir resolves to the tenant-scoped default string."""

    def test_default_spool_dir_is_tenant_scoped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """An empty spool_dir coalesces to ~/.rondo/spool/<tenant> (string only)."""
        monkeypatch.setenv("RONDO_TENANT", "cursortenant")
        # -- inspect the STRING only; never touch ~/.rondo on disk.
        cfg = SpoolConfig()
        assert cfg.spool_dir == "~/.rondo/spool/cursortenant"
        assert cfg.spool_dir.endswith(".rondo/spool/cursortenant")


# -- sig: mgh-6201.cd.bd955f.0b4d.692874
