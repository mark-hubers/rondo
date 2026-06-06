# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Model registry — provider model lists, cache, drift report.

REQ-111 reqs 600-603 (RONDO-305). Driver: providers retire/rename models
every few weeks; pinned config names rot silently until a dispatch 404s.
The hand-run prototype of this check (2026-06-05) found xAI had RETIRED
the entire grok-3 family — all three configured tiers dead, nobody knew.

Design rules:
    - Detection automated, fix manual (suggest mode): this module NEVER
      writes config. It reports; Mark flips lines. (Session 81 rule.)
    - Per-provider fetch failure is non-fatal (req 600).
    - Read-only catalog fetches: no prompts, no dispatch, ~$0.
    - Fetcher + key loader are injectable — tests never touch the network.

Import direction:
    model_registry.py → adapters.auth (key loading) only when used live.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_CACHE_PATH = "~/.rondo/models-cache.json"
TIER_KEYS = ("cheap_model", "default_model", "best_model")

# -- provider name → (models endpoint, auth style). Gemini uses key-in-URL.
_ENDPOINTS: dict[str, tuple[str, str]] = {
    "openai": ("https://api.openai.com/v1/models", "bearer"),
    "mistral": ("https://api.mistral.ai/v1/models", "bearer"),
    "grok": ("https://api.x.ai/v1/models", "bearer"),
    "anthropic": ("https://api.anthropic.com/v1/models", "anthropic"),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/models", "gemini"),
}


def default_fetcher(provider: str, cfg: dict[str, Any], api_key: str) -> list[str]:
    """Fetch a provider's served model IDs from its live endpoint — req 600.

    Read-only catalog GET. Raises OSError-family on failure; the caller
    (refresh_registry) records the error and continues.
    """
    if provider not in _ENDPOINTS:
        raise OSError(f"no models endpoint known for provider '{provider}'")
    url, auth = _ENDPOINTS[provider]
    headers: dict[str, str] = {"User-Agent": "rondo-model-registry/0.1"}
    if auth == "bearer":
        headers["Authorization"] = f"Bearer {api_key}"
    elif auth == "anthropic":
        headers["x-api-key"] = api_key
        headers["anthropic-version"] = "2023-06-01"
    elif auth == "gemini":
        url = f"{url}?key={api_key}&pageSize=200"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=20) as resp:  # nosec B310 -- https catalog GET
        data = json.loads(resp.read().decode("utf-8"))
    if "data" in data:  # -- OpenAI-shape (openai/mistral/grok/anthropic)
        return [m.get("id", "") for m in data["data"] if m.get("id")]
    if "models" in data:  # -- Gemini shape
        return [m.get("name", "").removeprefix("models/") for m in data["models"] if m.get("name")]
    return []


