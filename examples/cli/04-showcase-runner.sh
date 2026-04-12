#!/bin/bash
# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
# rondo-meta: mode=subprocess provider=— category=observability value="One-command showcase run plus API example validation"

# -- Rondo CLI example: run the top-level showcase and API example suite.

set -euo pipefail

echo "=== CLI Example 04: Showcase + API Validation ==="
echo ""

echo "[1/2] Run showcase demo (10 sections):"
rondo-test --showcase
echo ""

echo "[2/2] Run API example living tests:"
rondo-test --examples-api
echo ""

echo "-PASS- Showcase runner example completed"
