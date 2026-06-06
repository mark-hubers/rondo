#!/bin/bash
# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
# rondo-meta: mode=matrix provider=anthropic,openai category=experiment value="Full experiment-matrix workflow: dry-run, execute, report, reveal (REQ-113)."
#
# The complete matrix workflow, start to finish. Costs ~$0.05 when executed
# (6 small cells under a $0.25 hard ceiling); the dry-run step costs nothing.
# Re-run safe: the matrix is RESUMABLE — done cells are skipped, error cells retry.

set -euo pipefail

MATRIX=examples/rounds/06-experiment-matrix.yaml

echo "=== CLI Example 06: Experiment Matrix (REQ-113) ==="

echo "[1/4] Dry run — full grid + cost estimate, ZERO spend"
rondo matrix run "$MATRIX" --dry-run
echo
echo "    Read the grid: thinking model sweeps efforts; classic model collapsed."
echo

echo "[2/4] Execute — hard budget ceiling enforced (estimate-abort + mid-run stop)"
rondo matrix run "$MATRIX"
echo

echo "[3/4] Report — blind-coded groups, replicate mean±stdev, self-ratings"
echo "      labeled UNCALIBRATED (never rank on a model grading itself)"
rondo matrix report demo-matrix
echo

echo "[4/4] Reveal — de-anonymize (the sealed mapping's SHA-256 is verified)"
rondo matrix reveal demo-matrix
rondo matrix report demo-matrix
echo

echo "Outputs: ~/.rondo/matrix/demo-matrix/ (per-cell files + manifest.json)"
echo "Repeat at any future model release: edit models[], change name:, re-run."
echo "-PASS- experiment matrix example completed"
