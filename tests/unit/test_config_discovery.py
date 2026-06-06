# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Config discovery — RONDO-331 (SOP-105 P1-2: cross-platform config).

VER-001 verification matrix: XDG-aware config resolution with legacy honor.

Strangers on Linux/Windows expect XDG paths; ~/.rondo stays honored as
legacy forever (Mark's machine never changes behavior). First existing
file wins: $RONDO_CONFIG → $XDG_CONFIG_HOME/rondo/ → ~/.config/rondo/ →
~/.rondo/ (legacy).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from rondo.config import discover_config_path


@pytest.fixture
def fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("RONDO_CONFIG", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    return tmp_path


def _mk(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("[providers.gemini]\nenabled = false\n")
    return path


class TestDiscoveryChain:
    """First existing file wins; chain documented in the docstring."""

    def test_rondo_config_env_wins(self, fake_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        explicit = _mk(fake_home / "custom" / "my.toml")
        _mk(fake_home / ".config" / "rondo" / "config.toml")
        _mk(fake_home / ".rondo" / "config.toml")
        monkeypatch.setenv("RONDO_CONFIG", str(explicit))
        assert discover_config_path() == explicit

    def test_xdg_config_home_respected(self, fake_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        xdg = _mk(fake_home / "xdg-custom" / "rondo" / "config.toml")
        _mk(fake_home / ".rondo" / "config.toml")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(fake_home / "xdg-custom"))
        assert discover_config_path() == xdg

    def test_default_xdg_dir_when_no_env(self, fake_home: Path) -> None:
        xdg = _mk(fake_home / ".config" / "rondo" / "config.toml")
        _mk(fake_home / ".rondo" / "config.toml")
        assert discover_config_path() == xdg

    def test_legacy_rondo_dir_honored(self, fake_home: Path) -> None:
        """Mark's machine: only ~/.rondo exists → behavior unchanged forever."""
        legacy = _mk(fake_home / ".rondo" / "config.toml")
        assert discover_config_path() == legacy

    def test_none_found_returns_legacy_default(self, fake_home: Path) -> None:
        """No config anywhere → the legacy path (callers handle absence)."""
        assert discover_config_path() == fake_home / ".rondo" / "config.toml"

    def test_env_pointing_at_missing_file_falls_through(self, fake_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """A broken $RONDO_CONFIG never strands the user — chain continues."""
        monkeypatch.setenv("RONDO_CONFIG", str(fake_home / "nope.toml"))
        legacy = _mk(fake_home / ".rondo" / "config.toml")
        assert discover_config_path() == legacy


# -- sig: mgh-6201.cd.bd955f.3fa2.4efa75
