# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Rondo output sanitization — detect and scrub secrets from AI output.

Rondo-STD-114: Output Sanitization.
Scans AI output for secret patterns (API keys, passwords, tokens, private
keys, high-entropy strings) and replaces them with [REDACTED:pattern_name]
placeholders before storage. Raw output preserved in memory for current
dispatch processing; scrubbed only at storage boundary.

Import direction:
    sanitize.py → no rondo imports (standalone utility)
"""

from __future__ import annotations

import copy
import logging
import math
import os
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# -- ──────────────────────────────────────────────────────────────
# --  Pattern definitions — STD-114 req 002
# -- ──────────────────────────────────────────────────────────────


@dataclass
class SecretPattern:
    """One pattern that identifies a potential secret."""

    name: str
    regex: str
    confidence: float = 0.95
    compiled: re.Pattern[str] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.compiled = re.compile(self.regex)


# -- STD-114 req 002: default patterns
DEFAULT_PATTERNS: list[SecretPattern] = [
    SecretPattern(
        name="api_key",
        regex=r"""(?i)(?:api[_-]?key|apikey)\s*[=:]\s*['"]?([A-Za-z0-9_\-]{8,})['"]?""",
        confidence=0.95,
    ),
    SecretPattern(
        name="password",
        regex=r"""(?i)(?:password|passwd|pwd)\s*[=:]\s*['"]?([^\s'"]{4,})['"]?""",
        confidence=0.95,
    ),
    SecretPattern(
        name="secret_key",
        regex=r"""(?i)(?:secret[_-]?key|SECRET_KEY)\s*[=:]\s*['"]?([A-Za-z0-9_\-]{8,})['"]?""",
        confidence=0.95,
    ),
    SecretPattern(
        name="bearer_token",
        regex=r"""(?i)Bearer\s+([A-Za-z0-9_\-.]+)""",
        confidence=0.95,
    ),
    SecretPattern(
        name="auth_token",
        regex=r"""(?i)(?:auth[_-]?token|token)\s*[=:]\s*['"]?([A-Za-z0-9_\-]{10,})['"]?""",
        confidence=0.95,
    ),
    SecretPattern(
        name="anthropic_key",
        regex=r"""(sk-ant-[A-Za-z0-9_\-]{20,})""",
        confidence=0.99,
    ),
    SecretPattern(
        name="openai_project_key",
        regex=r"""(sk-proj-[A-Za-z0-9_\-]{20,})""",
        confidence=0.99,
    ),
    SecretPattern(
        name="sk_prefix_key",
        regex=r"""(sk-[A-Za-z0-9]{20,})""",
        confidence=0.95,
    ),
    SecretPattern(
        name="github_personal_access_token",
        regex=r"""(ghp_[A-Za-z0-9]{36,})""",
        confidence=0.99,
    ),
    SecretPattern(
        name="github_oauth",
        regex=r"""(gho_[A-Za-z0-9]{36,})""",
        confidence=0.99,
    ),
    SecretPattern(
        name="github_server_token",
        regex=r"""(ghs_[A-Za-z0-9]{36,})""",
        confidence=0.99,
    ),
    SecretPattern(
        name="github_user_token",
        regex=r"""(ghu_[A-Za-z0-9]{36,})""",
        confidence=0.99,
    ),
    SecretPattern(
        name="github_refresh_token",
        regex=r"""(ghr_[A-Za-z0-9]{36,})""",
        confidence=0.99,
    ),
    SecretPattern(
        name="github_fine_grained_pat",
        regex=r"""(github_pat_[A-Za-z0-9_]{80,})""",
        confidence=0.99,
    ),
    SecretPattern(
        name="gitlab_pat",
        regex=r"""(glpat-[A-Za-z0-9_\-]{20,})""",
        confidence=0.99,
    ),
    SecretPattern(
        name="slack_bot_token",
        regex=r"""(xoxb-[A-Za-z0-9\-]{20,})""",
        confidence=0.99,
    ),
    SecretPattern(
        name="slack_user_token",
        regex=r"""(xoxp-[A-Za-z0-9\-]{20,})""",
        confidence=0.99,
    ),
    SecretPattern(
        name="slack_app_token",
        regex=r"""(xapp-[A-Za-z0-9\-]{20,})""",
        confidence=0.99,
    ),
    SecretPattern(
        name="slack_legacy_token",
        regex=r"""(xoxa-[A-Za-z0-9\-]{20,})""",
        confidence=0.99,
    ),
    SecretPattern(
        name="slack_session_token",
        regex=r"""(xoxs-[A-Za-z0-9\-]{20,})""",
        confidence=0.99,
    ),
    SecretPattern(
        name="jwt_token",
        regex=r"""(eyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,})""",
        confidence=0.95,
    ),
    SecretPattern(
        name="aws_access_key",
        regex=r"""(AKIA[0-9A-Z]{16})""",
        confidence=0.99,
    ),
    SecretPattern(
        name="aws_temp_access_key",
        regex=r"""(ASIA[0-9A-Z]{16})""",
        confidence=0.99,
    ),
    SecretPattern(
        name="aws_session_token",
        regex=r"""(?i)(?:aws[_-]?session[_-]?token)\s*[=:]\s*['"]?([A-Za-z0-9/+=]{100,})['"]?""",
        confidence=0.95,
    ),
    SecretPattern(
        name="google_api_key",
        regex=r"""(AIza[A-Za-z0-9_\-]{35})""",
        confidence=0.99,
    ),
    SecretPattern(
        name="stripe_live_key",
        regex=r"""(sk_live_[A-Za-z0-9]{24,})""",
        confidence=0.99,
    ),
    SecretPattern(
        name="stripe_test_key",
        regex=r"""(sk_test_[A-Za-z0-9]{24,})""",
        confidence=0.99,
    ),
    SecretPattern(
        name="private_key",
        regex=r"""-----BEGIN\s+(?:RSA\s+|EC\s+|DSA\s+|OPENSSH\s+)?PRIVATE\s+KEY-----[\s\S]*?-----END\s+(?:RSA\s+|EC\s+|DSA\s+|OPENSSH\s+)?PRIVATE\s+KEY-----""",
        confidence=0.99,
    ),
    SecretPattern(
        name="private_key_begin",
        regex=r"""-----BEGIN\s+(?:RSA\s+|EC\s+|DSA\s+|OPENSSH\s+)?PRIVATE\s+KEY-----[\s\S]*""",
        confidence=0.95,
    ),
    SecretPattern(
        name="high_entropy_base64",
        regex=r"""['"]([A-Za-z0-9+/]{40,}={0,2})['"]""",
        confidence=0.6,
    ),
]


