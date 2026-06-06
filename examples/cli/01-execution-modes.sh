#!/bin/bash
# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
# rondo-meta: mode=subprocess,http provider=anthropic,gemini category=basic value="CLI subprocess route vs provider HTTP route"

# -- Rondo CLI example: execution-mode behavior through `rondo_run` MCP analogs.
# -- This script demonstrates the practical equivalent of inline/agent/subprocess behavior
# -- from the CLI perspective (CLI naturally uses subprocess result mode).

set -euo pipefail

echo "=== CLI Example 01: Execution Behavior ==="
echo ""

# -- CLI dispatch (subprocess result path)
echo "[1/2] CLI subprocess-style dispatch result:"
rondo "Return JSON only: {\"benefits\": [\"...\", \"...\"]} for test automation value." --model sonnet
echo ""

# -- Provider-prefix dispatch (HTTP adapter path)
echo "[2/2] Provider-prefixed model dispatch (HTTP path):"
rondo "Give 2 architecture risks in bullet form." --model gemini:gemini-flash-latest
echo ""

echo "-PASS- CLI example completed"