def refresh_registry(
    providers_cfg: dict[str, dict[str, Any]],
    *,
    key_loader: Callable[[str], str],
    fetcher: Callable[[str, dict[str, Any], str], list[str]] = default_fetcher,
    cache_path: str = DEFAULT_CACHE_PATH,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Refresh the model cache from every enabled provider — req 600.

    One provider's failure NEVER aborts the refresh: its entry records the
    error and keeps no stale model list (drift reports NO_CACHE for it).
    Writes the cache JSON and returns it.
    """
    now = now or datetime.now(UTC)
    cache: dict[str, Any] = {"fetched_at": now.isoformat(), "providers": {}}
    for name, cfg in providers_cfg.items():
        if not cfg.get("enabled", False):
            continue
        entry: dict[str, Any] = {"models": [], "error": ""}
        try:
            key = key_loader(name)
            entry["models"] = sorted(fetcher(name, cfg, key))
        except (OSError, ValueError, TypeError, KeyError) as exc:
            entry["error"] = f"{type(exc).__name__}: {exc}"
            logger.warning("-WARNING- registry refresh: %s fetch failed (%s) — non-fatal", name, exc)
        cache["providers"][name] = entry

    try:
        path = Path(cache_path).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        path.write_text(json.dumps(cache, indent=1), encoding="utf-8")
        path.chmod(0o600)
    except OSError as exc:
        logger.warning("-WARNING- registry cache write failed (%s) — returning in-memory cache", exc)
    return cache


def load_cache(cache_path: str = DEFAULT_CACHE_PATH) -> dict[str, Any] | None:
    """Load the cached registry, or None when absent/unreadable."""
    path = Path(cache_path).expanduser()
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def drift_report(cache: dict[str, Any], providers_cfg: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Compare configured tiers vs served models — reqs 602-603.

    States per configured tier:
        OK       — model is served
        STALE    — model NOT served (the dead-grok scenario) → fix config
        NO_CACHE — provider fetch failed; never fake-OK
    Plus NEW rows: served models not referenced by any tier (top 5 per
    provider) so new generations get seen, never auto-adopted.
    """
    entries: list[dict[str, Any]] = []
    cached = cache.get("providers", {})
    for name, cfg in providers_cfg.items():
        if not cfg.get("enabled", False):
            continue
        provider_cache = cached.get(name, {})
        served: list[str] = provider_cache.get("models", [])
        fetch_error: str = provider_cache.get("error", "") or ("" if provider_cache else "not in cache")
        configured = [cfg.get(t, "") for t in TIER_KEYS if cfg.get(t)]

        for tier in TIER_KEYS:
            model = cfg.get(tier, "")
            if not model:
                continue
            if fetch_error or not served:
                state = "NO_CACHE"
            elif model in served:
                state = "OK"
            else:
                state = "STALE"
            entries.append({"provider": name, "tier": tier, "model": model, "state": state, "note": fetch_error})

        # -- req 602 NEW: surface unconfigured served models (top 5, newest-ish last)
        if served:
            unconfigured = [m for m in served if m not in configured]
            for model in unconfigured[-5:]:
                entries.append({"provider": name, "tier": "-", "model": model, "state": "NEW", "note": ""})
    return entries


def format_drift_table(entries: list[dict[str, Any]]) -> str:
    """Human-readable drift table for `rondo providers --drift` — req 602."""
    if not entries:
        return "  drift: no enabled providers / empty cache — run a refresh first"
    lines = [f"  {'Provider':<11} {'Tier':<14} {'Model':<34} {'State':<8} Note"]
    lines.append(f"  {'─' * 11} {'─' * 14} {'─' * 34} {'─' * 8} {'─' * 20}")
    order = {"STALE": 0, "NO_CACHE": 1, "OK": 2, "NEW": 3}
    for e in sorted(entries, key=lambda x: (order.get(x["state"], 9), x["provider"])):
        lines.append(f"  {e['provider']:<11} {e['tier']:<14} {e['model']:<34} {e['state']:<8} {e['note'][:40]}")
    stale = sum(1 for e in entries if e["state"] == "STALE")
    if stale:
        lines.append(f"  ⚠ {stale} STALE tier(s) — update ~/.rondo/config.toml (registry never auto-edits)")
    return "\n".join(lines)


# -- ──────────────────────────────────────────────────────────────
# --  RONDO-316: auto-tiers + canary — REQ-111 reqs 604-610
# -- ──────────────────────────────────────────────────────────────

# -- capability-class markers (req 607): the registry's alias-first rule
# -- means names ARE the capability metadata we have. Matched as whole
# -- name TOKENS (split on -._/) — substring matching classified every
# -- "geMINI" model as low. Low/high markers are provider-spanning;
# -- anything unmarked is mid.
_LOW_MARKERS = ("nano", "lite", "mini", "haiku", "small", "tiny")
_HIGH_MARKERS = ("opus", "pro", "large", "ultra", "flagship")

# -- non-chat exclusion (live run 2026-06-06: openai auto_high derived to
# -- text-embedding-3-large, grok to an imagine-video model — catalogs mix
# -- every modality). A model carrying ANY of these tokens never enters a
# -- text tier.
_NON_CHAT_MARKERS = (
    "embedding",
    "embed",
    "moderation",
    "whisper",
    "tts",
    "audio",
    "voice",
    "voxtral",
    "image",
    "imagine",
    "video",
    "dall",
    "sora",
    "realtime",
    "transcribe",
    "ocr",
    "rerank",
)

_TIER_TO_AUTO = {
    "cheap_model": "auto_low",
    "default_model": "auto_mid",
    "best_model": "auto_high",
}


def _capability_class(model: str) -> str:
    """Classify a model ID into low/mid/high by name TOKENS — req 607."""
    tokens = set(re.split(r"[-._/]", model.lower()))
    if tokens & set(_LOW_MARKERS):
        return "low"
    if tokens & set(_HIGH_MARKERS):
        return "high"
    return "mid"


def _pick_from_bucket(bucket: list[str]) -> str:
    """Pick one model from a class bucket — alias-first (req 603), else last."""
    aliases = [m for m in bucket if "latest" in m.lower()]
    if aliases:
        return aliases[-1]
    return bucket[-1]


def derive_auto_tiers(cache: dict[str, Any], providers_cfg: dict[str, dict[str, Any]]) -> dict[str, dict[str, str]]:
    """Derive auto_low/auto_mid/auto_high per provider — reqs 607-609.

    Within-provider ONLY (req 609): a provider's tiers come from ITS served
    list, never another's. Collapse ladder (req 608): missing low inherits
    mid, missing mid inherits high; a one-model provider fills all three.
    Providers with fetch errors or empty lists are skipped — never derive
    from stale or absent data.
    """
    cached = cache.get("providers", {})
    tiers: dict[str, dict[str, str]] = {}
    for name, cfg in providers_cfg.items():
        if not cfg.get("enabled", False):
            continue
        provider_cache = cached.get(name, {})
        served: list[str] = provider_cache.get("models", [])
        if not served or provider_cache.get("error"):
            continue
        buckets: dict[str, list[str]] = {"low": [], "mid": [], "high": []}
        for model in served:
            tokens = set(re.split(r"[-._/]", model.lower()))
            if tokens & set(_NON_CHAT_MARKERS):
                continue  # -- embeddings/moderation/audio/image never enter text tiers
            buckets[_capability_class(model)].append(model)
        picks = {cls: _pick_from_bucket(bucket) for cls, bucket in buckets.items() if bucket}
        # -- req 608 collapse ladder: "next best" fills the gaps
        high = picks.get("high") or picks.get("mid") or picks.get("low") or ""
        mid = picks.get("mid") or high
        low = picks.get("low") or mid
        if high:
            tiers[name] = {"auto_low": low, "auto_mid": mid, "auto_high": high}
    return tiers


def resolve_model(
    provider: str,
    tier_key: str,
    providers_cfg: dict[str, dict[str, Any]],
    auto_tiers: dict[str, dict[str, str]],
) -> str:
    """COALESCE one tier: manual pin → auto-tier → '' — req 610.

    Manual ALWAYS wins (same idiom as REQ-109 reqs 024/320). The auto term
    already embeds the collapse ladder from derive_auto_tiers.
    """
    manual = (providers_cfg.get(provider) or {}).get(tier_key, "")
    if manual:
        return str(manual)
    auto_key = _TIER_TO_AUTO.get(tier_key, "")
    return (auto_tiers.get(provider) or {}).get(auto_key, "")


def registry_mode(config: dict[str, Any]) -> str:
    """Registry mode — req 605: 'suggest' (default) never writes config.

    req 606 auto-APPLY (config writes + audit + morning report) is NOT
    built yet — 'auto' downgrades to suggest WITH a warning rather than
    silently pretending. Tracked as an open work request.
    """
    mode = str((config.get("registry") or {}).get("mode", "suggest")).lower()
    if mode == "auto":
        logger.warning(
            "-WARNING- registry mode 'auto' requested but auto-apply is not "
            "implemented yet (REQ-111 req 606) — running in suggest mode"
        )
        return "suggest"
    return "suggest" if mode != "suggest" else mode


def _canary_dispatch(provider: str, model: str) -> tuple[bool, str, float]:
    """Live canary: one tiny dispatch proving the model ID answers — req 604."""
    from rondo.adapters.factory import get_adapter  # pylint: disable=import-outside-toplevel

    adapter = get_adapter(provider, model)
    if adapter is None:
        return False, f"no adapter for provider {provider!r}", 0.0
    tr = adapter.dispatch(prompt="Reply with exactly: OK", model=model)
    ok = bool(tr.raw_output) and tr.status not in ("error", "failed")
    note = "" if ok else (tr.error_message or tr.error_code or "empty response")
    return ok, str(note)[:120], float(tr.cost_usd or 0.0)


def verify_models(
    providers_cfg: dict[str, dict[str, Any]],
    *,
    dispatcher: Callable[[str, str], tuple[bool, str, float]] = _canary_dispatch,
) -> list[dict[str, Any]]:
    """Canary every configured tier model — req 604. PASS/FAIL/SKIP rows.

    Disabled providers and blank tiers produce SKIP rows (visible, never
    silently absent). A dispatcher crash is a FAIL row, not an exception —
    one dead provider must not hide the others' results.
    """
    rows: list[dict[str, Any]] = []
    for name, cfg in providers_cfg.items():
        enabled = bool(cfg.get("enabled", False))
        for tier in TIER_KEYS:
            model = str(cfg.get(tier, "") or "")
            if not model:
                continue
            if not enabled:
                rows.append(
                    {
                        "provider": name,
                        "tier": tier,
                        "model": model,
                        "result": "SKIP",
                        "note": "provider disabled",
                        "cost_usd": 0.0,
                    }
                )
                continue
            try:
                ok, note, cost = dispatcher(name, model)
            except (OSError, ValueError, TypeError, KeyError, RuntimeError) as exc:
                ok, note, cost = False, str(exc)[:120], 0.0
            rows.append(
                {
                    "provider": name,
                    "tier": tier,
                    "model": model,
                    "result": "PASS" if ok else "FAIL",
                    "note": note,
                    "cost_usd": cost,
                }
            )
    return rows


def format_verify_table(rows: list[dict[str, Any]]) -> str:
    """Render the canary table — req 604."""
    if not rows:
        return "  (no configured tier models found)"
    lines = [f"  {'PROVIDER':<11} {'TIER':<14} {'MODEL':<34} {'RESULT':<7} NOTE"]
    for r in rows:
        lines.append(f"  {r['provider']:<11} {r['tier']:<14} {r['model']:<34} {r['result']:<7} {r['note'][:40]}")
    total = sum(r["cost_usd"] for r in rows)
    fails = sum(1 for r in rows if r["result"] == "FAIL")
    lines.append(f"  {len(rows)} canaries, {fails} FAIL, total cost ${total:.4f}")
    return "\n".join(lines)


# -- sig: mgh-6201.cd.bd955f.f1a8.mr305b


# -- sig: mgh-6201.cd.bd955f.016c.f2b27b
