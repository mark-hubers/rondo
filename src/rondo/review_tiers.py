# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Merge ai-review --tier presets with ~/.rondo/config.toml [providers.*].

REQ-109: Rondo is SSOT for best_model / default_model / cheap_model per provider.
scripts/ai_review.py maps --tier best|standard|fast to those three fields.

Import direction: ai_review.py (optional) → review_tiers — no adapter imports.
"""

from __future__ import annotations

import copy
import logging
import os
import tomllib
from pathlib import Path

logger = logging.getLogger(__name__)

# -- ai-review PROVIDERS keys → [providers.<toml>] section names
_AI_REVIEW_TO_TOML: tuple[tuple[str, str], ...] = (
    ("openai", "openai"),
    ("gemini", "gemini"),
    ("mistral", "mistral"),
    ("grok", "grok"),
    ("claude", "anthropic"),
)

# -- ai-review CLI --tier → TOML field
_TIER_TO_FIELD: tuple[tuple[str, str], ...] = (
    ("best", "best_model"),
    ("standard", "default_model"),
    ("fast", "cheap_model"),
)


def merge_ai_review_tiers(builtin: dict[str, dict[str, str]]) -> dict[str, dict[str, str]]:
    """Return a deep copy of builtin with models overridden from Rondo config.

    Reads ~/.rondo/config.toml (or RONDO_CONFIG_PATH). For each enabled
    [providers.<name>] block, overwrites the matching ai-review tier row when
    best_model, default_model, or cheap_model is set.

    Unknown or missing config: returns a deep copy of builtin unchanged.
    """
    merged = copy.deepcopy(builtin)
    path = Path.home() / ".rondo" / "config.toml"
    alt = os.environ.get("RONDO_CONFIG_PATH", "").strip()
    if alt:
        path = Path(alt)
    if not path.is_file():
        return merged

    try:

        with open(path, "rb") as f:
            data = tomllib.load(f)
    except (OSError, UnicodeDecodeError, TypeError) as exc:
        logger.debug("merge_ai_review_tiers: skip config %s: %s", path, exc)
        return merged

    providers_cfg = data.get("providers", {})
    if not isinstance(providers_cfg, dict):
        return merged

    for tier_name, field in _TIER_TO_FIELD:
        if tier_name not in merged:
            merged[tier_name] = {}
        for ai_key, toml_key in _AI_REVIEW_TO_TOML:
            pcfg = providers_cfg.get(toml_key)
            if not isinstance(pcfg, dict):
                continue
            if pcfg.get("enabled") is False:
                continue
            val = pcfg.get(field)
            if isinstance(val, str) and val.strip():
                merged[tier_name][ai_key] = val.strip()

    return merged


def describe_tier_source() -> str:
    """Return human-readable config path for --help / diagnostics."""
    path = Path.home() / ".rondo" / "config.toml"
    alt = os.environ.get("RONDO_CONFIG_PATH", "").strip()
    if alt:
        return alt
    return str(path)


# -- sig: mgh-6201.cd.bd955f.b901.d42e11
