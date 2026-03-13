#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Mark G. Hubers / HubersTech
# SPDX-License-Identifier: LicenseRef-Proprietary
"""Rondo Engine — the conductor that runs rounds.

Every round has 3 phases: PRE (entry gates), MAIN (tasks), POST (recording).
Tasks can be automated (Python checks) or interactive (instructions to Claude).
Progress tracked in DB, survives compaction, queryable anytime.

Python is the conductor. Claude is the orchestra.

Usage:
   from rondo.engine import Round, Task, Gate, run_round

   round_def = Round(
      name="design",
      round_num=2,
      pre_gates=[Gate("Prior round done", check_fn=...)],
      tasks=[
         Task("Check scope", auto_fn=scan_scope),       # automated
         Task("Review tables", instruction="..."),        # interactive
      ],
      post_gates=[Gate("DB recorded", check_fn=...)],
   )

   run_round(round_def, project="ACE", spec_id="OB-01")

Created: 2026-03-12 (Session 74)
Moved to rondo/: 2026-03-13 (Session 75)
Author: Mark Hubers — HubersTech
Spec: OB-08 (Round Lifecycle)
"""

import json
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path

## -- Project root for imports
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
   sys.path.insert(0, _PROJECT_ROOT)

from scripts.ob_queries import get_connection  # noqa: E402
from scripts.ob_queries import planning_gates as pg_queries  # noqa: E402
from scripts.status_output import error_msg, pass_msg, warn_msg  # noqa: E402

# ═══════════════════════════════════════════════════════════════════════
# ENUMS
# ═══════════════════════════════════════════════════════════════════════

class TaskStatus(Enum):
   """Status of a task in a round."""

   PENDING = "pending"
   RUNNING = "running"
   PASSED = "passed"
   FAILED = "failed"
   SKIPPED = "skipped"


class TaskMode(Enum):
   """How the task gets executed."""

   AUTO = "auto"              ## -- Python function runs it
   INTERACTIVE = "interactive" ## -- Claude follows instructions


# ═══════════════════════════════════════════════════════════════════════
# DATA MODELS
# ═══════════════════════════════════════════════════════════════════════

def _now() -> str:
   """ISO 8601 UTC timestamp."""
   return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")


@dataclass
class Gate:
   """A guardrail gate — must pass before/after round work.

   Gates are BLOCKING by default. If a gate fails and blocking=True,
   the round stops.
   """

   name: str
   description: str
   check_fn: object = None     ## -- Callable that returns (passed: bool, evidence: str)
   blocking: bool = True
   passed: bool | None = None  ## -- None = not checked yet
   evidence: str = ""

   def check(self, **kwargs: object) -> bool:
      """Run the gate check function."""
      if self.check_fn is None:
         self.passed = True
         self.evidence = "No check function — auto-pass"
         return True
      passed, evidence = self.check_fn(**kwargs)
      self.passed = passed
      self.evidence = evidence
      return passed


@dataclass
class Task:
   """A single task in a round.

   Automated tasks have an auto_fn that returns (passed, result_text).
   Interactive tasks have an instruction that tells Claude what to do.
   Both track status, duration, and evidence.
   """

   name: str
   description: str = ""

   ## -- For automated tasks
   auto_fn: object = None       ## -- Callable returning (passed: bool, detail: str)

   ## -- For interactive tasks (instructions TO Claude)
   instruction: str = ""        ## -- What Claude should do
   context_files: list[str] = field(default_factory=list)  ## -- Files to read first
   done_when: str = ""          ## -- How to know it's complete

   ## -- Dispatch hints (round author recommends, CLI can override)
   model: str = "sonnet"        ## -- opus, sonnet, haiku
   effort: str = "high"         ## -- low, medium, high, max

   ## -- State
   mode: TaskMode = TaskMode.AUTO
   status: TaskStatus = TaskStatus.PENDING
   result: str = ""
   started_at: str = ""
   completed_at: str = ""

   def __post_init__(self) -> None:
      """Auto-detect mode from what's provided."""
      if self.instruction and not self.auto_fn:
         self.mode = TaskMode.INTERACTIVE
      elif self.auto_fn:
         self.mode = TaskMode.AUTO

   def run(self, **kwargs: object) -> bool:
      """Execute an automated task. Returns True if passed."""
      if self.mode != TaskMode.AUTO or self.auto_fn is None:
         return False
      self.status = TaskStatus.RUNNING
      self.started_at = _now()
      try:
         passed, detail = self.auto_fn(**kwargs)
         self.status = TaskStatus.PASSED if passed else TaskStatus.FAILED
         self.result = detail
      except Exception as e:
         self.status = TaskStatus.FAILED
         self.result = f"Exception: {e}"
         passed = False
      self.completed_at = _now()
      return passed

   def mark_done(self, evidence: str = "") -> None:
      """Mark an interactive task as complete (Claude did it)."""
      self.status = TaskStatus.PASSED
      self.result = evidence or "Marked complete"
      self.completed_at = _now()

   def mark_skipped(self, reason: str = "") -> None:
      """Skip a task with reason."""
      self.status = TaskStatus.SKIPPED
      self.result = reason or "Skipped"
      self.completed_at = _now()

   def to_prompt(self) -> str:
      """Serialize task to a prompt string for Mode 2/3 dispatch."""
      parts = []
      if self.context_files:
         parts.append(f"Read: {', '.join(self.context_files)}")
      if self.instruction:
         parts.append(f"Do: {self.instruction}")
      if self.done_when:
         parts.append(f"Done when: {self.done_when}")
      return "\n".join(parts)


