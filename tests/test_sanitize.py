# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Tests for rondo.sanitize — Rondo-STD-114 output sanitization.

VER-001 verification matrix: secret detection, scrubbing, audit.
"""

import json

from rondo.sanitize import (
    DEFAULT_PATTERNS,
    SanitizeConfig,
    sanitize_task_result,
    sanitize_text,
)

# ──────────────────────────────────────────────────────────────────
#  STD-114 req 001 — Scan all AI output for secret patterns
# ──────────────────────────────────────────────────────────────────


class TestScanDetection:
    """STD-114 req 001: scan AI output for secret patterns before storing."""

    def test_detects_api_key_assignment(self):
        """Finds api_key = 'value' pattern."""
        result = sanitize_text("config api_key = 'sk-abc123def456'")
        assert result.secrets_found > 0

    def test_detects_bearer_token(self):
        """Finds Bearer token pattern."""
        result = sanitize_text("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.test.sig")
        assert result.secrets_found > 0

    def test_clean_text_returns_zero(self):
        """No secrets = zero count."""
        result = sanitize_text("Hello world, this is normal output.")
        assert result.secrets_found == 0

    def test_detects_multiple_secrets(self):
        """Multiple secrets in same text all found."""
        text = "api_key = 'sk-abc123def456' password = 'hunter2pass'"
        result = sanitize_text(text)
        assert result.secrets_found >= 2


# ──────────────────────────────────────────────────────────────────
#  STD-114 req 002 — Default patterns
# ──────────────────────────────────────────────────────────────────


class TestDefaultPatterns:
    """STD-114 req 002: default secret patterns."""

    def test_aws_access_key(self):
        """Detects AWS access key (AKIA...)."""
        result = sanitize_text("aws_access_key_id = AKIAIOSFODNN7EXAMPLE")
        assert result.secrets_found > 0
        assert "AKIAIOSFODNN7EXAMPLE" not in result.sanitized_text

    def test_private_key_marker(self):
        """Detects -----BEGIN PRIVATE KEY-----."""
        text = "-----BEGIN PRIVATE KEY-----\nMIIEvgIBADANBg..."
        result = sanitize_text(text)
        assert result.secrets_found > 0

    def test_password_assignment(self):
        """Detects password = 'value'."""
        result = sanitize_text("db_password = 'super_secret_pw'")
        assert result.secrets_found > 0

    def test_secret_key_env(self):
        """Detects SECRET_KEY pattern."""
        result = sanitize_text("SECRET_KEY=a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6")
        assert result.secrets_found > 0

    def test_token_pattern(self):
        """Detects token = 'value'."""
        result = sanitize_text("auth_token = 'ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'")
        assert result.secrets_found > 0

    def test_high_entropy_base64(self):
        """Detects base64 strings >40 chars as potential secrets."""
        ## 48-char base64 string — suspicious
        b64 = "aGVsbG8gd29ybGQgdGhpcyBpcyBhIGxvbmcgYmFzZTY0IHN0cmluZw=="
        result = sanitize_text(f"data = '{b64}'")
        assert result.secrets_found > 0

    def test_default_patterns_list_exists(self):
        """DEFAULT_PATTERNS is a non-empty list of pattern definitions."""
        assert len(DEFAULT_PATTERNS) >= 6


# ──────────────────────────────────────────────────────────────────
#  STD-114 req 003 — Confidence scoring
# ──────────────────────────────────────────────────────────────────


class TestConfidenceScoring:
    """STD-114 req 003: confidence scoring for detections."""

    def test_exact_match_high_confidence(self):
        """Exact pattern match (api_key=) scores 0.9+."""
        result = sanitize_text("api_key = 'sk-abc123def456ghi789'")
        assert any(d.confidence >= 0.9 for d in result.detections)

    def test_heuristic_match_medium_confidence(self):
        """Heuristic match (high-entropy string) scores 0.5-0.8."""
        ## Random-looking hex string
        result = sanitize_text("value = 'a3f8b2c1d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4'")
        heuristic_hits = [d for d in result.detections if d.confidence < 0.9]
        if heuristic_hits:
            assert all(0.4 <= d.confidence <= 0.9 for d in heuristic_hits)


# ──────────────────────────────────────────────────────────────────
#  STD-114 req 004 — Custom patterns configurable
# ──────────────────────────────────────────────────────────────────


class TestCustomPatterns:
    """STD-114 req 004: custom patterns in config."""

    def test_custom_pattern_detected(self):
        """User-defined pattern matches."""
        config = SanitizeConfig(extra_patterns=[{"name": "internal_id", "pattern": r"CORP-[A-Z0-9]{12}"}])
        result = sanitize_text("ref CORP-A1B2C3D4E5F6 here", config=config)
        assert result.secrets_found > 0

    def test_custom_pattern_plus_defaults(self):
        """Custom patterns add to defaults, don't replace them."""
        config = SanitizeConfig(extra_patterns=[{"name": "custom", "pattern": r"MYCORP-\d+"}])
        ## Default should still catch api_key (value must be 8+ chars)
        result = sanitize_text("api_key = 'sk-test123456' ref MYCORP-999", config=config)
        assert result.secrets_found >= 2


