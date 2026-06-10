# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Mutation-gate regression: entropy calc, extra_patterns gate, scrub return.

VER-001 verification matrix: high-entropy detection, custom-pattern gating,
and sanitized-output propagation in src/rondo/sanitize.py.

Quality-checklist item 19 (mutation gate): after the pyc-staleness fix the
honest score on sanitize.py was 28/36. Three clusters of survivors remained —
tests passed while the code was wrong:

  A. ``_shannon_entropy`` (~lines 274-282) — the empty-input guard, the
     frequency tally (``freq.get(c, 0) + 1``) and the entropy formula return
     were never asserted. The function is the kernel of the high-entropy secret
     story; if it silently returned ``None`` / garbage, high-entropy tokens
     would stop ranking as suspicious and nothing would catch it.
  B. ``_build_patterns`` (~line 293, ``config and config.extra_patterns``) —
     the boolean short-circuit was never pinned, so ``and`` -> ``or`` survived
     (it only crashes on the ``config is None`` path, which the public
     ``sanitize_text`` never reaches because it substitutes a default config).
  C. ``_scrub_home_paths`` (~line 352, ``return sanitized``) — the early-return
     guard taken when ``_HOME_DIR`` is empty was never exercised, so the
     return-None mutant survived; the propagated output was never asserted.

These tests assert OBSERVABLE behaviour so each listed mutant now FAILS, while
passing against the current (correct) code.