@dataclass
class Round:
   """A complete round definition: pre-gates + tasks + post-gates.

   This is the BLUEPRINT. Create one per round type (survey, design, etc.).
   The run_round() function executes it.
   """

   name: str
   round_num: int
   description: str = ""

   pre_gates: list[Gate] = field(default_factory=list)
   tasks: list[Task] = field(default_factory=list)
   post_gates: list[Gate] = field(default_factory=list)

   @property
   def tasks_done(self) -> int:
      """Count of completed tasks."""
      return sum(1 for t in self.tasks if t.status in (TaskStatus.PASSED, TaskStatus.SKIPPED))

   @property
   def tasks_total(self) -> int:
      """Total task count."""
      return len(self.tasks)

   @property
   def tasks_pending(self) -> list[Task]:
      """Tasks not yet done."""
      return [t for t in self.tasks if t.status == TaskStatus.PENDING]

   @property
   def next_task(self) -> Task | None:
      """Next pending task, or None if all done."""
      pending = self.tasks_pending
      return pending[0] if pending else None


# ═══════════════════════════════════════════════════════════════════════
# ROUND RUNNER — the engine
# ═══════════════════════════════════════════════════════════════════════

def run_round(
   round_def: Round,
   project: str = "ACE",
   orbit: int = 1,
   spec_id: str | None = None,
   dry_run: bool = False,
) -> Round:
   """Execute a round: PRE → MAIN → POST.

   For automated tasks: runs them immediately.
   For interactive tasks: prints instructions and waits for mark_done().

   Args:
      round_def: The round blueprint to execute.
      project: Project key.
      orbit: Orbit number.
      spec_id: Optional spec scope (e.g., "OB-01").
      dry_run: If True, don't write to DB.

   Returns:
      The round_def with updated task/gate statuses.
   """
   scope = f" — {spec_id}" if spec_id else ""
   print(f"\n  {'═'*60}")
   print(f"  ROUND {round_def.round_num}: {round_def.name.upper()}{scope}")
   print(f"  {round_def.description}")
   print(f"  {'═'*60}")

   kwargs = {"project": project, "orbit": orbit, "spec_id": spec_id}

   ## ── PHASE 1: PRE-GATES ──────────────────────────────────────────
   if round_def.pre_gates:
      print("\n  PRE-CHECK")
      print(f"  {'─'*50}")
      for gate in round_def.pre_gates:
         gate.check(**kwargs)
         mark = "✓" if gate.passed else "✗"
         print(f"  {mark} {gate.name}: {gate.evidence}")
         if not gate.passed and gate.blocking:
            error_msg(f"BLOCKED — {gate.name} failed. Cannot proceed.")
            return round_def

   ## ── PHASE 2: AUTO TASKS ──────────────────────────────────────────
   auto_tasks = [(i, t) for i, t in enumerate(round_def.tasks, 1) if t.mode == TaskMode.AUTO]
   interactive_tasks = [(i, t) for i, t in enumerate(round_def.tasks, 1) if t.mode == TaskMode.INTERACTIVE]

   print(f"\n  AUTO CHECKS ({len(auto_tasks)} tasks — Python verifies)")
   print(f"  {'─'*50}")

   for i, task in auto_tasks:
      passed = task.run(**kwargs)
      mark = "✓" if passed else "✗"
      print(f"  {mark} Task {i}/{round_def.tasks_total}: {task.name} — {task.result}")

   ## ── PHASE 2b: INTERACTIVE TASKS (Claude's work) ───────────────
   print(f"\n  {'═'*50}")
   print(f"  INTERACTIVE TASKS ({len(interactive_tasks)} — WAITING FOR CLAUDE)")
   print(f"  {'═'*50}")

   for i, task in interactive_tasks:
      _print_task(i, round_def.tasks_total, task)
      print()

   ## ── PHASE 3: POST-GATES ─────────────────────────────────────────
   if round_def.post_gates:
      if round_def.tasks_pending:
         ## -- Don't run post-gates when work is still pending
         print(f"\n  POST-CHECK — SKIPPED ({len(round_def.tasks_pending)} tasks still pending)")
      else:
         print("\n  POST-CHECK")
         print(f"  {'─'*50}")
         for gate in round_def.post_gates:
            gate.check(**kwargs)
            mark = "✓" if gate.passed else "✗"
            print(f"  {mark} {gate.name}: {gate.evidence}")

   ## ── SUMMARY ─────────────────────────────────────────────────────
   _print_summary(round_def)

   ## ── RECORD ──────────────────────────────────────────────────────
   if not dry_run:
      _record_to_db(round_def, project, orbit)
   else:
      warn_msg("DRY RUN — not recording in DB")

   return round_def


