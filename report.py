#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Mark G. Hubers / HubersTech
# SPDX-License-Identifier: LicenseRef-Proprietary
"""Rondo Report — aggregate results into morning summary.

Reads all round result files and generates a human-readable summary.
Designed to be the first thing Mark sees after overnight Rondo runs.

Usage:
   python3 -m rondo.report                    # latest results
   python3 -m rondo.report --since 2026-03-13 # specific date
   python3 -m rondo.report --round spec-health # specific round type

Created: 2026-03-13 (Session 75)
Author: Mark Hubers — HubersTech
"""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
ROUND_RESULTS_DIR = Path(_PROJECT_ROOT) / "reports" / "rondo-results" / "rounds"


def load_results(since: str | None = None, round_type: str | None = None) -> list[dict]:
   """Load round result files, optionally filtered."""
   if not ROUND_RESULTS_DIR.exists():
      return []

   results = []
   for f in sorted(ROUND_RESULTS_DIR.glob("*.json"), reverse=True):
      try:
         data = json.loads(f.read_text(encoding="utf-8"))
      except (json.JSONDecodeError, OSError):
         continue

      ## -- Filter by round type
      if round_type and data.get("round_name") != round_type:
         continue

      ## -- Filter by date
      if since:
         ts = data.get("timestamp", "")
         if ts < since:
            continue

      results.append(data)

   return results


def generate_report(results: list[dict]) -> str:
   """Generate a summary report from round results."""
   if not results:
      return "No Rondo results found.\n"

   lines = []
   lines.append("═" * 60)
   lines.append("RONDO MORNING REPORT")
   lines.append(f"Generated: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}")
   lines.append(f"Results: {len(results)} round(s)")
   lines.append("═" * 60)

   ## -- Group by round type
   by_round: dict[str, list[dict]] = {}
   for r in results:
      rname = r.get("round_name", "unknown")
      by_round.setdefault(rname, []).append(r)

   for round_name, round_results in sorted(by_round.items()):
      lines.append("")
      lines.append(f"── {round_name.upper()} ({len(round_results)} spec(s)) ──")
      lines.append("")

      total_done = 0
      total_blocked = 0
      total_error = 0
      total_time = 0.0

      for r in round_results:
         spec = r.get("spec_id", "?")
         done = r.get("tasks_done", 0)
         blocked = r.get("tasks_blocked", 0)
         error = r.get("tasks_error", 0)
         dur = r.get("total_duration_sec", 0)

         total_done += done
         total_blocked += blocked
         total_error += error
         total_time += dur

         ## -- Color-code status
         if error > 0:
            icon = "✗"
            health = "RED"
         elif blocked > 0:
            icon = "⚠"
            health = "YELLOW"
         else:
            icon = "✓"
            health = "GREEN"

         lines.append(f"  {icon} {spec:12s} {health:7s} │ {done} done, {blocked} blocked, {error} error │ {dur:.0f}s")

         ## -- Show task results for non-green specs
         if health != "GREEN" and "tasks" in r:
            for t in r["tasks"]:
               if t.get("status") in ("blocked", "error"):
                  lines.append(f"     └─ {t.get('task_name', '?')}: {t.get('result', '')[:80]}")

      lines.append("")
      lines.append(f"  Totals: {total_done} done, {total_blocked} blocked, {total_error} error")
      lines.append(f"  Time: {total_time:.0f}s ({total_time/60:.1f}m)")

   ## -- Overall summary
   all_done = sum(r.get("tasks_done", 0) for r in results)
   all_blocked = sum(r.get("tasks_blocked", 0) for r in results)
   all_error = sum(r.get("tasks_error", 0) for r in results)
   all_time = sum(r.get("total_duration_sec", 0) for r in results)

   lines.append("")
   lines.append("═" * 60)
   lines.append("OVERALL")
   lines.append(f"  ✓ Done: {all_done}  ⚠ Blocked: {all_blocked}  ✗ Error: {all_error}")
   lines.append(f"  Total time: {all_time:.0f}s ({all_time/60:.1f}m)")

   ## -- Action items
   blocked_tasks = []
   for r in results:
      for t in r.get("tasks", []):
         if t.get("status") == "blocked":
            blocked_tasks.append(f"  → {r.get('spec_id', '?')}: {t.get('task_name', '?')} — {t.get('result', '')[:60]}")

   if blocked_tasks:
      lines.append("")
      lines.append("ACTION ITEMS (blocked tasks need human input):")
      lines.extend(blocked_tasks[:10])
      if len(blocked_tasks) > 10:
         lines.append(f"  ... and {len(blocked_tasks) - 10} more")

   lines.append("═" * 60)
   return "\n".join(lines)


def main() -> None:
   """CLI: generate morning report."""
   parser = argparse.ArgumentParser(description="Rondo Report — morning summary")
   parser.add_argument("--since", default=None, help="Only results since date (YYYY-MM-DD)")
   parser.add_argument("--round", default=None, help="Filter by round type")
   parser.add_argument("--save", action="store_true", help="Save report to file")
   args = parser.parse_args()

   results = load_results(since=args.since, round_type=args.round)
   report = generate_report(results)
   print(report)

   if args.save:
      stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
      report_path = Path(_PROJECT_ROOT) / "reports" / f"rondo-morning-{stamp}.md"
      report_path.write_text(report, encoding="utf-8")
      print(f"\n  Saved: {report_path}")


if __name__ == "__main__":
   main()
