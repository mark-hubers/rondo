#!/bin/bash
# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
# -- Rondo CLI example: start background run via MCP-compatible tool surface and poll status.
# -- Uses `rondo mcp` equivalent workflow conceptually, but calls through `rondo_run` tool syntax
# -- represented as copy/paste guidance for MCP clients.

set -euo pipefail

echo "=== CLI Example 02: Background Polling Pattern ==="
echo ""
echo "Use this from MCP clients (Claude Code) as real background workflow:"
echo ""
cat <<'EOF'
rondo_run(
    prompt="Deep review this design and return structured findings.",
    model="sonnet",
    execution="subprocess",
    background=True,
    dry_run=False
)

rondo_run_status(dispatch_id="mcp-<id>", heartbeat=True)
rondo_run_status(dispatch_id="mcp-<id>", brief=True)
rondo_run_status(dispatch_id="mcp-<id>")
EOF
echo ""
echo "-PASS- Background polling recipe printed"
