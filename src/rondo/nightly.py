# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Rondo nightly watchdog — the sweep that watches when nobody is looking.

RONDO-314 (finding #285 residual): registry drift, retry-queue rot, and
reliability decay were all DETECTABLE but only on demand — the fleet had
instruments and no night watchman. run_nightly_check() composes the three
checks into one schedulable sweep:

    drift     — configured models vs each provider's live list (REQ-111 600-603)
    retryq    — sweep aged/permanent entries to dead-letter, depth alert (REQ-109)
    metrics   — 7-day success rate vs the 95% reliability target (STD-101 240-242)

Any FAILURE/STALE condition fires notify_watchdog (terminal + file + macOS),
so a silent overnight fleet failure becomes a banner on the screen by morning.

Schedule it:  rondo schedule --cmd nightly --interval daily --install

Import direction:
    nightly.py → model_registry, retry_queue, metrics, notify, config
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from rondo.notify import notify_watchdog

## -- the campaign goal: 95% dispatch reliability (STD-101 scoreboard target)
RELIABILITY_FLOOR = 0.95
## -- minimum 7d volume before a low rate is signal rather than noise
RELIABILITY_MIN_VOLUME = 10


@dataclass
class NightlyReport:
    """One sweep's verdict — JSON-safe for audit/MCP consumption."""

    status: str = "OK"  # -- OK | ALERT
    alerts: list[str] = field(default_factory=list)
    drift: list[dict[str, Any]] = field(default_factory=list)
    retry_sweep: dict[str, Any] = field(default_factory=dict)
    success_rate_7d: float | None = None
    dispatches_7d: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON output and the audit trail."""
        return asdict(self)


def _gather_drift(refresh: bool) -> list[dict[str, Any]]:
    """Registry drift entries; optionally refresh the live cache first."""
    # -- import-outside-toplevel: keep nightly importable when adapters aren't configured
    from rondo.adapters.auth import load_api_key  # pylint: disable=import-outside-toplevel
    from rondo.config import get_rondo_config  # pylint: disable=import-outside-toplevel
    from rondo.model_registry import (  # pylint: disable=import-outside-toplevel
        drift_report,
        load_cache,
        refresh_registry,
    )

    providers_cfg = get_rondo_config().get("providers", {})
    if refresh:
        refresh_registry(providers_cfg, key_loader=load_api_key)
    cache = load_cache() or {}
    return drift_report(cache, providers_cfg)


def _sweep_retryq() -> dict[str, Any]:
    """Sweep the retry queue; return counts + depth alert."""
    from rondo.retry_queue import (  # pylint: disable=import-outside-toplevel
        resolve_retry_dir,
        sweep_retry_queue,
    )

    report = sweep_retry_queue(resolve_retry_dir())
    return {
        "dead_lettered": report.dead_lettered_permanent + report.dead_lettered_expired,
        "remaining": report.remaining,
        "queue_alert": report.alert,
    }


def _compute_reliability() -> dict[str, Any]:
    """7-day windowed success rate from the always-on audit trail."""
    from rondo.metrics import compute_metrics  # pylint: disable=import-outside-toplevel

    report = compute_metrics()
    return {
        "success_rate_7d": report.success_rate_7d,
        "dispatches_7d": report.dispatches_7d,
    }


def run_nightly_check(*, refresh: bool = True, notify_alerts: bool = True) -> NightlyReport:
    """Run the full watchdog sweep; alert on anything that needs a human.

    Every subsystem failure is captured as an alert, never an exception —
    a watchdog that dies when a subsystem dies is no watchdog at all.
    """
    report = NightlyReport()

    ## -- 1) model registry drift: a STALE model means tomorrow's dispatch 404s
    try:
        report.drift = _gather_drift(refresh)
        ## -- drift_report entries carry "state" (NOT "status") — guarded by
        ## -- test_drift_alert_uses_real_drift_report_shape
        for entry in report.drift:
            if entry.get("state") in ("STALE", "NO_CACHE"):
                report.alerts.append(f"{entry.get('provider')}: {entry.get('model')} is {entry.get('state')}")
    except (OSError, ValueError, KeyError) as exc:
        report.alerts.append(f"drift check failed: {exc}")

    ## -- 2) retry queue: sweep rot to dead-letter, alert on depth
    try:
        report.retry_sweep = _sweep_retryq()
        if report.retry_sweep.get("queue_alert"):
            report.alerts.append(str(report.retry_sweep["queue_alert"]))
    except (OSError, ValueError, KeyError) as exc:
        report.alerts.append(f"retry sweep failed: {exc}")

    ## -- 3) reliability: 7d rate below the 95% floor (with volume) is an alert
    try:
        reliability = _compute_reliability()
        report.success_rate_7d = reliability.get("success_rate_7d")
        report.dispatches_7d = int(reliability.get("dispatches_7d") or 0)
        rate = report.success_rate_7d
        if rate is not None and report.dispatches_7d >= RELIABILITY_MIN_VOLUME and rate < RELIABILITY_FLOOR:
            report.alerts.append(
                f"7d success rate {rate:.0%} below {RELIABILITY_FLOOR:.0%} target ({report.dispatches_7d} dispatches)"
            )
    except (OSError, ValueError, KeyError) as exc:
        report.alerts.append(f"metrics check failed: {exc}")

    if report.alerts:
        report.status = "ALERT"
        if notify_alerts:
            notify_watchdog(report.alerts, title="Rondo nightly watchdog")
    return report
