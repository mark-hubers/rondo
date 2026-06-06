# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Public-build cut mechanism — RONDO-332 (SOP-105 P1-6).

VER-001 verification matrix: auth=max excluded from public distributions.

Mark's biggest stated share-risk is the Max-subscription subprocess
pattern. The mechanism: ONE flag (`rondo._build.PUBLIC_BUILD`) flipped by
release packaging; when True, auth=max refuses loudly with the api-key
alternative. Mark's tree ships False — his flow never changes.
"""

from __future__ import annotations

import pytest


class TestBuildFlag:
    """The flag exists, defaults False (Mark's tree), and is one constant."""

    def test_default_is_private_build(self) -> None:
        from rondo._build import PUBLIC_BUILD, is_public_build

        assert PUBLIC_BUILD is False
        assert is_public_build() is False


class TestAuthMaxGate:
    """Public builds refuse auth=max at config validation — before any dispatch."""

    def test_private_build_allows_max(self) -> None:
        from rondo.config import RondoConfig, validate_config

        errors = validate_config(RondoConfig(auth="max"))
        assert not any("auth" in e and "public" in e.lower() for e in errors)

    def test_public_build_refuses_max(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import rondo.config as _cfg
        from rondo.config import RondoConfig, validate_config

        monkeypatch.setattr(_cfg, "_is_public_build", lambda: True)
        errors = validate_config(RondoConfig(auth="max"))
        joined = " ".join(errors).lower()
        assert "auth" in joined and "not available" in joined
        assert "api" in joined  # -- the alternative is named, never a bare refusal

    def test_public_build_allows_api(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import rondo.config as _cfg
        from rondo.config import RondoConfig, validate_config

        monkeypatch.setattr(_cfg, "_is_public_build", lambda: True)
        errors = validate_config(RondoConfig(auth="api"))
        assert not any("not available" in e.lower() for e in errors)


class TestDispatchDefenseInDepth:
    """Even if validation is bypassed, the dispatch env-prep refuses max."""

    def test_prepare_env_refuses_max_in_public_build(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import rondo.dispatch as _d
        from rondo.config import RondoConfig

        monkeypatch.setattr(_d, "_is_public_build", lambda: True)
        from rondo.dispatch import prepare_env

        with pytest.raises(ValueError, match="not available"):
            prepare_env(RondoConfig(auth="max"))

    def test_prepare_env_max_works_in_private_build(self) -> None:
        from rondo.config import RondoConfig
        from rondo.dispatch import prepare_env

        env = prepare_env(RondoConfig(auth="max"))
        assert isinstance(env, dict)


# -- sig: mgh-6201.cd.bd955f.d6f4.9d3fe5