# -- ──────────────────────────────────────────────────────────────
# --  Environment and path patterns — STD-114 reqs 008, 009
# -- ──────────────────────────────────────────────────────────────

_ENV_PATTERNS: list[tuple[str, str]] = [
    ("env_dollar_brace", r"""\$\{[A-Z_][A-Z0-9_]*\}"""),
    ("env_dollar", r"""\$HOME\b"""),
    ("env_dotenv", r"""~/\.env[.\w]*"""),
]

_HOME_DIR = os.path.expanduser("~")


# -- ──────────────────────────────────────────────────────────────
# --  Data structures — STD-114 reqs 010, 011
# -- ──────────────────────────────────────────────────────────────


@dataclass
class Detection:
    """One detected secret — STD-114 req 010.

    Never stores the actual secret value.
    """

    pattern_name: str
    confidence: float
    line_number: int


@dataclass
class SanitizeResult:
    """Result of sanitizing text — STD-114 reqs 007, 011."""

    original_text: str
    sanitized_text: str
    secrets_found: int = 0
    detections: list[Detection] = field(default_factory=list)


@dataclass
class SanitizeConfig:
    """Configuration for sanitization — STD-114 req 004."""

    extra_patterns: list[dict[str, str]] = field(default_factory=list)
    scrub_env_vars: bool = True
    scrub_home_paths: bool = True


# -- ──────────────────────────────────────────────────────────────
# --  Core functions
# -- ──────────────────────────────────────────────────────────────


def _shannon_entropy(s: str) -> float:
    """Calculate Shannon entropy of a string."""
    if not s:
        return 0.0
    freq: dict[str, int] = {}
    for c in s:
        freq[c] = freq.get(c, 0) + 1
    length = len(s)
    return -sum((count / length) * math.log2(count / length) for count in freq.values())


def _get_line_number(text: str, match_start: int) -> int:
    """Get 1-based line number for a match position."""
    return text[:match_start].count("\n") + 1


def _build_patterns(config: SanitizeConfig | None) -> list[SecretPattern]:
    """Build full pattern list: defaults + custom — STD-114 req 004."""
    patterns = list(DEFAULT_PATTERNS)
    if config and config.extra_patterns:
        for extra in config.extra_patterns:
            patterns.append(
                SecretPattern(
                    name=extra.get("name", "custom"),
                    regex=extra["pattern"],
                    confidence=float(extra.get("confidence", 0.9)),
                )
            )
    return patterns


