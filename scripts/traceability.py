#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Generate traceability matrix: Spec Req → Source Code → Test.

NASA/DO-178C style: every requirement must trace to code AND test.
Scans source files for 'Rondo-REQ-NNN' and 'Rondo-STD-NNN' references.

Usage:
    python3 scripts/traceability.py              # human-readable
    python3 scripts/traceability.py --json       # machine-readable
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

SRC_DIR = Path(__file__).parent.parent / "src" / "rondo"
TEST_DIR = Path(__file__).parent.parent / "tests"
SPEC_PATTERN = re.compile(r"Rondo-(REQ|STD|IFS|VER)-\d{3}")


def scan_files(directory: Path, pattern: str = "*.py") -> dict[str, list[str]]:
    """Scan files for spec references. Returns {spec_id: [file:line, ...]}."""
    refs: dict[str, list[str]] = {}
    for filepath in sorted(directory.glob(pattern)):
        for i, line in enumerate(filepath.read_text(encoding="utf-8").splitlines(), 1):
            for match in SPEC_PATTERN.findall(line):
                spec_id = SPEC_PATTERN.search(line)
                if spec_id:
                    key = spec_id.group(0)
                    refs.setdefault(key, []).append(f"{filepath.name}:{i}")
    return refs


def generate_matrix() -> dict[str, dict[str, list[str]]]:
    """Generate full traceability matrix."""
    source_refs = scan_files(SRC_DIR)
    test_refs = scan_files(TEST_DIR)

    all_specs = sorted(set(list(source_refs.keys()) + list(test_refs.keys())))

    matrix: dict[str, dict[str, list[str]]] = {}
    for spec in all_specs:
        matrix[spec] = {
            "source": source_refs.get(spec, []),
            "tests": test_refs.get(spec, []),
            "status": "TRACED" if source_refs.get(spec) and test_refs.get(spec) else
                      "CODE_ONLY" if source_refs.get(spec) else
                      "TEST_ONLY" if test_refs.get(spec) else "MISSING",
        }
    return matrix


def print_matrix(matrix: dict[str, dict[str, list[str]]]) -> None:
    """Print human-readable traceability report."""
    traced = sum(1 for v in matrix.values() if v["status"] == "TRACED")
    code_only = sum(1 for v in matrix.values() if v["status"] == "CODE_ONLY")
    test_only = sum(1 for v in matrix.values() if v["status"] == "TEST_ONLY")
    total = len(matrix)

    print(f"\n{'=' * 70}")
    print(f"  RONDO TRACEABILITY MATRIX")
    print(f"  Specs: {total} | Traced: {traced} | Code-only: {code_only} | Test-only: {test_only}")
    print(f"  Coverage: {traced}/{total} = {traced * 100 // total if total else 0}% fully traced")
    print(f"{'=' * 70}\n")

    for spec, data in sorted(matrix.items()):
        status = data["status"]
        marker = "-PASS-" if status == "TRACED" else "-WARNING-" if status in ("CODE_ONLY", "TEST_ONLY") else "-ERROR-"
        print(f"  {marker} {spec}: {status}")
        if data["source"]:
            print(f"         Code: {', '.join(data['source'][:5])}")
        if data["tests"]:
            print(f"         Test: {', '.join(data['tests'][:5])}")


def main() -> int:
    """Entry point."""
    matrix = generate_matrix()
    if "--json" in sys.argv:
        print(json.dumps(matrix, indent=2))
    else:
        print_matrix(matrix)
    return 0


if __name__ == "__main__":
    sys.exit(main())


# -- sig: mgh-6201.cd.bd955f.e4a1.trace1
