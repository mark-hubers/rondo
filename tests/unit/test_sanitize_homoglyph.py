# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
r"""Homoglyph defense tests for sanitize_text — RONDO-292 (Finding #249).

VER-001: Product acceptance / unit test coverage.

Finding #249: sanitize.py had no Unicode NFKC normalization, so an LLM
echoing a Cyrillic-disguised API key would bypass the regex patterns that
use Latin characters. RONDO-292 adds NFKC normalization before scanning.

Attack vector example:
    text = "аpi_key = 'SECRET'"    # Cyrillic 'а' (U+0430)
    Regex: r"(?i)api[_-]?key\\s*=\\s*..."  expects Latin 'a' (U+0061)
    Without NFKC: secret passes through unscrubbed.
    With NFKC: "а" -> "a", regex matches, secret redacted.

These tests verify:
    1. Cyrillic homoglyph API keys are caught after NFKC
    2. Full-width ASCII (U+FF21-U+FF5A) is caught after NFKC
    3. Mixed-script bypass attempts are caught
    4. Latin-only text (clean input) still works unchanged
    5. Opt-out via normalize_unicode=False preserves old behavior
"""

from __future__ import annotations

from pathlib import Path

from rondo.sanitize import SanitizeConfig, sanitize_text


class TestHomoglyphDefense:
    """NFKC normalization catches homoglyph-disguised secrets."""

    def test_cyrillic_a_in_api_key_is_normalized_and_caught(self) -> None:
        ## Cyrillic 'а' (U+0430) replacing Latin 'a' (U+0061)
        text = "\u0430pi_key = 'sk-FAKE-TEST-VALUE-NOT-REAL'"  # gitleaks:allow
        result = sanitize_text(text)
        assert result.secrets_found >= 1, f"Homoglyph API key NOT caught: detections={result.detections}"
        assert "sk-FAKE-TEST" not in result.sanitized_text
        assert "[REDACTED" in result.sanitized_text

    def test_cyrillic_a_in_password_is_normalized_and_caught(self) -> None:
        ## Cyrillic 'а' replacing Latin 'a' in "password"
        text = "p\u0430ssword = 'FAKE-TEST-PW-NOT-REAL'"  # gitleaks:allow
        result = sanitize_text(text)
        assert result.secrets_found >= 1, f"Homoglyph password NOT caught: detections={result.detections}"

    def test_fullwidth_chars_normalized_and_caught(self) -> None:
        ## Full-width ASCII 'ａｐｉ_ｋｅｙ' (U+FF41 etc.) instead of 'api_key'
        text = "\uff41\uff50\uff49_\uff4b\uff45\uff59 = 'FAKE-TEST-VALUE-1234'"  # gitleaks:allow
        result = sanitize_text(text)
        assert result.secrets_found >= 1, f"Full-width homoglyph NOT caught: detections={result.detections}"

    def test_clean_latin_text_still_caught(self) -> None:
        ## Baseline — regular Latin still works
        text = "api_key = 'FAKE-TEST-CLEAN-1234567890'"  # gitleaks:allow
        result = sanitize_text(text)
        assert result.secrets_found >= 1
        assert "FAKE-TEST-CLEAN" not in result.sanitized_text

    def test_text_without_secrets_passes_through(self) -> None:
        ## Normalization of clean non-secret text must not flag anything
        text = "Hello, world! This is plain Latin text with no secrets."
        result = sanitize_text(text)
        assert result.secrets_found == 0
        assert result.sanitized_text == result.original_text

    def test_normalize_unicode_default_is_true(self) -> None:
        ## Defense in depth — default must be secure
        config = SanitizeConfig()
        assert config.normalize_unicode is True

    def test_normalize_unicode_can_be_disabled(self) -> None:
        ## With normalization off, the homoglyph bypass still works
        ## (documenting legacy behavior — DON'T disable in production)
        text = "\u0430pi_key = 'FAKE-TEST-DISGUISED-1234567890'"  # gitleaks:allow
        config = SanitizeConfig(normalize_unicode=False)
        result = sanitize_text(text, config=config)
        ## Old behavior — secret leaks through because regex can't match Cyrillic
        assert "FAKE-TEST-DISGUISED" in result.sanitized_text


class TestNormalizationDoesNotBreakExistingSanitization:
    """RONDO-292 regression guards — make sure we didn't break anything."""

    def test_env_vars_still_scrubbed_after_normalization(self) -> None:
        ## env var scrubbing still works under normalization
        text = "export AWS_SECRET_KEY=FAKE-TEST-AWS-VALUE-1234567890"  # gitleaks:allow
        result = sanitize_text(text)
        assert result.secrets_found >= 1
        assert "FAKE-TEST-AWS-VALUE" not in result.sanitized_text

    def test_home_paths_still_scrubbed(self) -> None:
        ## Home path scrubbing still works
        ## RONDO-341: derive from Path.home() — the scrubber targets the
        ## PRODUCING machine's home (Linux container home is /root, not /Users/...)
        home = str(Path.home())
        text = f"Reading {home}/.ssh/id_rsa for auth"
        result = sanitize_text(text)
        ## sanitized text should have home path replaced
        assert f"{home}/" not in result.sanitized_text

    def test_empty_string_still_handled(self) -> None:
        result = sanitize_text("")
        assert result.sanitized_text == ""
        assert result.secrets_found == 0

    def test_no_secrets_returns_unchanged_original(self) -> None:
        ## Clean text returns original unchanged (fast path)
        text = "Hello world, nothing to scrub here."
        result = sanitize_text(text)
        assert result.sanitized_text == text
        assert result.original_text == text


# -- sig: mgh-6201.cd.bd955f.d249.f2b249