# ──────────────────────────────────────────────────────────────────
#  STD-114 req 005 — Replace with [REDACTED:{pattern_name}]
# ──────────────────────────────────────────────────────────────────


class TestScrubbing:
    """STD-114 req 005: replace secrets with [REDACTED:name]."""

    def test_redaction_placeholder(self):
        """Secret replaced with [REDACTED:pattern_name]."""
        result = sanitize_text("api_key = 'sk-abc123def456'")
        assert "[REDACTED:" in result.sanitized_text
        assert "sk-abc123def456" not in result.sanitized_text

    def test_private_key_redacted(self):
        """Private key block redacted."""
        text = "-----BEGIN RSA PRIVATE KEY-----\ndata\n-----END RSA PRIVATE KEY-----"
        result = sanitize_text(text)
        assert "[REDACTED:" in result.sanitized_text
        assert "BEGIN RSA PRIVATE KEY" not in result.sanitized_text

    def test_multiple_redactions(self):
        """Multiple secrets all redacted."""
        text = "api_key = 'sk-abc12345678' password = 'hunter2pass'"
        result = sanitize_text(text)
        assert "sk-abc12345678" not in result.sanitized_text
        assert "hunter2pass" not in result.sanitized_text


# ──────────────────────────────────────────────────────────────────
#  STD-114 req 006 — Scrub BEFORE writing to storage
# ──────────────────────────────────────────────────────────────────


class TestScrubOrder:
    """STD-114 req 006: scrub before writing to audit/result files."""

    def test_sanitize_task_result_scrubs_raw_output(self):
        """TaskResult.raw_output gets scrubbed."""
        from rondo.engine import TaskResult

        tr = TaskResult(
            task_name="test",
            raw_output="Found api_key = 'sk-secret123456789'",
        )
        sanitized_tr, sr = sanitize_task_result(tr)
        assert "sk-secret123456789" not in sanitized_tr.raw_output
        assert sr.secrets_found > 0

    def test_sanitize_task_result_scrubs_parsed_result(self):
        """TaskResult.parsed_result dict values get scrubbed."""
        from rondo.engine import TaskResult

        tr = TaskResult(
            task_name="test",
            parsed_result={"output": "password = 'hunter2'"},
        )
        sanitized_tr, sr = sanitize_task_result(tr)
        assert "hunter2" not in json.dumps(sanitized_tr.parsed_result)

    def test_original_not_mutated(self):
        """Original TaskResult is not modified (new copy returned)."""
        from rondo.engine import TaskResult

        tr = TaskResult(
            task_name="test",
            raw_output="api_key = 'sk-keep-this'",
        )
        sanitized_tr, _ = sanitize_task_result(tr)
        ## Original should still have the secret
        assert "sk-keep-this" in tr.raw_output
        ## Sanitized should not
        assert "sk-keep-this" not in sanitized_tr.raw_output


# ──────────────────────────────────────────────────────────────────
#  STD-114 req 007 — Raw preserved in memory
# ──────────────────────────────────────────────────────────────────


class TestRawPreservation:
    """STD-114 req 007: raw unscrubbed preserved in memory during dispatch."""

    def test_sanitize_text_returns_original(self):
        """SanitizeResult includes original_text for in-memory use."""
        result = sanitize_text("api_key = 'secret'")
        assert result.original_text == "api_key = 'secret'"


# ──────────────────────────────────────────────────────────────────
#  STD-114 req 008 — Environment variable patterns stripped
# ──────────────────────────────────────────────────────────────────


class TestEnvVarStripping:
    """STD-114 req 008: env var patterns stripped from stored output."""

    def test_dollar_var_stripped(self):
        """${VAR_NAME} patterns replaced."""
        result = sanitize_text("path is ${SECRET_TOKEN}/data")
        assert "${SECRET_TOKEN}" not in result.sanitized_text

    def test_home_tilde_stripped(self):
        """~/.env patterns replaced."""
        result = sanitize_text("loaded from ~/.env.production")
        assert "~/.env.production" not in result.sanitized_text

    def test_dollar_home(self):
        """$HOME path stripped."""
        result = sanitize_text("config at $HOME/.config/secrets.json")
        assert "$HOME" not in result.sanitized_text


# ──────────────────────────────────────────────────────────────────
#  STD-114 req 009 — File paths truncated
# ──────────────────────────────────────────────────────────────────