def _scrub_secret_patterns(
    text: str,
    sanitized: str,
    patterns: list[SecretPattern],
    detections: list[Detection],
) -> str:
    """Pass 1: detect and redact secret patterns — STD-114 reqs 001, 002, 005."""
    for pat in patterns:
        for match in pat.compiled.finditer(sanitized):
            line_num = _get_line_number(text, match.start())
            detections.append(
                Detection(
                    pattern_name=pat.name,
                    confidence=pat.confidence,
                    line_number=line_num,
                )
            )
    # -- Apply redactions
    for pat in patterns:
        sanitized = pat.compiled.sub(f"[REDACTED:{pat.name}]", sanitized)
    return sanitized


def _scrub_env_vars(
    text: str,
    sanitized: str,
    detections: list[Detection],
) -> str:
    """Pass 2: detect and redact environment variable patterns — STD-114 req 008."""
    for name, pattern in _ENV_PATTERNS:
        compiled = re.compile(pattern)
        for match in compiled.finditer(sanitized):
            line_num = _get_line_number(text, match.start())
            detections.append(
                Detection(
                    pattern_name=name,
                    confidence=0.8,
                    line_number=line_num,
                )
            )
        sanitized = compiled.sub(f"[REDACTED:{name}]", sanitized)
    return sanitized


def _scrub_home_paths(sanitized: str) -> str:
    """Pass 3: replace home directory paths with [PATH]/basename — STD-114 req 009."""
    if not _HOME_DIR:
        return sanitized
    home_pattern = re.compile(re.escape(_HOME_DIR) + r"(/[^\s'\"]*)?")
    for match in home_pattern.finditer(sanitized):
        full_path = match.group(0)
        basename = os.path.basename(full_path.rstrip("'\"")) if match.group(1) else ""
        replacement = f"[PATH]/{basename}" if basename else "[PATH]"
        sanitized = sanitized.replace(full_path, replacement)
    return sanitized


def sanitize_text(
    text: str,
    *,
    config: SanitizeConfig | None = None,
) -> SanitizeResult:
    """Scan and scrub secrets from text — STD-114 reqs 001, 005, 007.

    Returns SanitizeResult with original preserved and sanitized copy.
    """
    if not text:
        return SanitizeResult(original_text=text, sanitized_text=text)

    config = config or SanitizeConfig()
    patterns = _build_patterns(config)
    detections: list[Detection] = []

    sanitized = _scrub_secret_patterns(text, text, patterns, detections)

    if config.scrub_env_vars:
        sanitized = _scrub_env_vars(text, sanitized, detections)

    if config.scrub_home_paths:
        sanitized = _scrub_home_paths(sanitized)

    # -- STD-114 req 012: no noise for clean output
    if not detections and sanitized == text:
        return SanitizeResult(
            original_text=text,
            sanitized_text=text,
            secrets_found=0,
            detections=[],
        )

    return SanitizeResult(
        original_text=text,
        sanitized_text=sanitized,
        secrets_found=len(detections),
        detections=detections,
    )


def sanitize_task_result(
    task_result: Any,
    *,
    config: SanitizeConfig | None = None,
) -> tuple[Any, SanitizeResult]:
    """Sanitize a TaskResult — STD-114 req 006.

    Returns (sanitized_copy, SanitizeResult).
    Original TaskResult is NOT mutated (req 007).
    """
    sanitized_tr = copy.deepcopy(task_result)
    all_detections: list[Detection] = []

    # -- Scrub raw_output
    if sanitized_tr.raw_output:
        sr = sanitize_text(sanitized_tr.raw_output, config=config)
        sanitized_tr.raw_output = sr.sanitized_text
        all_detections.extend(sr.detections)

    # -- Scrub stderr
    if sanitized_tr.stderr:
        sr = sanitize_text(sanitized_tr.stderr, config=config)
        sanitized_tr.stderr = sr.sanitized_text
        all_detections.extend(sr.detections)

    # -- Scrub parsed_result (recursive dict/list scrubbing)
    if sanitized_tr.parsed_result is not None:
        sanitized_tr.parsed_result = _scrub_dict(sanitized_tr.parsed_result, config=config, detections=all_detections)

    return sanitized_tr, SanitizeResult(
        original_text="",
        sanitized_text="",
        secrets_found=len(all_detections),
        detections=all_detections,
    )


def _scrub_dict(
    obj: Any,
    *,
    config: SanitizeConfig | None = None,
    detections: list[Detection],
) -> Any:
    """Recursively scrub string values in dicts/lists."""
    if isinstance(obj, str):
        sr = sanitize_text(obj, config=config)
        detections.extend(sr.detections)
        return sr.sanitized_text
    if isinstance(obj, dict):
        return {k: _scrub_dict(v, config=config, detections=detections) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_scrub_dict(item, config=config, detections=detections) for item in obj]
    return obj


# -- sig: mgh-6201.cd.bd955f.f1a1.92a1b2