def resume_round(round_def: Round) -> None:
   """Show where we are after compaction — the COMPACTION KILLER.

   Claude runs this after context is lost. It shows:
   - What's done (green)
   - What's next (with full instructions)
   - What's pending (count)
   """
   print(f"\n  {'═'*60}")
   print(f"  RESUMING ROUND {round_def.round_num}: {round_def.name.upper()}")
   print(f"  {'═'*60}")

   ## -- Show completed tasks
   done = [t for t in round_def.tasks if t.status in (TaskStatus.PASSED, TaskStatus.SKIPPED)]
   next_task = round_def.next_task

   print(f"\n  Progress: {len(done)}/{round_def.tasks_total} tasks complete")
   print(f"  {'─'*50}")

   for i, task in enumerate(round_def.tasks, 1):
      if task.status == TaskStatus.PASSED:
         print(f"  ✓ Task {i}/{round_def.tasks_total}: {task.name}")
      elif task.status == TaskStatus.SKIPPED:
         print(f"  ⊘ Task {i}/{round_def.tasks_total}: {task.name} (skipped: {task.result})")
      elif task == next_task:
         print(f"  → Task {i}/{round_def.tasks_total}: {task.name}  ← YOU ARE HERE")
      else:
         print(f"    Task {i}/{round_def.tasks_total}: {task.name}")

   ## -- Show next task instructions
   if next_task:
      print()
      _print_task(
         round_def.tasks.index(next_task) + 1,
         round_def.tasks_total,
         next_task,
      )
   else:
      print()
      pass_msg("All tasks complete — ready for POST-CHECK")


# ═══════════════════════════════════════════════════════════════════════
# DISPLAY HELPERS
# ═══════════════════════════════════════════════════════════════════════

def _print_task(num: int, total: int, task: Task) -> None:
   """Print a task with its instructions."""
   mode_tag = "AUTO" if task.mode == TaskMode.AUTO else "INTERACTIVE"
   status_tag = task.status.value.upper()

   print(f"  {'─'*50}")
   print(f"  📋 Task {num}/{total}: {task.name}  [{mode_tag}] [{status_tag}]")

   if task.description:
      print(f"     {task.description}")

   if task.context_files:
      print(f"     Read:  {', '.join(task.context_files)}")

   if task.instruction:
      print(f"     Do:    {task.instruction}")

   if task.done_when:
      print(f"     Done:  {task.done_when}")

   if task.status == TaskStatus.PASSED:
      print(f"     ✓ Result: {task.result}")


