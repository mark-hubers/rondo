# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Rondo report — morning report generator.

Rondo-REQ-101 reqs 29-36.
Consumes OvernightResult, produces markdown report.

Import direction:
    engine.py → (no rondo imports)
    config.py → (no rondo imports)
    overnight.py → imports engine + config + runner
    report.py → imports engine + config + overnight (types only)
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

from rondo.config import RondoConfig
from rondo.overnight import OvernightResult

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────
#  Health indicator — Rondo-REQ-101 req 32
# ──────────────────────────────────────────────────────────────────


def _health_indicator(done: int, total: int) -> str:
    """Return health string based on done/total ratio.

    PASS — all succeeded.
    PARTIAL — some failed.
    FAIL — majority failed (more than half).
    """
    if total == 0:
        return "PASS"
    if done == total:
        return "PASS"
    if done > 0:
        return "PARTIAL"
    return "FAIL"


# ──────────────────────────────────────────────────────────────────
#  Format helpers
# ──────────────────────────────────────────────────────────────────


def _format_duration(seconds: float) -> str:
    """Format seconds as human-readable duration."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    if minutes < 60:
        return f"{minutes}m {secs}s"
    hours = minutes // 60
    mins = minutes % 60
    return f"{hours}h {mins}m"


# ──────────────────────────────────────────────────────────────────
#  generate_report() — Rondo-REQ-101 reqs 29-36
# ──────────────────────────────────────────────────────────────────


def generate_report(result: OvernightResult, metrics_report: object | None = None) -> str:
    """Generate morning report markdown from OvernightResult.

    Rondo-REQ-101 req 29: aggregate results from all phases.
    Rondo-REQ-101 req 30: group by round type.
    Rondo-REQ-101 req 31: round stats (done, failed, duration).
    Rondo-REQ-101 req 32: health indicators.
    Rondo-REQ-101 req 33: action items (failed/blocked tasks).
    Rondo-REQ-101 req 35: totals (duration, tasks, errors, timestamp).
    Rondo-REQ-101 req 36: usage summary (cost, tokens, watchdog).
    STD-101 req 242 (RONDO-302): 7-day success scoreboard vs the 95% target.
    `metrics_report` is injectable for tests; defaults to live compute.
    """
    lines: list[str] = []
    _emit_header(result, lines)
    _emit_summary(result, lines)
    _emit_scoreboard(lines, metrics_report)
    _emit_usage(result, lines)
    _emit_phases(result, lines)
    _emit_action_items(result, lines)
    return "\n".join(lines)


def _emit_scoreboard(lines: list[str], metrics_report: object | None = None) -> None:
    """Emit the 7-day reliability scoreboard — STD-101 req 242 (RONDO-302).

    Best-effort: the morning report MUST always generate (STD-108 rule 10),
    so any metrics failure is swallowed and the section simply omitted.
    """
    try:
        if metrics_report is None:
            from rondo.metrics import compute_metrics  # pylint: disable=import-outside-toplevel

            metrics_report = compute_metrics()
        rate = getattr(metrics_report, "success_rate_7d", None)
        if rate is None:
            return
        from rondo.metrics import SUCCESS_TARGET  # pylint: disable=import-outside-toplevel

        arrow = {"up": "↑", "down": "↓", "flat": "→"}.get(getattr(metrics_report, "trend_7d", "n/a"), "")
        count = getattr(metrics_report, "dispatches_7d", 0)
        verdict = "✓ above" if rate >= SUCCESS_TARGET else "✗ BELOW"
        lines.append(
            f"**7-day success:** {rate:.0%} {arrow} ({count} dispatches — target {SUCCESS_TARGET:.0%} {verdict})"
        )
        lines.append("")
        # -- STD-108 req 017 (RONDO-303): retry-queue depth alert — silent
        # -- growth is forbidden; the morning report is where Mark looks.
        import os  # pylint: disable=import-outside-toplevel

        from rondo.retry_queue import list_queue, queue_depth_alert  # pylint: disable=import-outside-toplevel

        test_dir = os.environ.get("RONDO_TEST_DIR")
        retry_dir = os.path.join(test_dir, "retry") if test_dir else "~/.rondo/retry"
        alert = queue_depth_alert(len(list_queue(retry_dir)))
        if alert:
            lines.append(f"⚠ **{alert}**")
            lines.append("")
    except (OSError, TypeError, ValueError, ImportError) as exc:
        logger.debug("Scoreboard emit skipped (non-fatal): %s", exc)


# ──────────────────────────────────────────────────────────────────
#  Report sections — extracted for clarity + pylint statement count
# ──────────────────────────────────────────────────────────────────


def _emit_header(result: OvernightResult, lines: list[str]) -> None:
    """Emit report header section."""
    lines.append("# Rondo Morning Report")
    lines.append("")
    lines.append(f"**Mode:** {result.mode}")
    lines.append(f"**Started:** {result.started_at}")
    lines.append(f"**Completed:** {result.completed_at}")
    lines.append(f"**Duration:** {_format_duration(result.duration_sec)}")
    lines.append(f"**Status:** {result.status}")
    lines.append("")


def _emit_summary(result: OvernightResult, lines: list[str]) -> None:
    """Emit totals section (Rondo-REQ-101 req 35)."""
    total_tasks = sum(len(pr.task_results) for pr in result.phase_results)
    total_done = sum(1 for pr in result.phase_results for tr in pr.task_results if tr.status == "done")
    total_errors = sum(1 for pr in result.phase_results for tr in pr.task_results if tr.status == "error")
    total_blocked = sum(1 for pr in result.phase_results for tr in pr.task_results if tr.status == "blocked")
    total_skipped = sum(1 for pr in result.phase_results for tr in pr.task_results if tr.status == "skipped")

    lines.append("## Summary")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Total tasks | {total_tasks} |")
    lines.append(f"| Done | {total_done} |")
    lines.append(f"| Errors | {total_errors} |")
    lines.append(f"| Skipped | {total_skipped} |")
    lines.append(f"| Blocked | {total_blocked} |")
    lines.append(f"| Duration | {_format_duration(result.duration_sec)} ({result.duration_sec:.1f}s) |")
    lines.append(f"| Health | {_health_indicator(total_done, total_tasks)} |")
    lines.append("")


def _emit_usage(result: OvernightResult, lines: list[str]) -> None:
    """Emit usage summary section (Rondo-REQ-101 req 36)."""
    total_input_tokens = sum(u.input_tokens for pr in result.phase_results for u in pr.usage)
    total_output_tokens = sum(u.output_tokens for pr in result.phase_results for u in pr.usage)
    total_tokens = total_input_tokens + total_output_tokens
    watchdog_count = sum(1 for e in result.event_log if e.get("type") == "watchdog_kill")

    lines.append("## Usage")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Total cost | ${result.total_cost_usd:.2f} |")
    lines.append(f"| Input tokens | {total_input_tokens:,} |")
    lines.append(f"| Output tokens | {total_output_tokens:,} |")
    lines.append(f"| Total tokens | {total_tokens:,} |")
    lines.append(f"| Watchdog interventions | {watchdog_count} |")
    lines.append("")


def _emit_phases(result: OvernightResult, lines: list[str]) -> None:
    """Emit per-phase sections (Rondo-REQ-101 reqs 30-31)."""
    lines.append("## Phases")
    lines.append("")

    for pr in result.phase_results:
        phase_done = sum(1 for tr in pr.task_results if tr.status == "done")
        phase_errors = sum(1 for tr in pr.task_results if tr.status == "error")
        phase_skipped = sum(1 for tr in pr.task_results if tr.status == "skipped")
        phase_total = len(pr.task_results)
        health = _health_indicator(phase_done, phase_total)

        lines.append(f"### {pr.round_name} — {health}")
        lines.append("")
        lines.append("| Stat | Value |")
        lines.append("|------|-------|")
        lines.append(f"| Tasks done | {phase_done} |")
        lines.append(f"| Tasks failed | {phase_errors} |")
        lines.append(f"| Tasks skipped | {phase_skipped} |")
        lines.append(f"| Total tasks | {phase_total} |")
        lines.append(f"| Duration | {_format_duration(pr.duration_sec)} ({pr.duration_sec:.1f}s) |")
        lines.append("")


def _emit_action_items(result: OvernightResult, lines: list[str]) -> None:
    """Emit action items section (Rondo-REQ-101 req 33)."""
    action_items: list[str] = []
    for pr in result.phase_results:
        for tr in pr.task_results:
            if tr.status in ("error", "blocked"):
                detail = tr.error_message or tr.status
                # -- FIX-674: include recovery guidance from ErrorPayload if present
                recovery = ""
                if tr.error_payload and tr.error_payload.recovery:
                    recovery = f" **Recovery:** {tr.error_payload.recovery}"
                action_items.append(f"- **{pr.round_name}/{tr.task_name}** [{tr.status}]: {detail}{recovery}")

    # -- Count skipped tasks for accurate messaging
    total_done = sum(1 for pr in result.phase_results for tr in pr.task_results if tr.status == "done")
    total_skipped = sum(1 for pr in result.phase_results for tr in pr.task_results if tr.status == "skipped")
    total_tasks = sum(len(pr.task_results) for pr in result.phase_results)

    lines.append("## Action Items")
    lines.append("")
    if action_items:
        lines.append(f"{len(action_items)} action item(s):")
        lines.append("")
        lines.extend(action_items)
    elif total_skipped == total_tasks and total_tasks > 0:
        lines.append("All tasks skipped (dry-run or gate block). No dispatches executed.")
    elif total_done == total_tasks:
        lines.append("No action items — all tasks completed successfully.")
    elif total_tasks == 0:
        lines.append("No tasks were scheduled.")
    else:
        lines.append("No errors or blocks, but not all tasks completed. Check phase details.")
    lines.append("")


# ──────────────────────────────────────────────────────────────────
#  save_report() — Rondo-REQ-101 req 34
# ──────────────────────────────────────────────────────────────────


def save_report(
    result: OvernightResult,
    config: RondoConfig,
) -> str:
    """Save morning report to dated markdown file.

    Rondo-REQ-101 req 34: rondo-morning-YYYYMMDD.md.
    """
    report = generate_report(result)

    out_dir = Path(config.report_dir)
    out_dir.mkdir(parents=True, exist_ok=True, mode=0o700)

    date_str = datetime.now(UTC).strftime("%Y%m%d")
    filename = f"rondo-morning-{date_str}.md"
    filepath = out_dir / filename

    filepath.write_text(report, encoding="utf-8")
    return str(filepath)


# -- sig: mgh-6201.cd.bd955f.cc6f.2da0e6
