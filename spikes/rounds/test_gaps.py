#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Mark G. Hubers / HubersTech
# SPDX-License-Identifier: LicenseRef-Proprietary
"""Test Gap Analysis Round — find untested code.

For each source module, checks: does a test exist? What's untested?
Are tests stale (testing deleted functionality)?

Created: 2026-03-13 (Session 75)
Author: Mark Hubers — HubersTech
"""

from pathlib import Path

from rondo.engine import Gate, Round, Task

_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent.parent)


def _find_source_modules() -> list[tuple[str, str]]:
    """Find source modules and their expected test files."""
    src_dir = Path(_PROJECT_ROOT) / "src" / "ace2"
    pairs = []
    for f in sorted(src_dir.glob("*.py")):
        if f.name.startswith("_"):
            continue
        module_name = f.stem
        test_path = Path(_PROJECT_ROOT) / "tests" / f"test_{module_name}.py"
        pairs.append((str(f), str(test_path)))
    return pairs


def _check_src_exists(**_kwargs: object) -> tuple[bool, str]:
    """Verify src/ace2/ exists."""
    src = Path(_PROJECT_ROOT) / "src" / "ace2"
    return src.exists(), f"{'Found' if src.exists() else 'MISSING'}: {src}"


def build_test_gap_round() -> Round:
    """Build a test gap analysis round."""
    module_pairs = _find_source_modules()

    tasks = []
    for src_path, test_path in module_pairs[:20]:
        module_name = Path(src_path).stem
        test_exists = Path(test_path).exists()
        context = [src_path]
        if test_exists:
            context.append(test_path)

        tasks.append(
            Task(
                name=f"Test Gap: {module_name}",
                description=f"Test coverage analysis for {module_name}",
                instruction=f"Read {src_path}. "
                f"{'Also read ' + test_path + '. ' if test_exists else 'NO TEST FILE EXISTS. '}"
                "For each public function/class: "
                "1) Is it tested? (function name appears in test file) "
                "2) Are edge cases covered? "
                "3) Are error paths tested? "
                "List untested functions with priority: HIGH (public API), "
                "MEDIUM (internal logic), LOW (simple getters/formatters).",
                context_files=context,
                done_when=f"Test gap list for {module_name} with priorities",
                model="sonnet",
            ),
        )

    ## -- Summary task
    tasks.append(
        Task(
            name="Test Gap Summary",
            description="Overall test coverage assessment",
            instruction="Based on all module analyses: "
            "1) Modules with NO test file (critical gaps) "
            "2) Modules with test file but missing coverage (gaps) "
            "3) Estimated overall coverage completeness "
            "4) Top 5 functions that MOST need tests (by risk) "
            "5) Any stale tests (testing deleted code)?",
            context_files=[],
            done_when="Prioritized test gap report with top 5 action items",
            model="opus",
        ),
    )

    return Round(
        name="test-gaps",
        round_num=0,
        description=f"Test gap analysis: {len(module_pairs)} source modules",
        pre_gates=[
            Gate(
                name="Source exists",
                description="src/ace2/ directory exists",
                check_fn=_check_src_exists,
                blocking=True,
            ),
        ],
        tasks=tasks,
        post_gates=[
            Gate(
                name="Analysis complete",
                description="All modules analyzed",
                check_fn=lambda **_kw: (True, "Recorded"),
            ),
        ],
    )
