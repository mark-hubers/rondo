#!/bin/bash
# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
# rondo-meta: mode=cli provider=all category=operations value="The morning fleet check: model drift, learned scores, retry queue, reliability scoreboard."
#
# Rondo watches its own health — this is the one-minute morning check that
# reads all of it. Everything here is FREE (catalog fetches + local data,
# zero dispatches). Run it daily, or wire it via `rondo schedule`.

set -euo pipefail

echo "=== CLI Example 07: Fleet Health (the morning check) ==="

echo "[1/4] Model drift — catch retired models BEFORE dispatches 404"
echo "      (first ever run of this check found xAI had retired grok-3 entirely)"
rondo providers --refresh --drift
echo "      STALE = fix ~/.rondo/config.toml (Rondo NEVER auto-edits your config)"
echo "      NEW   = new models served — your call whether to adopt"
echo

echo "[2/4] Learned scores — 7-day per-model performance from YOUR dispatch history"
rondo providers --scores
echo "      Feeds routing: manual override → curated default → learned best."
echo "      Needs 10+ dispatches per model in the window before a model is scored."
echo

echo "[3/4] Retry queue — self-classifying: transient retries, permanent dead-letters"
rondo retryq list
rondo retryq sweep
echo

echo "[4/4] Reliability scoreboard — 7d/30d success vs the 95% target"
rondo metrics | head -20
echo

echo "All of the above also lands in the overnight morning report automatically."
echo "-PASS- fleet health check completed"
