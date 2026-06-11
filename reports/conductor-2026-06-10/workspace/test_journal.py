"""Tests for journal.py — add/list/search, empty store, unicode. tmp_path-isolated."""

import importlib
import types

import pytest


def _make_journal(tmp_path) -> types.ModuleType:
    """Return a fresh journal module wired to a tmp_path journal file."""
    journal_file = str(tmp_path / "journal.jsonl")

    ## Load the real source but override JOURNAL_FILE so every function
    ## reads/writes the isolated tmp file instead of the live one.
    spec = importlib.util.spec_from_file_location(
        "journal_isolated",
        "/Users/markhubers/git/mhubers/rondo/reports/conductor-2026-06-10/workspace/journal.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.JOURNAL_FILE = journal_file
    return mod


## ── empty store ─────────────────────────────────────────────────────────────


def test_list_empty_store(tmp_path) -> None:
    """list_entries returns [] when journal file does not exist."""
    j = _make_journal(tmp_path)
    assert j.list_entries() == []


def test_search_empty_store(tmp_path) -> None:
    """search_entries returns [] when journal file does not exist."""
    j = _make_journal(tmp_path)
    assert j.search_entries("anything") == []


## ── add ─────────────────────────────────────────────────────────────────────


def test_add_creates_file(tmp_path) -> None:
    """add_entry creates the journal file when it does not exist."""
    j = _make_journal(tmp_path)
    j.add_entry("first entry")
    assert (tmp_path / "journal.jsonl").exists()


def test_add_single_entry(tmp_path) -> None:
    """add_entry writes one entry that list_entries can read back."""
    j = _make_journal(tmp_path)
    j.add_entry("hello world")
    entries = j.list_entries()
    assert len(entries) == 1
    assert entries[0] == {"text": "hello world"}


def test_add_multiple_entries(tmp_path) -> None:
    """add_entry appends; list_entries returns all in insertion order."""
    j = _make_journal(tmp_path)
    j.add_entry("alpha")
    j.add_entry("beta")
    j.add_entry("gamma")
    entries = j.list_entries()
    assert len(entries) == 3
    assert [e["text"] for e in entries] == ["alpha", "beta", "gamma"]


## ── list ─────────────────────────────────────────────────────────────────────


def test_list_returns_dicts(tmp_path) -> None:
    """list_entries returns list of dicts with 'text' key."""
    j = _make_journal(tmp_path)
    j.add_entry("check type")
    entries = j.list_entries()
    assert isinstance(entries, list)
    assert all(isinstance(e, dict) for e in entries)
    assert all("text" in e for e in entries)


def test_list_idempotent(tmp_path) -> None:
    """list_entries called twice returns the same data."""
    j = _make_journal(tmp_path)
    j.add_entry("stable")
    assert j.list_entries() == j.list_entries()


## ── search ───────────────────────────────────────────────────────────────────


def test_search_finds_matching(tmp_path) -> None:
    """search_entries returns only entries containing the term."""
    j = _make_journal(tmp_path)
    j.add_entry("apple pie")
    j.add_entry("banana split")
    j.add_entry("apple cider")
    results = j.search_entries("apple")
    assert len(results) == 2
    assert all("apple" in e["text"] for e in results)


def test_search_case_insensitive(tmp_path) -> None:
    """search_entries is case-insensitive."""
    j = _make_journal(tmp_path)
    j.add_entry("Hello World")
    assert j.search_entries("hello") != []
    assert j.search_entries("WORLD") != []
    assert j.search_entries("HeLLo WoRLD") != []


def test_search_no_match(tmp_path) -> None:
    """search_entries returns [] when term is not found."""
    j = _make_journal(tmp_path)
    j.add_entry("cats and dogs")
    assert j.search_entries("fish") == []


def test_search_empty_term(tmp_path) -> None:
    """search_entries with '' matches every entry."""
    j = _make_journal(tmp_path)
    j.add_entry("one")
    j.add_entry("two")
    results = j.search_entries("")
    assert len(results) == 2


## ── edge cases ───────────────────────────────────────────────────────────────


def test_add_long_text_entry(tmp_path) -> None:
    """add_entry stores and retrieves a very long text string without truncation."""
    j = _make_journal(tmp_path)
    long_text = "x" * 10_000
    j.add_entry(long_text)
    entries = j.list_entries()
    assert len(entries) == 1
    assert entries[0]["text"] == long_text
    assert len(entries[0]["text"]) == 10_000


def test_add_duplicate_entries(tmp_path) -> None:
    """add_entry stores duplicate text as separate entries; list returns all."""
    j = _make_journal(tmp_path)
    j.add_entry("duplicate text")
    j.add_entry("duplicate text")
    j.add_entry("duplicate text")
    entries = j.list_entries()
    assert len(entries) == 3
    assert all(e["text"] == "duplicate text" for e in entries)


def test_search_no_match_populated_store(tmp_path) -> None:
    """search_entries returns [] when no entry matches and store is non-empty."""
    j = _make_journal(tmp_path)
    j.add_entry("alpha")
    j.add_entry("beta")
    j.add_entry("gamma")
    assert j.search_entries("zzz_no_match_zzz") == []


## ── unicode ──────────────────────────────────────────────────────────────────


def test_add_unicode_entry(tmp_path) -> None:
    """add_entry round-trips unicode text correctly."""
    j = _make_journal(tmp_path)
    text = "日本語テスト 🎉 café naïve résumé"
    j.add_entry(text)
    entries = j.list_entries()
    assert entries[0]["text"] == text


def test_search_unicode(tmp_path) -> None:
    """search_entries finds unicode terms."""
    j = _make_journal(tmp_path)
    j.add_entry("café au lait")
    j.add_entry("plain coffee")
    results = j.search_entries("café")
    assert len(results) == 1
    assert results[0]["text"] == "café au lait"


def test_unicode_emoji(tmp_path) -> None:
    """Emoji characters survive round-trip through add/list."""
    j = _make_journal(tmp_path)
    j.add_entry("🔥 fire entry 🔥")
    entries = j.list_entries()
    assert entries[0]["text"] == "🔥 fire entry 🔥"


def test_unicode_cjk_search(tmp_path) -> None:
    """CJK characters are searchable."""
    j = _make_journal(tmp_path)
    j.add_entry("日本語のエントリ")
    j.add_entry("英語のエントリ")
    results = j.search_entries("日本")
    assert len(results) == 1
    assert "日本" in results[0]["text"]
