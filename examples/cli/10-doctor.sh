#!/bin/bash
# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
# rondo-meta: mode=cli provider=all category=operations value="rondo doctor: the first command support asks anyone to run — install diagnosis with fix hints + a redacted support bundle. Zero dispatches, zero cost."
#
# RONDO-320 (REQ-103 reqs 030-036; SOP-105 P2-0 — the top onboarding item
# from the 4-AI productization review). Preflight answers "can I dispatch
# RIGHT NOW"; doctor answers "is this INSTALL healthy, and what exactly do
# I fix": config, provider keys (last-4 only, never full), registry drift,
# data dirs, claude binary, versions.
#
# Contracts:
#   - exit 0 = healthy, 1 = at least one FAIL (WARN never fails) — CI-able
#   - every non-PASS row carries a one-line FIX hint, never a traceback
#   - --bundle writes ONE redacted file; a leak ABORTS the write

set -euo pipefail

echo "=== CLI Example 10: Doctor (install diagnosis) ==="

echo "[1/3] Diagnose this install — free, no dispatches"
rondo doctor || true
echo

echo "[2/3] Machine-readable for your own automation"
rondo doctor --json | head -12 || true
echo

echo "[3/3] Redacted support bundle (paste into an issue report)"
rondo doctor --bundle >/dev/null || true
echo "      Written to ~/.rondo/support-bundle.txt — keys appear as last-4 ONLY;"
echo "      a bundle that fails the leak scan is never written at all."
echo

echo "-PASS- doctor example completed"
