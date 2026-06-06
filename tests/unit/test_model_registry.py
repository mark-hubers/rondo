# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Tests for rondo.model_registry — REQ-111 reqs 600-603 (RONDO-305).

Driver: the hand-run drift check (2026-06-05) found xAI had RETIRED the
entire grok-3 family — all three configured tiers would 404 — and nobody
knew. This module is that check as a real, daily-runnable tool.
Fetcher is injected: tests never touch the network.

VER-001 verification matrix: registry refresh, drift states, alias-first.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

from rondo.model_registry import (
    drift_report,
    format_drift_table,
    load_cache,
    refresh_registry,
)

NOW = datetime(2026, 6, 5, 12, 0, tzinfo=UTC)

PROVIDERS_CFG = {
    "grok": {"enabled": True, "cheap_model": "grok-3-mini", "default_model": "grok-3", "best_model": "grok-3"},
    "mistral": {"enabled": True, "best_model": "mistral-large-latest"},
    "off": {"enabled": False, "best_model": "x"},
}


def _fake_fetcher(provider: str, cfg: dict, api_key: str) -> list[str]:
    """Injected fetcher — grok serves only 4.3-era models now."""
    served = {
        "grok": ["grok-4.3", "grok-build-0.1"],
        "mistral": ["mistral-large-latest", "mistral-small-latest"],
    }
    if provider not in served:
        raise OSError(f"no such provider endpoint: {provider}")
    return served[provider]


def _fake_keys(provider: str) -> str:
    return "test-key"


class TestRefresh:
    """REQ-111 req 600: refresh caches per-provider model lists."""

    def test_refresh_writes_cache(self, tmp_path: Path) -> None:
        cache_path = tmp_path / "models-cache.json"
        cache = refresh_registry(
            PROVIDERS_CFG, key_loader=_fake_keys, fetcher=_fake_fetcher, cache_path=str(cache_path), now=NOW
        )
        assert "grok-4.3" in cache["providers"]["grok"]["models"]
        assert cache_path.exists()
        on_disk = json.loads(cache_path.read_text(encoding="utf-8"))
        assert on_disk["providers"]["mistral"]["models"] == ["mistral-large-latest", "mistral-small-latest"]

    def test_disabled_provider_skipped(self, tmp_path: Path) -> None:
        cache = refresh_registry(
            PROVIDERS_CFG, key_loader=_fake_keys, fetcher=_fake_fetcher, cache_path=str(tmp_path / "c.json"), now=NOW
        )
        assert "off" not in cache["providers"]

    def test_fetch_failure_is_non_fatal(self, tmp_path: Path) -> None:
        """REQ-111 req 600: one provider down never aborts the refresh."""
        cfg = dict(PROVIDERS_CFG)
        cfg["broken"] = {"enabled": True, "best_model": "m"}
        cache = refresh_registry(
            cfg, key_loader=_fake_keys, fetcher=_fake_fetcher, cache_path=str(tmp_path / "c.json"), now=NOW
        )
        assert cache["providers"]["broken"]["error"]
        assert "grok-4.3" in cache["providers"]["grok"]["models"]

    def test_load_cache_roundtrip(self, tmp_path: Path) -> None:
        cache_path = tmp_path / "c.json"
        refresh_registry(
            PROVIDERS_CFG, key_loader=_fake_keys, fetcher=_fake_fetcher, cache_path=str(cache_path), now=NOW
        )
        loaded = load_cache(str(cache_path))
        assert loaded is not None
        assert "grok" in loaded["providers"]

    def test_load_cache_missing_returns_none(self, tmp_path: Path) -> None:
        assert load_cache(str(tmp_path / "nope.json")) is None


class TestDrift:
    """REQ-111 reqs 602-603: OK / STALE / NEW + alias-first flagging."""

    def _cache(self, tmp_path: Path) -> dict:
        return refresh_registry(
            PROVIDERS_CFG, key_loader=_fake_keys, fetcher=_fake_fetcher, cache_path=str(tmp_path / "c.json"), now=NOW
        )

    def test_stale_models_flagged(self, tmp_path: Path) -> None:
        """The dead-grok scenario: configured tier no longer served → STALE."""
        entries = drift_report(self._cache(tmp_path), PROVIDERS_CFG)
        grok_states = {e["tier"]: e["state"] for e in entries if e["provider"] == "grok"}
        assert grok_states["cheap_model"] == "STALE"
        assert grok_states["best_model"] == "STALE"

    def test_served_models_ok(self, tmp_path: Path) -> None:
        entries = drift_report(self._cache(tmp_path), PROVIDERS_CFG)
        mistral = [e for e in entries if e["provider"] == "mistral" and e["tier"] == "best_model"]
        assert mistral[0]["state"] == "OK"

    def test_new_models_surfaced(self, tmp_path: Path) -> None:
        """REQ-111 req 602: unconfigured served models surface as NEW."""
        entries = drift_report(self._cache(tmp_path), PROVIDERS_CFG)
        new = [e for e in entries if e["provider"] == "grok" and e["state"] == "NEW"]
        assert any("grok-4.3" in e["model"] for e in new)

    def test_no_cache_for_provider(self, tmp_path: Path) -> None:
        """Provider with a fetch error reports NO_CACHE, never fake-OK."""
        cfg = dict(PROVIDERS_CFG)
        cfg["broken"] = {"enabled": True, "best_model": "m"}
        cache = refresh_registry(
            cfg, key_loader=_fake_keys, fetcher=_fake_fetcher, cache_path=str(tmp_path / "c.json"), now=NOW
        )
        entries = drift_report(cache, cfg)
        broken = [e for e in entries if e["provider"] == "broken"]
        assert broken[0]["state"] == "NO_CACHE"

    def test_format_table_contains_states(self, tmp_path: Path) -> None:
        """REQ-111 req 602: human-readable table for `rondo providers --drift`."""
        text = format_drift_table(drift_report(self._cache(tmp_path), PROVIDERS_CFG))
        assert "STALE" in text
        assert "OK" in text


