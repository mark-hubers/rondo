#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Mark G. Hubers / HubersTech
# SPDX-License-Identifier: LicenseRef-Proprietary
"""Convention Check Round — enforce codebase conventions via AI.

Goes beyond what convention lock tests catch — Claude reviews for
patterns that require judgment: naming consistency, import style,
comment quality, dead code, architecture layer violations.

Created: 2026-03-13 (Session 75)
Author: Mark Hubers — HubersTech
"""

from rondo.engine import Gate, Round, Task


def build_convention_round() -> Round:
   """Build a convention enforcement round."""
   return Round(
      name="convention-check",
      round_num=0,
      description="AI-powered convention enforcement",

      pre_gates=[
         Gate(
            name="Convention tests exist",
            description="tests/test_fix2_conventions.py exists",
            check_fn=lambda **_kw: (True, "Convention lock tests assumed present"),
            blocking=False,
         ),
      ],

      tasks=[
         ## -- 1. Naming conventions (sonnet — pattern matching)
         Task(
            name="Naming Conventions",
            description="Check function/class/variable naming consistency",
            instruction="Scan src/ace2/ and scripts/ for naming violations: "
                        "functions should be snake_case, classes CamelCase, "
                        "constants UPPER_SNAKE. Check that query classes in ob_queries.py "
                        "follow the lowercase namespace pattern. "
                        "Flag any inconsistencies.",
            context_files=["pyproject.toml"],
            done_when="Naming violations listed with file:line or confirmed clean",
            model="sonnet",
         ),

         ## -- 2. Import hygiene (sonnet — structural check)
         Task(
            name="Import Hygiene",
            description="Check for unused imports, circular deps, wrong patterns",
            instruction="Check scripts/ and rondo/ for: "
                        "1) Unused imports (ruff F401 should catch, but verify) "
                        "2) Inline imports that should be top-level "
                        "3) sys.path manipulation (should use pyproject.toml paths) "
                        "4) Circular import risks between ob/, rondo/, scripts/",
            context_files=["pyproject.toml"],
            done_when="Import issues catalogued or confirmed clean",
            model="sonnet",
         ),

         ## -- 3. Dead code detection (sonnet — search + analysis)
         Task(
            name="Dead Code Detection",
            description="Find unused functions, classes, and files",
            instruction="Look for: "
                        "1) Functions in src/ace2/ that are never called (no references) "
                        "2) Files that are never imported "
                        "3) Test files that test deleted functionality "
                        "4) Scripts that are superseded by newer versions. "
                        "Focus on obvious cases, not edge cases.",
            context_files=["pyproject.toml"],
            done_when="Dead code candidates listed with evidence or confirmed minimal",
            model="sonnet",
         ),

         ## -- 4. Comment quality (haiku — simple pattern check)
         Task(
            name="Comment Quality",
            description="Check comment convention compliance",
            instruction="Check rondo/ and scripts/ for comment convention: "
                        "Real comments use '## --' (Python) or '// --' (other). "
                        "Without '--' = disabled code, not a comment. "
                        "Flag any real comments missing the '--' prefix. "
                        "Also flag commented-out code that should be deleted.",
            context_files=["rondo/dispatch.py", "rondo/engine.py"],
            done_when="Comment violations listed or confirmed compliant",
            model="haiku",
         ),

         ## -- 5. Architecture layer check (opus — needs understanding)
         Task(
            name="Architecture Layers",
            description="Check for layer violations",
            instruction="ACE2 has layers: L0 (foundation) through L8 (integration). "
                        "Check: does any code in src/ace2/ import from a HIGHER layer? "
                        "Does any script bypass the query module (inline SQL)? "
                        "Does rondo/ depend on anything it shouldn't? "
                        "Check for proper separation of concerns.",
            context_files=["pyproject.toml"],
            done_when="Layer violations identified or confirmed clean",
            model="opus",
         ),

         ## -- 6. Summary
         Task(
            name="Convention Summary",
            description="Overall convention health",
            instruction="Based on checks 1-5, rate convention health: "
                        "GREEN (clean), YELLOW (minor issues), RED (significant drift). "
                        "Top 3 action items. Compare to 137 convention lock classes — "
                        "are there patterns that SHOULD be locked but aren't?",
            context_files=["tests/test_fix2_conventions.py"],
            done_when="Convention health score with action items",
            model="opus",
         ),
      ],

      post_gates=[
         Gate(
            name="Convention results recorded",
            description="All checks complete",
            check_fn=lambda **_kw: (True, "Recorded by runner"),
         ),
      ],
   )
