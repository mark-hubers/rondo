#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Mark G. Hubers / HubersTech
# SPDX-License-Identifier: LicenseRef-Proprietary
"""Knowledge Mining Round — extract knowledge from conversations.

Dispatches Claude to read recent chat history and extract:
decisions, patterns, corrections, and insights worth preserving.
This is the self-learning loop: conversations → structured knowledge.

Created: 2026-03-13 (Session 75)
Author: Mark Hubers — HubersTech
"""

from rondo.engine import Gate, Round, Task


def build_knowledge_round() -> Round:
   """Build a knowledge mining round.

   Reads recent conversation data and extracts structured knowledge
   that persists across sessions.
   """
   return Round(
      name="knowledge-mine",
      round_num=0,
      description="Extract knowledge from recent conversations",

      pre_gates=[
         Gate(
            name="Chat DB accessible",
            description="Claude Code chat database must be readable",
            check_fn=lambda **_kw: (True, "Assumed accessible"),
            blocking=False,
         ),
      ],

      tasks=[
         ## -- 1. Decision extraction (opus — needs judgment)
         Task(
            name="Extract Decisions",
            description="Find decisions made in recent sessions",
            instruction="Read ace/ACE-JOURNAL.md (last 100 lines). "
                        "Extract any architecture decisions, design choices, "
                        "or policy changes. For each decision: "
                        "what was decided, why, what alternatives were rejected. "
                        "Format as DEC-NNN entries if they're significant enough.",
            context_files=["ace/ACE-JOURNAL.md"],
            done_when="Decisions extracted with context, or 'no new decisions'",
            model="opus",
         ),

         ## -- 2. Correction extraction (opus — needs understanding)
         Task(
            name="Extract Corrections",
            description="Find mistakes and corrections from recent work",
            instruction="Read ace/ACE-JOURNAL.md (last 100 lines). "
                        "Find instances where: "
                        "1) An approach was tried and abandoned (why?) "
                        "2) A bug was found during review (what class of bug?) "
                        "3) Mark corrected Claude's behavior (what rule was learned?) "
                        "These become feedback memories to prevent repeating mistakes.",
            context_files=["ace/ACE-JOURNAL.md"],
            done_when="Corrections catalogued with lesson learned, or 'no new corrections'",
            model="opus",
         ),

         ## -- 3. Pattern recognition (opus — synthesis)
         Task(
            name="Recognize Patterns",
            description="Find recurring patterns across sessions",
            instruction="Read ace/ACE-JOURNAL.md (last 200 lines). "
                        "Look for patterns: "
                        "1) What tasks keep recurring? (indicates automation opportunity) "
                        "2) What questions keep being asked? (indicates missing docs) "
                        "3) What workflows are followed repeatedly? (indicates round candidate) "
                        "4) What takes the most time? (indicates optimization target)",
            context_files=["ace/ACE-JOURNAL.md"],
            done_when="Patterns listed with frequency and automation potential",
            model="opus",
         ),

         ## -- 4. Spec gap detection (sonnet — cross-reference)
         Task(
            name="Spec Gap Detection",
            description="Find work being done that has no spec",
            instruction="Read ace/ACE-JOURNAL.md (last 100 lines). "
                        "Compare work described to known specs in ace/specs/ and orbital/specs/. "
                        "Is any significant work happening that isn't covered by an existing spec? "
                        "Flag as potential new spec candidates.",
            context_files=["ace/ACE-JOURNAL.md"],
            done_when="Spec gaps identified or confirmed coverage is complete",
            model="sonnet",
         ),

         ## -- 5. Memory freshness (sonnet — compare)
         Task(
            name="Memory Freshness",
            description="Check if project memories are current",
            instruction="Read the memory index file. "
                        "For each memory: is it still accurate based on recent journal entries? "
                        "Flag any memories that are outdated, contradicted by recent work, "
                        "or missing information from recent sessions.",
            context_files=[
               "ace/ACE-JOURNAL.md",
            ],
            done_when="Memory freshness report: current/stale/missing per entry",
            model="sonnet",
         ),

         ## -- 6. Knowledge synthesis (opus — big picture)
         Task(
            name="Knowledge Synthesis",
            description="Synthesize findings into actionable items",
            instruction="Based on all previous extractions: "
                        "1) Top 3 decisions to formalize (need DEC record) "
                        "2) Top 3 corrections to save as feedback memories "
                        "3) Top 3 patterns to automate (Rondo round candidates) "
                        "4) Any spec gaps to address "
                        "5) Any stale memories to update. "
                        "Prioritize by impact.",
            context_files=["ace/ACE-JOURNAL.md"],
            done_when="Prioritized action list from knowledge mining",
            model="opus",
         ),
      ],

      post_gates=[
         Gate(
            name="Knowledge extracted",
            description="Mining round complete",
            check_fn=lambda **_kw: (True, "Recorded by runner"),
         ),
      ],
   )