# -- sig: mgh-6201.cd.bd955f.f1a8.mr305a


class TestDocsDrift:
    """REQ-111 req 611 (RONDO-325): stale model IDs in examples/docs.

    Driver: 78 stale IDs across 24 example files after a model refresh —
    stale docs teach users dead dispatches. Detection-only; never edits.
    """

    CACHE = {
        "providers": {
            "grok": {"models": ["grok-4.3"], "error": ""},
            "gemini": {"models": ["gemini-flash-latest", "gemini-pro-latest"], "error": ""},
        }
    }

    def _tree(self, tmp_path: Path) -> Path:
        root = tmp_path / "examples"
        root.mkdir()
        (root / "stale.sh").write_text("rondo review f.py --providers grok\n# uses grok:grok-3 here\n")
        (root / "fresh.yaml").write_text("model: grok:grok-4.3\nother: gemini:gemini-flash-latest\n")
        (root / "history.md").write_text("grok-3 family RETIRED (now grok-4.3) — historical note\n")
        return root

    def test_stale_id_flagged_with_location(self, tmp_path: Path) -> None:
        from rondo.model_registry import docs_drift

        hits = docs_drift(self.CACHE, [str(self._tree(tmp_path))])
        assert any(h["model"] == "grok-3" and "stale.sh" in h["file"] for h in hits)
        assert all(h["line"] > 0 for h in hits)

    def test_served_ids_not_flagged(self, tmp_path: Path) -> None:
        from rondo.model_registry import docs_drift

        hits = docs_drift(self.CACHE, [str(self._tree(tmp_path))])
        assert not any(h["model"] in ("grok-4.3", "gemini-flash-latest") for h in hits)

    def test_historical_narrative_skipped(self, tmp_path: Path) -> None:
        """The grok-3-RETIRED note is history, not guidance — never flagged.

        (Night-shift gotcha: historical narrative must survive model sweeps.)
        """
        from rondo.model_registry import docs_drift

        hits = docs_drift(self.CACHE, [str(self._tree(tmp_path))])
        assert not any("history.md" in h["file"] for h in hits)

    def test_undated_alias_of_dated_snapshot_not_flagged(self, tmp_path: Path) -> None:
        """Live canary 2026-06-06: claude-haiku-4-5 dispatches fine but
        /v1/models lists only claude-haiku-4-5-20251001. DATE-suffix-only
        tolerance — gpt-4 must never hide behind gpt-4-turbo siblings.
        """
        from rondo.model_registry import docs_drift

        cache = {"providers": {"anthropic": {"models": ["claude-haiku-4-5-20251001"], "error": ""}}}
        root = tmp_path / "docs"
        root.mkdir()
        (root / "ok.md").write_text("use anthropic:claude-haiku-4-5 for cheap tasks\n")
        (root / "bad.md").write_text("use anthropic:claude-haiku-3-5 maybe\n")
        hits = docs_drift(cache, [str(root)])
        assert not any(h["model"] == "claude-haiku-4-5" for h in hits)  # -- dated alias OK
        assert any(h["model"] == "claude-haiku-3-5" for h in hits)  # -- truly gone

    def test_no_cache_provider_not_scanned(self, tmp_path: Path) -> None:
        """A provider with a failed fetch proves nothing about its docs."""
        from rondo.model_registry import docs_drift

        cache = {"providers": {"grok": {"models": [], "error": "HTTP 500"}}}
        hits = docs_drift(cache, [str(self._tree(tmp_path))])
        assert hits == []

    def test_missing_dir_is_empty_not_crash(self, tmp_path: Path) -> None:
        from rondo.model_registry import docs_drift

        assert docs_drift(self.CACHE, [str(tmp_path / "nope")]) == []


# -- sig: mgh-6201.cd.bd955f.d5e0.1c1548
