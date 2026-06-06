#!/bin/bash
# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
# rondo-meta: mode=subprocess,http provider=anthropic,gemini,grok category=review value="Compare one prompt across three models from CLI."

set -euo pipefail

echo "=== CLI Example 04: Model Comparison ==="
echo "[1/3] Claude subprocess path"
rondo "Return two reliability risks for Python task runners." --model sonnet
echo
echo "[2/3] Gemini HTTP path"
rondo "Return two reliability risks for Python task runners." --model gemini:gemini-flash-latest
echo
echo "[3/3] Grok HTTP path"
rondo "Return two reliability risks for Python task runners." --model grok:grok-4.3
echo
echo "-PASS- model comparison example completed"
