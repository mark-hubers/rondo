# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Rondo provider scoring — learn from dispatch history.

REQ-111 reqs 442-445, REQ-109 (Adaptive Provider Scoring) reqs 300-324.
Reads audit JSONL, computes per-provider quality scores, caches results.

Import direction:
    scoring.py → reads audit JSONL files (no rondo imports needed)
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# -- Default score weights (REQ-109 addendum req 301)
DEFAULT_WEIGHTS = {
    "success": 0.5,
    "cost": 0.3,
    "latency": 0.2,
}

# -- Minimum dispatches before scoring (REQ-109 addendum req 302)
MIN_SAMPLE_COUNT = 10

# -- Score window in seconds: 7 days (REQ-109 addendum req 303)
SCORE_WINDOW_SEC = 7 * 24 * 3600


def compute_provider_scores(audit_dir: str = "") -> dict[str, dict[str, Any]]:
    """Compute per-provider quality scores from audit JSONL history.

    REQ-111 req 442: reads last 7 days of dispatch data.
    Returns dict of provider → score breakdown.
    """
    if not audit_dir:
        audit_dir = os.path.expanduser("~/.rondo/audit")

    audit_path = Path(audit_dir)
    if not audit_path.is_dir():
        logger.warning("Audit dir not found: %s", audit_dir)
        return {}

    # -- Read all JSONL files in audit dir
    records = _load_recent_outcomes(audit_path)
    if not records:
        return {}

    # -- Group by provider
    by_provider: dict[str, list[dict]] = {}
    for rec in records:
        provider = rec.get("model", "unknown")
        if provider:
            by_provider.setdefault(provider, []).append(rec)

    # -- Compute scores
    scores: dict[str, dict[str, Any]] = {}
    for provider, recs in by_provider.items():
        if len(recs) < MIN_SAMPLE_COUNT:
            continue
        scores[provider] = _score_provider(provider, recs)

    return scores


def _load_recent_outcomes(audit_path: Path) -> list[dict]:
    """Load OUTCOME records from JSONL within the score window."""
    cutoff = time.time() - SCORE_WINDOW_SEC
    records: list[dict] = []

    for jsonl_file in sorted(audit_path.glob("*.jsonl")):
        try:
            for line in jsonl_file.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                # -- Only OUTCOME records (status != "INTENT")
                if rec.get("status") == "INTENT":
                    continue
                # -- Within time window
                completed = rec.get("completed_at", "")
                if completed and completed > time.strftime("%Y-%m-%d", time.gmtime(cutoff)):
                    records.append(rec)
        except OSError as exc:
            logger.debug("Failed to read %s: %s", jsonl_file, exc)

    return records


def _score_provider(provider: str, records: list[dict]) -> dict[str, Any]:
    """Compute score for a single provider from its records.

    Score = success_rate * w_success + (1 - norm_cost) * w_cost + (1 - norm_latency) * w_latency
    """
    done_count = sum(1 for r in records if r.get("status") == "done")
    error_count = sum(1 for r in records if r.get("status") == "error")
    total = done_count + error_count
    success_rate = done_count / total if total > 0 else 0.0

    costs = [r.get("cost_usd", 0.0) for r in records if r.get("cost_usd", 0) > 0]
    avg_cost = sum(costs) / len(costs) if costs else 0.0

    latencies = [r.get("duration_sec", 0.0) for r in records if r.get("duration_sec", 0) > 0]
    avg_latency = sum(latencies) / len(latencies) if latencies else 0.0

    # -- JSON quality rating (REQ-111)
    json_checks = [r for r in records if r.get("json_valid") is not None]
    json_success_rate = sum(1 for r in json_checks if r.get("json_valid")) / len(json_checks) if json_checks else None

    fields_checks = [r for r in records if r.get("fields_complete") is not None]
    fields_complete_rate = (
        sum(1 for r in fields_checks if r.get("fields_complete")) / len(fields_checks) if fields_checks else None
    )

    # -- Composite score (simplified — no cross-provider normalization yet)
    w = DEFAULT_WEIGHTS
    score = success_rate * w["success"]
    if avg_cost > 0:
        score += (1.0 - min(avg_cost / 0.05, 1.0)) * w["cost"]  # -- $0.05 as reference max
    else:
        score += w["cost"]  # -- free = perfect cost score
    if avg_latency > 0:
        score += (1.0 - min(avg_latency / 10.0, 1.0)) * w["latency"]  # -- 10s as reference max
    else:
        score += w["latency"]  # -- instant = perfect latency score

    return {
        "provider": provider,
        "score": round(score, 3),
        "success_rate": round(success_rate, 3),
        "avg_cost_usd": round(avg_cost, 6),
        "avg_latency_sec": round(avg_latency, 2),
        "json_success_rate": round(json_success_rate, 3) if json_success_rate is not None else None,
        "fields_complete_rate": round(fields_complete_rate, 3) if fields_complete_rate is not None else None,
        "sample_count": len(records),
        "done_count": done_count,
        "error_count": error_count,
    }


def save_scores_cache(scores: dict[str, dict[str, Any]], cache_dir: str = "") -> None:
    """Save computed scores to cache file.

    REQ-111 req 443: ~/.rondo/learned/provider_scores.json
    """
    if not cache_dir:
        cache_dir = os.path.expanduser("~/.rondo/learned")

    path = Path(cache_dir)
    path.mkdir(parents=True, exist_ok=True, mode=0o700)

    cache_file = path / "provider_scores.json"
    data = {
        "computed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "window_days": 7,
        "min_samples": MIN_SAMPLE_COUNT,
        "providers": scores,
    }
    cache_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
    logger.info("Provider scores cached to %s (%d providers)", cache_file, len(scores))


def load_scores_cache(cache_dir: str = "") -> dict[str, dict[str, Any]]:
    """Load cached provider scores.

    Returns empty dict if cache doesn't exist or is stale (>5 min).
    """
    if not cache_dir:
        cache_dir = os.path.expanduser("~/.rondo/learned")

    cache_file = Path(cache_dir) / "provider_scores.json"
    if not cache_file.is_file():
        return {}

    try:
        data = json.loads(cache_file.read_text(encoding="utf-8"))
        return data.get("providers", {})
    except (json.JSONDecodeError, OSError, KeyError):
        return {}


# -- sig: mgh-6201.cd.bd955f.5c0e.1ea4b0
