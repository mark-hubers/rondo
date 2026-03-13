#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Mark G. Hubers / HubersTech
# SPDX-License-Identifier: LicenseRef-Proprietary
"""Rondo Overnight — scheduled batch dispatch.

The overnight workhorse. Runs a configurable set of rounds across
all specs using Max plan capacity. Generates morning report.

Designed to be called from cron/LaunchAgent at ~10pm:
   python3 -m rondo.overnight               # default: health + digest
   python3 -m rondo.overnight --full        # all rounds
   python3 -m rondo.overnight --quick       # just health check

Rounds executed (in order):
   1. spec-health    — all OB specs (32 × 8 = 256 tasks)
   2. digest-refresh — all specs with stale digests
   3. convention     — full codebase scan
   4. knowledge-mine — extract from recent conversations
   5. morning report — aggregate all results

Created: 2026-03-13 (Session 75)
Author: Mark Hubers — HubersTech
"""

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from rondo.report import generate_report  # noqa: E402
from rondo.runner import _find_ob_specs, run_full_round  # noqa: E402

OVERNIGHT_LOG = Path(_PROJECT_ROOT) / "reports" / "rondo-results" / "overnight-log.json"


def _now() -> str:
    """ISO timestamp."""
    return datetime.now(UTC).isoformat()


def _log_event(event: str, details: str = "") -> None:
    """Append to overnight log."""
    log = []
    if OVERNIGHT_LOG.exists():
        try:
            log = json.loads(OVERNIGHT_LOG.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            log = []
    log.append({"time": _now(), "event": event, "details": details})
    ## -- Keep last 100 entries
    log = log[-100:]
    OVERNIGHT_LOG.write_text(json.dumps(log, indent=2), encoding="utf-8")


def run_overnight(mode: str = "default", workers: int = 1, auth: str = "max") -> dict:
    """Run overnight batch.

    Args:
       mode: "quick" (health only), "default" (health + digest + convention),
             "full" (all rounds including knowledge-mine)
       workers: Concurrent tasks (1 = sequential, safe default)
       auth: Auth mode

    Returns:
       Summary dict
    """
    start = datetime.now(UTC)
    _log_event("overnight_start", f"mode={mode}, workers={workers}, auth={auth}")

    print(f"\n  {'═' * 60}")
    print("  RONDO OVERNIGHT RUN")
    print(f"  Mode: {mode}  Auth: {'Max plan' if auth == 'max' else 'API key'}")
    print(f"  Started: {start.strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"  {'═' * 60}")

    all_summaries = []
    ob_specs = _find_ob_specs()

    ## -- Phase 1: Spec Health (always runs)
    print(f"\n  ── PHASE 1: Spec Health ({len(ob_specs)} OB specs) ──")
    from rondo.rounds.spec_health import build_spec_health_round

    for spec_id, spec_path in ob_specs:
        try:
            round_def = build_spec_health_round(spec_id, spec_path)
            summary = run_full_round(
                round_def,
                auth=auth,
                spec_id=spec_id,
                spec_path=spec_path,
            )
            all_summaries.append(summary)
        except Exception as e:
            _log_event("error", f"spec-health {spec_id}: {e}")
            print(f"  ✗ Error on {spec_id}: {e}")

    if mode == "quick":
        _log_event("overnight_end", f"quick mode, {len(all_summaries)} rounds")
        return _finish(all_summaries, start)

    ## -- Phase 2: Convention Check
    print("\n  ── PHASE 2: Convention Check ──")
    try:
        from rondo.rounds.convention_check import build_convention_round

        round_def = build_convention_round()
        summary = run_full_round(round_def, auth=auth, spec_id="project")
        all_summaries.append(summary)
    except Exception as e:
        _log_event("error", f"convention: {e}")
        print(f"  ✗ Error on convention check: {e}")

    ## -- Phase 3: Digest Refresh (top 10 stalest specs)
    print("\n  ── PHASE 3: Digest Refresh (OB specs) ──")
    from rondo.rounds.digest_refresh import build_digest_round

    for spec_id, spec_path in ob_specs[:10]:
        try:
            round_def = build_digest_round(spec_id, spec_path)
            summary = run_full_round(
                round_def,
                auth=auth,
                spec_id=spec_id,
                spec_path=spec_path,
            )
            all_summaries.append(summary)
        except Exception as e:
            _log_event("error", f"digest {spec_id}: {e}")

    if mode == "default":
        _log_event("overnight_end", f"default mode, {len(all_summaries)} rounds")
        return _finish(all_summaries, start)

    ## -- Phase 4: Knowledge Mining (full mode only)
    print("\n  ── PHASE 4: Knowledge Mining ──")
    try:
        from rondo.rounds.knowledge_mine import build_knowledge_round

        round_def = build_knowledge_round()
        summary = run_full_round(round_def, auth=auth, spec_id="project")
        all_summaries.append(summary)
    except Exception as e:
        _log_event("error", f"knowledge: {e}")

    ## -- Phase 5: Test Gap Analysis (full mode only)
    print("\n  ── PHASE 5: Test Gap Analysis ──")
    try:
        from rondo.rounds.test_gaps import build_test_gap_round

        round_def = build_test_gap_round()
        summary = run_full_round(round_def, auth=auth, spec_id="project")
        all_summaries.append(summary)
    except Exception as e:
        _log_event("error", f"test-gaps: {e}")

    _log_event("overnight_end", f"full mode, {len(all_summaries)} rounds")
    return _finish(all_summaries, start)


def _finish(summaries: list[dict], start: datetime) -> dict:
    """Generate morning report and return summary."""
    end = datetime.now(UTC)
    duration = (end - start).total_seconds()

    ## -- Generate morning report
    report = generate_report(summaries)
    print(f"\n{'report'}")

    ## -- Save report
    stamp = end.strftime("%Y%m%d")
    report_path = Path(_PROJECT_ROOT) / "reports" / f"rondo-morning-{stamp}.md"
    report_path.write_text(report, encoding="utf-8")
    print(f"\n  Morning report saved: {report_path}")

    total_done = sum(s.get("tasks_done", 0) for s in summaries)
    total_error = sum(s.get("tasks_error", 0) for s in summaries)

    print(f"\n  {'═' * 60}")
    print("  OVERNIGHT COMPLETE")
    print(f"  Duration: {duration / 3600:.1f}h ({duration / 60:.0f}m)")
    print(f"  Rounds: {len(summaries)}")
    print(f"  Tasks: {total_done} done, {total_error} errors")
    print(f"  Report: {report_path}")
    print(f"  {'═' * 60}\n")

    return {
        "mode": "overnight",
        "duration_sec": duration,
        "rounds": len(summaries),
        "tasks_done": total_done,
        "tasks_error": total_error,
        "report_path": str(report_path),
    }


def main() -> None:
    """CLI: overnight batch."""
    parser = argparse.ArgumentParser(description="Rondo Overnight — scheduled batch dispatch")
    parser.add_argument(
        "--mode",
        choices=["quick", "default", "full"],
        default="default",
        help="quick=health only, default=health+digest+convention, full=everything",
    )
    parser.add_argument("--auth", choices=["max", "api"], default="max")
    parser.add_argument("--workers", type=int, default=1, help="Concurrent tasks (default: 1 for safety)")

    args = parser.parse_args()
    run_overnight(mode=args.mode, workers=args.workers, auth=args.auth)


if __name__ == "__main__":
    main()
