#!/bin/bash
# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
# -- Rondo CLI example: consensus review on a real file.

set -euo pipefail

TARGET_FILE="${1:-src/rondo/mcp_dispatch.py}"

echo "=== CLI Example 03: Consensus Review ==="
echo "Target: ${TARGET_FILE}"
echo ""

# -- First provider review
echo "[1/2] Gemini review:"
rondo review "${TARGET_FILE}" --providers gemini --tier default
echo ""

# -- Second provider review
echo "[2/2] Grok review:"
rondo review "${TARGET_FILE}" --providers grok --tier default
echo ""

echo "-PASS- Consensus review example completed"
