#!/bin/bash
# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
# rondo-meta: mode=cli provider=all category=operations value="Auto-tiers + canary: derive low/mid/high from live catalogs (free) and PROVE every configured model still answers (~cents)."
#
# The drift report (example 07) tells you a model ID vanished from the
# catalog. This goes two steps further (REQ-111 reqs 604-610):
#   --tiers  : derive auto_low/mid/high per provider from the registry cache.
#              SUGGEST mode — printed, never written. You flip config lines.
#   --verify : one tiny live dispatch per configured tier model. A model can
#              be IN the catalog and still refuse your account/region — only
#              a real answer proves the pipe.
#
# First live run of --tiers exposed a real trap: provider catalogs mix
# embeddings/moderation/audio/video models in with chat models. The
# derivation excludes non-chat modalities by name token.

set -euo pipefail

echo "=== CLI Example 09: Auto-Tiers + Model Canary ==="

echo "[1/3] Refresh the registry cache (free catalog GETs)"
rondo providers --refresh
echo

echo "[2/3] Derived auto-tiers — suggest mode, config never touched"
rondo models --tiers
echo "      Manual pins ALWAYS win (COALESCE: pin -> auto-tier -> collapse ladder)."
echo "      Collapse ladder: a provider missing 'low' inherits 'mid', missing 'mid' inherits 'high'."
echo

echo "[3/3] Canary — one tiny live dispatch per configured tier (~cents total)"
echo "      Exit 0 = all answer, 1 = at least one FAIL (scriptable, CI-able)"
rondo models --verify || true
echo

echo "-PASS- model canary example completed"
