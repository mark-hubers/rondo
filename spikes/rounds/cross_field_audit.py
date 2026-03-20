#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Mark G. Hubers / HubersTech
# SPDX-License-Identifier: LicenseRef-Proprietary
"""Cross-Field Relationship Audit Round — catch config validation gaps.

Scans frozen dataclasses for numeric fields that share a domain (timeouts,
sizes, counts) and verifies that _validate_relationships() functions exist
and check logical ordering between related fields.

Why: Google AI review caught watchdog_timeout_sec >= task_timeout_sec gap
that Claude and humans missed. Per-field range checks pass individually
but the COMBINATION is invalid. This round automates that detection.

Implements: OB-STD-009 Req 24, OB-SOP-006 Req 27-32
Category: SEMANTIC convention (3rd category alongside STRUCTURAL and WIRING)

Created: 2026-03-14 (Session 75)
Author: Mark Hubers — HubersTech
"""

from rondo.engine import Gate, Round, Task


def build_cross_field_round() -> Round:
    """Build a cross-field relationship audit round."""
    return Round(
        name="cross-field-audit",

        pre_gates=[
            Gate(
                name="Python source exists",
                check_fn=lambda **_kw: (True, "Source directories assumed present"),
                blocking=False,
            ),
        ],

        tasks=[
            # -- 1. Discover frozen dataclasses (sonnet — AST scanning)
            Task(
                name="Discover Dataclasses",
                description="Find all frozen dataclasses with numeric fields",
                instruction=(
                    "Scan all .py files in the project for @dataclass(frozen=True) "
                    "classes. For each one, list:\n"
                    "  1. Class name and file path\n"
                    "  2. All numeric fields (int, float) with their defaults\n"
                    "  3. Group fields by domain: timeouts (*_sec, *_timeout), "
                    "sizes (*_size, *_bytes, *_mb), counts (*_count, *_max, *_min, "
                    "*_workers, *_limit), durations (*_ms, *_duration)\n"
                    "  4. Flag any class with 2+ numeric fields in the same domain\n\n"
                    "Output a table: class | file | domain | fields | field_count"
                ),
                context_files=["pyproject.toml"],
                done_when="Table of all frozen dataclasses with grouped numeric fields",
                model="sonnet",
            ),

            # -- 2. Check for _validate_relationships (sonnet — code search)
            Task(
                name="Check Validation Functions",
                description="Verify _validate_relationships() exists for flagged classes",
                instruction=(
                    "For each dataclass flagged in task 1 (2+ numeric fields in "
                    "same domain), check:\n"
                    "  1. Does a validate_*() or _validate_relationships() function "
                    "exist that takes this dataclass as input?\n"
                    "  2. Does that function compare the related fields against each "
                    "other (not just individual range checks)?\n"
                    "  3. Are ALL field pairs in the same domain covered?\n\n"
                    "Example: if class has watchdog_timeout_sec and task_timeout_sec, "
                    "there MUST be a check that watchdog < task.\n\n"
                    "Output: class | domain | field_pair | has_check | check_location"
                ),
                context_files=["pyproject.toml"],
                done_when="Coverage matrix of relationship checks vs field pairs",
                model="sonnet",
            ),

            # -- 3. AI relationship analysis (opus — reasoning required)
            Task(
                name="Infer Missing Relationships",
                description="Use domain knowledge to identify what relationships SHOULD exist",
                instruction=(
                    "For each class with 2+ numeric fields in the same domain, "
                    "reason about what logical relationships MUST hold:\n\n"
                    "Timeout domain:\n"
                    "  - watchdog < task (watchdog detects silence within a task)\n"
                    "  - retry_delay < timeout (retries must fit within timeout)\n"
                    "  - backoff < timeout (backoff must not exceed timeout)\n\n"
                    "Size domain:\n"
                    "  - min < max (obvious but often missing)\n"
                    "  - chunk_size < max_size (chunks must fit)\n"
                    "  - buffer_size < memory_limit\n\n"
                    "Count domain:\n"
                    "  - min_workers <= max_workers\n"
                    "  - batch_size <= total_limit\n\n"
                    "For each field pair, state:\n"
                    "  1. The relationship (A < B, A <= B, A != B)\n"
                    "  2. WHY (the domain reason)\n"
                    "  3. Whether the check exists in code\n"
                    "  4. Priority: HIGH (silent failure if wrong) vs MEDIUM (error but caught)"
                ),
                context_files=["pyproject.toml"],
                done_when="Full relationship map with priorities and gap analysis",
                model="opus",
            ),

            # -- 4. Generate fix recommendations (sonnet — code generation)
            Task(
                name="Generate Fixes",
                description="Write the missing validation code",
                instruction=(
                    "For each gap found in task 3 (relationship exists but no check), "
                    "generate the validation code that should be added:\n\n"
                    "  1. The function signature (or where to add to existing function)\n"
                    "  2. The exact if/check with descriptive error message\n"
                    "  3. The error message MUST explain WHY the relationship must hold "
                    "(not just 'A must be less than B')\n"
                    "  4. A test case that verifies the check catches violations\n\n"
                    "Follow the existing validation pattern in the codebase. "
                    "Example from rondo/config.py _validate_relationships():\n"
                    "  if config.watchdog_timeout_sec >= config.task_timeout_sec:\n"
                    "      errors.append(f'watchdog_timeout_sec (...) must be less "
                    "than task_timeout_sec (...) — watchdog detects silence within "
                    "a task, so it must fire before the task times out')"
                ),
                context_files=["pyproject.toml"],
                done_when="Validation code and test cases for all gaps",
                model="sonnet",
            ),

            # -- 5. Summary report (haiku — aggregation)
            Task(
                name="Audit Summary",
                description="Cross-field validation health report",
                instruction=(
                    "Summarize the cross-field validation audit:\n\n"
                    "  1. Total frozen dataclasses scanned\n"
                    "  2. Classes with 2+ related numeric fields\n"
                    "  3. Relationship checks found / expected (coverage %)\n"
                    "  4. Gaps by priority (HIGH / MEDIUM)\n"
                    "  5. Overall health: GREEN (100% covered), YELLOW (>80%), "
                    "RED (<80%)\n\n"
                    "Rate: GREEN / YELLOW / RED with specific action items."
                ),
                context_files=["pyproject.toml"],
                done_when="Health score with gap count and action items",
                model="haiku",
            ),
        ],

        post_gates=[
            Gate(
                name="Audit results recorded",
                check_fn=lambda **_kw: (True, "Recorded by runner"),
            ),
        ],
    )