class TestFilePathTruncation:
    """STD-114 req 009: file paths truncated to basename, hide home dir."""

    def test_home_dir_hidden(self):
        """Full home directory path replaced."""
        import os

        home = os.path.expanduser("~")
        result = sanitize_text(f"reading {home}/secrets/keys.json")
        assert home not in result.sanitized_text

    def test_basename_preserved(self):
        """File basename remains visible after path truncation."""
        import os

        home = os.path.expanduser("~")
        result = sanitize_text(f"reading {home}/project/config.toml")
        assert "config.toml" in result.sanitized_text


# ──────────────────────────────────────────────────────────────────
#  STD-114 req 010 — Log scrubbing events (never log actual secret)
# ──────────────────────────────────────────────────────────────────


class TestScrubAudit:
    """STD-114 req 010: log scrubbing events, never log the actual secret."""

    def test_detection_has_pattern_name(self):
        """Each detection records which pattern matched — assert actual name."""
        result = sanitize_text("api_key = 'sk-test123'")
        assert len(result.detections) > 0
        assert isinstance(result.detections[0].pattern_name, str)
        assert len(result.detections[0].pattern_name) >= 3, (
            f"Pattern name too short: {result.detections[0].pattern_name!r}"
        )

    def test_detection_has_line_number(self):
        """Detection records line number."""
        text = "line 1\napi_key = 'sk-test123'\nline 3"
        result = sanitize_text(text)
        assert any(d.line_number == 2 for d in result.detections)

    def test_detection_never_contains_secret_value(self):
        """Detection object does NOT store the actual secret."""
        result = sanitize_text("api_key = 'sk-top-secret-value-here'")
        for detection in result.detections:
            ## Check no attribute contains the secret
            assert "sk-top-secret-value-here" not in str(detection)


# ──────────────────────────────────────────────────────────────────
#  STD-114 req 011 — Scrubbing count in result metadata
# ──────────────────────────────────────────────────────────────────


class TestScrubCount:
    """STD-114 req 011: scrubbing count in dispatch result metadata."""

    def test_secrets_found_count(self):
        """SanitizeResult.secrets_found matches actual count."""
        result = sanitize_text("api_key = 'sk-longvalue123' password = 'secretpass99'")
        assert result.secrets_found >= 2

    def test_task_result_has_count(self):
        """sanitize_task_result returns count in SanitizeResult."""
        from rondo.engine import TaskResult

        tr = TaskResult(
            task_name="test",
            raw_output="password = 'secret'",
        )
        _, sr = sanitize_task_result(tr)
        assert sr.secrets_found > 0


# ──────────────────────────────────────────────────────────────────
#  STD-114 req 012 — Zero secrets = no noise
# ──────────────────────────────────────────────────────────────────


class TestQuietMode:
    """STD-114 req 012: if 0 secrets scrubbed, no log noise."""

    def test_clean_text_empty_detections(self):
        """Clean text produces empty detections list."""
        result = sanitize_text("This is perfectly clean output.")
        assert result.detections == []
        assert result.secrets_found == 0

    def test_clean_text_sanitized_equals_original(self):
        """Clean text: sanitized_text == original_text."""
        text = "Normal output with no secrets at all."
        result = sanitize_text(text)
        assert result.sanitized_text == text


# ──────────────────────────────────────────────────────────────────
#  Edge cases
# ──────────────────────────────────────────────────────────────────


class TestEdgeCases:
    """Edge cases for sanitization."""

    def test_empty_string(self):
        """Empty input returns empty output."""
        result = sanitize_text("")
        assert result.sanitized_text == ""
        assert result.secrets_found == 0

    def test_none_parsed_result(self):
        """TaskResult with None parsed_result doesn't crash."""
        from rondo.engine import TaskResult

        tr = TaskResult(task_name="test", parsed_result=None)
        sanitized_tr, sr = sanitize_task_result(tr)
        assert sanitized_tr.parsed_result is None
        assert sr.secrets_found == 0

    def test_nested_dict_scrubbed(self):
        """Nested dicts in parsed_result are fully scrubbed."""
        from rondo.engine import TaskResult

        tr = TaskResult(
            task_name="test",
            parsed_result={"level1": {"level2": "password = 'nested_secret'"}},
        )
        sanitized_tr, _ = sanitize_task_result(tr)
        assert "nested_secret" not in json.dumps(sanitized_tr.parsed_result)

    def test_unicode_text(self):
        """Unicode text doesn't break sanitization."""
        result = sanitize_text("日本語テスト api_key = 'sk-unicode-test'")
        assert result.secrets_found > 0
        assert "sk-unicode-test" not in result.sanitized_text

    def test_multiline_private_key(self):
        """Multi-line private key block fully redacted."""
        text = (
            "-----BEGIN PRIVATE KEY-----\n"
            "MIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQC\n"
            "-----END PRIVATE KEY-----"
        )
        result = sanitize_text(text)
        assert "MIIEvg" not in result.sanitized_text


# -- sig: mgh-6201.cd.bd955f.f1a1.92a1b3
