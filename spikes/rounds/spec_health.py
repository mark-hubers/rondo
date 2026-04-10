#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Mark G. Hubers / HubersTech
# SPDX-License-Identifier: LicenseRef-Proprietary
"""Spec Health Check — overnight round for any spec.

Checks a spec file for: staleness, missing sections, cross-ref integrity,
requirement quality, and actionable issues. Designed for batch dispatch
across all specs overnight.

Usage:
   from rondo.rounds.spec_health import build_spec_health_round
   round_def = build_spec_health_round("OB-REQ-100", "orbital/specs/OB-REQ-100-orbital-database.md")

Created: 2026-03-13 (Session 75 — Rondo Spike)
Author: Mark Hubers — HubersTech
"""

from rondo.engine import Gate, Round, Task


## -- Gate checks
def _check_file_exists(**kwargs: object) -> tuple[bool, str]:
    """Verify spec file exists on disk."""
    from pathlib import Path

    spec_path = str(kwargs.get("spec_path", ""))
    if not spec_path:
        return False, "No spec_path provided"
    exists = Path(spec_path).exists()
    return exists, f"{'Found' if exists else 'MISSING'}: {spec_path}"


def _check_file_readable(**kwargs: object) -> tuple[bool, str]:
    """Verify spec file has content."""
    from pathlib import Path

    spec_path = str(kwargs.get("spec_path", ""))
    if not spec_path:
        return False, "No spec_path provided"
    path = Path(spec_path)
    if not path.exists():
        return False, f"File missing: {spec_path}"
    size = path.stat().st_size
    if size < 100:
        return False, f"File too small ({size} bytes) — likely stub"
    return True, f"Readable: {size:,} bytes"


def build_spec_health_round(spec_id: str, spec_path: str) -> Round:
    """Build a health check round for any spec.

    Args:
       spec_id: Spec identifier (e.g., "OB-REQ-100", "R027", "F14")
       spec_path: Path to the spec markdown file

    Returns:
       Round with 8 health check tasks
    """
    return Round(
        name="spec-health",
        round_num=0,
        description=f"Health check for {spec_id}",
        pre_gates=[
            Gate(
                name="File exists",
                description=f"{spec_id} spec file exists on disk",
                check_fn=_check_file_exists,
                blocking=True,
            ),
            Gate(
                name="File readable",
                description=f"{spec_id} has real content (not a stub)",
                check_fn=_check_file_readable,
                blocking=True,
            ),
        ],
        tasks=[
            ## -- 1. Section completeness (simple pattern check → sonnet)
            Task(
                name=f"{spec_id}: Section Check",
                description="Verify required sections exist",
                instruction="Read the spec file. Check if it has these sections: "
                "Problem Statement, Architecture, Data Model, Dependencies, "
                "Success Criteria, Assumptions, Risks. "
                "List which sections are present and which are missing.",
                context_files=[spec_path],
                done_when="All sections catalogued with present/missing status",
                model="sonnet",
            ),
            ## -- 2. Requirement quality (needs judgment → opus)
            Task(
                name=f"{spec_id}: Requirement Quality",
                description="Check requirements are testable and specific",
                instruction="Read the requirements section. For each requirement: "
                "Is it testable? Is it specific (not vague)? "
                "Does it have a verification method? "
                "Flag any that say 'should' instead of 'shall', "
                "or that are unmeasurable.",
                context_files=[spec_path],
                done_when="Each requirement rated: testable/vague/missing-verification",
                model="opus",
            ),
            ## -- 3. Cross-reference check (pattern matching → sonnet)
            Task(
                name=f"{spec_id}: Cross-References",
                description="Verify referenced specs exist and are correct",
                instruction="Find all references to other specs (R-numbers, F-numbers, "
                "OB-numbers). Verify: does each referenced spec exist? "
                "Is the reference direction correct? "
                "Are there obvious missing cross-references?",
                context_files=[spec_path],
                done_when="All cross-refs verified or flagged as broken",
                model="sonnet",
            ),
            ## -- 4. Staleness detection (pattern matching → sonnet)
            Task(
                name=f"{spec_id}: Staleness Check",
                description="Check for outdated content",
                instruction="Look for signs of staleness: "
                "references to old table names (round-tracking.db, ace_files, "
                "step_completions), text IDs instead of integer PKs, "
                "missing project_id awareness, old CLI syntax. "
                "Flag anything that doesn't match OB2 architecture.",
                context_files=[spec_path],
                done_when="Stale patterns catalogued with line numbers",
                model="sonnet",
            ),
            ## -- 5. OB2 alignment (architecture knowledge → opus)
            Task(
                name=f"{spec_id}: OB2 Alignment",
                description="Check spec aligns with OB2 decisions",
                instruction="Does this spec mention: multi-project support, "
                "integer PKs, dual-backend (Postgres+SQLite), "
                ".ob/config.toml, project_id? "
                "If any are relevant but missing, flag them.",
                context_files=[spec_path],
                done_when="OB2 alignment gaps identified or confirmed aligned",
                model="opus",
            ),
            ## -- 6. Assumptions and risks (judgment → opus)
            Task(
                name=f"{spec_id}: Assumptions & Risks",
                description="Check assumptions are documented and risks identified",
                instruction="Read Assumptions and Risks sections. "
                "Are assumptions explicit and testable? "
                "Are risks rated by impact and likelihood? "
                "Are there obvious risks not listed? "
                "Flag any assumption that should be a spike.",
                context_files=[spec_path],
                done_when="Assumptions and risks reviewed with gaps flagged",
                model="opus",
            ),
            ## -- 7. Test coverage (structured check → sonnet)
            Task(
                name=f"{spec_id}: Test Coverage Plan",
                description="Check success criteria have verification methods",
                instruction="Read Success Criteria or Test Plan section. "
                "Does each criterion have: a test type (unit/integration/e2e), "
                "a pass condition, and a way to run it? "
                "Flag criteria that have no verification method.",
                context_files=[spec_path],
                done_when="Each success criterion mapped to verification method or flagged",
                model="sonnet",
            ),
            ## -- 8. Summary score (synthesis across all checks → opus)
            Task(
                name=f"{spec_id}: Health Score",
                description="Overall health assessment",
                instruction="Based on all previous checks, rate this spec: "
                "GREEN (healthy, no blockers), "
                "YELLOW (issues but workable), "
                "RED (major gaps, blocks build). "
                "Provide 1-line summary and top 3 action items.",
                context_files=[spec_path],
                done_when="Health score (GREEN/YELLOW/RED) with action items",
                model="opus",
            ),
        ],
        post_gates=[
            Gate(
                name="All checks complete",
                description="All 8 health tasks finished",
                check_fn=lambda **_kw: (True, "Manual verification"),
            ),
        ],
    )