def _print_summary(round_def: Round) -> None:
   """Print round summary with stats."""
   done = sum(1 for t in round_def.tasks if t.status == TaskStatus.PASSED)
   failed = sum(1 for t in round_def.tasks if t.status == TaskStatus.FAILED)
   skipped = sum(1 for t in round_def.tasks if t.status == TaskStatus.SKIPPED)
   pending = sum(1 for t in round_def.tasks if t.status == TaskStatus.PENDING)
   auto_count = sum(1 for t in round_def.tasks if t.mode == TaskMode.AUTO)
   interactive_count = sum(1 for t in round_def.tasks if t.mode == TaskMode.INTERACTIVE)

   print(f"\n  {'═'*60}")
   print(f"  ROUND {round_def.round_num} SUMMARY: {round_def.name.upper()}")
   print(f"  {'─'*50}")
   print(f"  {'Tasks total:':<25} {round_def.tasks_total}")
   print(f"  {'  Automated:':<25} {auto_count}")
   print(f"  {'  Interactive:':<25} {interactive_count}")
   print(f"  {'─'*50}")
   print(f"  {'✓ Passed:':<25} {done}")
   print(f"  {'✗ Failed:':<25} {failed}")
   print(f"  {'⊘ Skipped:':<25} {skipped}")
   print(f"  {'⏳ Pending:':<25} {pending}")
   print(f"  {'═'*60}\n")


# ═══════════════════════════════════════════════════════════════════════
# DB RECORDING
# ═══════════════════════════════════════════════════════════════════════

def _record_to_db(round_def: Round, project: str, orbit: int) -> None:
   """Save round results to planning_rounds and planning_gates."""
   try:
      with get_connection() as conn:
         all_gates = round_def.pre_gates + round_def.post_gates
         gates_passed = sum(1 for g in all_gates if g.passed)

         conn.execute(
            """INSERT INTO planning_rounds
            (orbit, round, round_name, status, specs_touched,
             findings_count, gates_passed, gates_total,
             golden_numbers_checked, started_at, completed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
               orbit,
               round_def.round_num,
               round_def.name,
               "done" if round_def.tasks_done == round_def.tasks_total else "in_progress",
               round_def.tasks_total,
               sum(1 for t in round_def.tasks if t.status == TaskStatus.FAILED),
               gates_passed,
               len(all_gates),
               "yes",
               _now(),
               _now() if round_def.tasks_done == round_def.tasks_total else None,
            ),
         )
         round_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

         for g in all_gates:
            if g.passed is not None:
               pg_queries.insert(
                  conn,
                  planning_round_id=round_id,
                  gate_num=0,
                  gate_name=g.name,
                  status="pass" if g.passed else "fail",
                  evidence=g.evidence,
               )

         conn.commit()
         pass_msg(f"Recorded in DB: planning_rounds id={round_id}")

   except Exception as e:
      error_msg(f"Failed to record: {e}")


# ═══════════════════════════════════════════════════════════════════════
# SERIALIZATION — save/load round state (compaction-proof)
# ═══════════════════════════════════════════════════════════════════════

def save_round_state(round_def: Round, path: Path) -> None:
   """Save round progress to JSON file (compaction-proof).

   After compaction, Claude can load this to see exactly where we are.
   """
   state = {
      "name": round_def.name,
      "round_num": round_def.round_num,
      "saved_at": _now(),
      "tasks": [
         {
            "name": t.name,
            "mode": t.mode.value,
            "status": t.status.value,
            "result": t.result,
            "instruction": t.instruction,
            "done_when": t.done_when,
         }
         for t in round_def.tasks
      ],
   }
   path.write_text(json.dumps(state, indent=2), encoding="utf-8")
   pass_msg(f"Round state saved to {path}")


def load_round_state(round_def: Round, path: Path) -> Round:
   """Load round progress from JSON, update task statuses.

   Claude calls this after compaction to restore where we were.
   """
   state = json.loads(path.read_text(encoding="utf-8"))

   for saved_task in state["tasks"]:
      for task in round_def.tasks:
         if task.name == saved_task["name"]:
            task.status = TaskStatus(saved_task["status"])
            task.result = saved_task["result"]
            break

   pass_msg(f"Round state loaded from {path} (saved {state['saved_at']})")
   return round_def
