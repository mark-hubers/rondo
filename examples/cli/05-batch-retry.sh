#!/bin/bash
# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
# rondo-meta: mode=http provider=gemini,grok category=pipeline value="Run batch providers then retry failed dispatch ids via MCP tools."

set -euo pipefail

echo "=== CLI Example 05: Batch Retry Pattern ==="
echo "Use this with MCP calls from Claude Code:"
echo
echo "1) Run batch review:"
echo '   rondo_multi_review(prompt="Review this diff for risks", providers="[\"gemini:gemini-flash-latest\",\"grok:grok-4.3\"]", dry_run=false)'
echo
echo "2) If a provider fails, retry dispatch id:"
echo '   rondo_retry(dispatch_id="<id>", model="gemini:gemini-flash-latest")'
echo
echo "3) Check retry status:"
echo '   rondo_run_status(dispatch_id="<id>", brief=true)'
echo
echo "-PASS- batch retry recipe ready"
