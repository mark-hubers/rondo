"""Rondo report — morning report generator.

REQ-002 reqs 29-36.
Consumes OvernightResult, produces markdown report.

Import direction:
    engine.py → (no rondo imports)
    config.py → (no rondo imports)
    overnight.py → imports engine + config + runner
    report.py → imports engine + config + overnight (types only)
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from rondo.config import RondoConfig
from rondo.overnight import OvernightResult

# ──────────────────────────────────────────────────────────────────
#  Health indicator — REQ-002 req 32
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
#  generate_report() — REQ-002 reqs 29-36
# ──────────────────────────────────────────────────────────────────


def generate_report(result: OvernightResult) -> str:
    """Generate morning report markdown from OvernightResult.

    REQ-002 req 29: aggregate results from all phases.
    REQ-002 req 30: group by round type.
    REQ-002 req 31: round stats (done, failed, duration).
    REQ-002 req 32: health indicators.
    REQ-002 req 33: action items (failed/blocked tasks).
    REQ-002 req 35: totals (duration, tasks, errors, timestamp).
    REQ-002 req 36: usage summary (cost, tokens, watchdog).
    """
    lines: list[str] = []
    _emit_header(result, lines)
    _emit_summary(result, lines)
    _emit_usage(result, lines)
    _emit_phases(result, lines)
    _emit_action_items(result, lines)
    return "\n".join(lines)


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
    """Emit totals section (REQ-002 req 35)."""
    total_tasks = sum(len(pr.task_results) for pr in result.phase_results)
    total_done = sum(1 for pr in result.phase_results for tr in pr.task_results if tr.status == "done")
    total_errors = sum(1 for pr in result.phase_results for tr in pr.task_results if tr.status == "error")
    total_blocked = sum(1 for pr in result.phase_results for tr in pr.task_results if tr.status == "blocked")

    lines.append("## Summary")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Total tasks | {total_tasks} |")
    lines.append(f"| Done | {total_done} |")
    lines.append(f"| Errors | {total_errors} |")
    lines.append(f"| Blocked | {total_blocked} |")
    lines.append(f"| Duration | {_format_duration(result.duration_sec)} ({result.duration_sec:.1f}s) |")
    lines.append(f"| Health | {_health_indicator(total_done, total_tasks)} |")
    lines.append("")


def _emit_usage(result: OvernightResult, lines: list[str]) -> None:
    """Emit usage summary section (REQ-002 req 36)."""
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
    """Emit per-phase sections (REQ-002 reqs 30-31)."""
    lines.append("## Phases")
    lines.append("")

    for pr in result.phase_results:
        phase_done = sum(1 for tr in pr.task_results if tr.status == "done")
        phase_errors = sum(1 for tr in pr.task_results if tr.status == "error")
        phase_total = len(pr.task_results)
        health = _health_indicator(phase_done, phase_total)

        lines.append(f"### {pr.round_name} — {health}")
        lines.append("")
        lines.append("| Stat | Value |")
        lines.append("|------|-------|")
        lines.append(f"| Tasks done | {phase_done} |")
        lines.append(f"| Tasks failed | {phase_errors} |")
        lines.append(f"| Total tasks | {phase_total} |")
        lines.append(f"| Duration | {_format_duration(pr.duration_sec)} ({pr.duration_sec:.1f}s) |")
        lines.append("")


def _emit_action_items(result: OvernightResult, lines: list[str]) -> None:
    """Emit action items section (REQ-002 req 33)."""
    action_items: list[str] = []
    for pr in result.phase_results:
        for tr in pr.task_results:
            if tr.status in ("error", "blocked"):
                detail = tr.error_message or tr.status
                action_items.append(f"- **{pr.round_name}/{tr.task_name}** [{tr.status}]: {detail}")

    lines.append("## Action Items")
    lines.append("")
    if action_items:
        lines.append(f"{len(action_items)} action item(s):")
        lines.append("")
        lines.extend(action_items)
    else:
        lines.append("No action items — all tasks completed successfully.")
    lines.append("")


# ──────────────────────────────────────────────────────────────────
#  save_report() — REQ-002 req 34
# ──────────────────────────────────────────────────────────────────


def save_report(
    result: OvernightResult,
    config: RondoConfig,
) -> str:
    """Save morning report to dated markdown file.

    REQ-002 req 34: rondo-morning-YYYYMMDD.md.
    """
    report = generate_report(result)

    out_dir = Path(config.report_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    date_str = datetime.now(UTC).strftime("%Y%m%d")
    filename = f"rondo-morning-{date_str}.md"
    filepath = out_dir / filename

    filepath.write_text(report, encoding="utf-8")
    return str(filepath)