Credentials policy: only gitleaks-allowlisted example values. The bare AWS key
AKIAIOSFODNN7EXAMPLE is the proven-safe fixture already used across tests/. The
custom marker (``MYSECRET-####``) and high-entropy blob are built from neutral
literals / stdlib alphabets, so no real-looking secret ever lands in source.
"""

import string

from rondo.sanitize import (
    DEFAULT_PATTERNS,
    SanitizeConfig,
    _build_patterns,
    _shannon_entropy,
    sanitize_text,
)

# -- Canonical AWS example key (AKIA + 16 upper/digit chars). Matches the
# -- aws_access_key pattern and is allowlisted by the repo's gitleaks hook
# -- (reused verbatim from tests/unit/test_sanitize.py).
AWS_EXAMPLE_KEY = "AKIAIOSFODNN7EXAMPLE"


# ──────────────────────────────────────────────────────────────────
#  A — _shannon_entropy: empty guard, frequency tally, formula return
# ──────────────────────────────────────────────────────────────────


class TestShannonEntropy:
    """Pin _shannon_entropy so the empty-guard, tally and formula mutants die."""

    def test_empty_input_is_zero(self) -> None:
        """Empty string has zero entropy — kills the ``return 0.0`` guard mutant."""
        # -- mutant `return 0.0 -> return None`: None != 0.0 -> caught.
        assert _shannon_entropy("") == 0.0

    def test_single_distinct_char_is_zero(self) -> None:
        """One distinct char (any repeat count) has zero entropy — kills tally mutants."""
        # -- A correct tally gives count/length == 1.0 -> log2(1) == 0 -> entropy 0.0.
        # -- mutant `freq.get(c, 0)` -> `freq.get(c, 1)`  : count inflates -> nonzero.
        # -- mutant `... + 1` -> `... + 2`                : count inflates -> nonzero.
        # -- mutant `... + 1` -> `... - 1`                : negative count -> log2 domain error.
        assert _shannon_entropy("a") == 0.0
        assert _shannon_entropy("aaaa") == 0.0
        assert _shannon_entropy("zzzzzzzz") == 0.0

    def test_entropy_increases_with_diversity(self) -> None:
        """More distinct chars => strictly higher entropy — kills the formula-return mutant."""
        # -- mutant `return -sum(...)` -> `return None`: None comparison raises -> caught.
        assert _shannon_entropy("abcd") > _shannon_entropy("aaaa")
        assert _shannon_entropy("abcdefgh") > _shannon_entropy("aaaaaaaa")

    def test_high_entropy_blob_redacted_plain_prose_untouched(self) -> None:
        """Observable detector: a long contiguous high-entropy token is redacted; prose is not."""
        # -- Built from stdlib alphabets so it is high-entropy (48 distinct chars)
        # -- yet obviously not a real secret to gitleaks. Quoted + 40+ base64
        # -- chars trips the high_entropy_base64 detector.
        blob = (string.ascii_uppercase + string.ascii_lowercase + string.digits)[:48]
        hot = sanitize_text(f'token = "{blob}"')
        assert blob not in hot.sanitized_text
        assert hot.secrets_found >= 1

        # -- A low-entropy plain-English line of similar length: the spaces break
        # -- any 40+ char contiguous run, so it is NOT flagged.
        prose = "the quick brown fox jumps over the lazy dog and then naps"
        cold = sanitize_text(prose)
        assert cold.secrets_found == 0
        assert cold.sanitized_text == prose

    def test_empty_string_does_not_crash_or_flag(self) -> None:
        """Empty input through the public API: no crash, nothing flagged."""
        result = sanitize_text("")
        assert result.secrets_found == 0
        assert result.sanitized_text == ""


# ──────────────────────────────────────────────────────────────────
#  B — _build_patterns: the `config and config.extra_patterns` gate
# ──────────────────────────────────────────────────────────────────


class TestExtraPatternsGate:
    """Pin both sides of the custom-pattern gate (line ~293)."""

    def test_none_config_short_circuits_to_defaults(self) -> None:
        """config=None returns exactly the defaults — kills the ``and`` -> ``or`` mutant."""
        # -- Real: `None and config.extra_patterns` short-circuits -> defaults.
        # -- Mutant `or`: `None or None.extra_patterns` -> AttributeError -> caught.
        # -- Also kills a `return patterns` -> `return None` mutant (None != list).
        assert _build_patterns(None) == DEFAULT_PATTERNS
        assert len(_build_patterns(None)) == len(DEFAULT_PATTERNS)

    def test_config_without_extra_patterns_adds_nothing(self) -> None:
        """A default config (empty extra_patterns) yields exactly the defaults."""
        assert _build_patterns(SanitizeConfig()) == DEFAULT_PATTERNS

    def test_config_with_extra_pattern_appends_it(self) -> None:
        """A custom extra pattern is appended on top of the defaults."""
        cfg = SanitizeConfig(extra_patterns=[{"name": "mysecret", "pattern": r"MYSECRET-\d{4}"}])
        built = _build_patterns(cfg)
        assert len(built) == len(DEFAULT_PATTERNS) + 1
        assert built[-1].name == "mysecret"

    def test_extra_pattern_redacts_only_when_configured(self) -> None:
        """The custom rule redacts matching text; config=None / no-extra leave it alone."""
        marker = "MYSECRET-4242"
        cfg = SanitizeConfig(extra_patterns=[{"name": "mysecret", "pattern": r"MYSECRET-\d{4}"}])

        on = sanitize_text(f"ref {marker} end", config=cfg)
        assert marker not in on.sanitized_text
        assert on.secrets_found >= 1

        # -- No extra_patterns: the marker is not a default secret -> untouched.
        off = sanitize_text(f"ref {marker} end", config=SanitizeConfig())
        assert marker in off.sanitized_text
        assert off.secrets_found == 0

        # -- config=None (default config under the hood): same, untouched.
        none_cfg = sanitize_text(f"ref {marker} end")
        assert marker in none_cfg.sanitized_text
        assert none_cfg.secrets_found == 0


# ──────────────────────────────────────────────────────────────────
#  C — _scrub_home_paths: the `return sanitized` propagation (line ~352)
# ──────────────────────────────────────────────────────────────────


class TestScrubHomePathsReturn:
    """Pin that _scrub_home_paths actually returns/propagates its output."""

    def test_empty_home_returns_input_unchanged(self, monkeypatch) -> None:
        """When _HOME_DIR is empty the guard returns the input verbatim — kills the early return-None mutant."""
        import rondo.sanitize as san

        # -- Force the `if not _HOME_DIR:` branch (never taken in a normal env,
        # -- which is exactly why its return mutant survived).
        monkeypatch.setattr(san, "_HOME_DIR", "")
        payload = "no secrets here, just plain text and a /tmp/path token"
        out = san._scrub_home_paths(payload)
        # -- mutant `return sanitized` -> `return None`: None != payload -> caught.
        assert out is not None
        assert out == payload

    def test_home_path_transformed_and_propagated(self, monkeypatch) -> None:
        """A home-dir path is rewritten to [PATH]/basename and propagated (not None)."""
        import rondo.sanitize as san

        monkeypatch.setattr(san, "_HOME_DIR", "/home/fakeuser")
        out = san._scrub_home_paths("reading /home/fakeuser/project/config.toml now")
        assert out is not None
        assert "/home/fakeuser/project" not in out
        assert "[PATH]" in out
        assert "config.toml" in out

    def test_credential_round_trips_through_sanitize_text(self) -> None:
        """A known credential comes back transformed (not None) through the full pipeline."""
        out = sanitize_text(f"deploy using {AWS_EXAMPLE_KEY} immediately")
        assert out.sanitized_text is not None
        assert AWS_EXAMPLE_KEY not in out.sanitized_text
        assert "[REDACTED:" in out.sanitized_text
        assert out.secrets_found >= 1


# -- sig: mgh-6201.cd.bd955f.7874.7bc60c
