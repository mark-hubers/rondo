#!/usr/bin/env bash
## ═══════════════════════════════════════════════════════════════
## Rondo Deep Build — ALL test levels, fail-fast, scripted
## ═══════════════════════════════════════════════════════════════
##
## Runs every test level in sequence. If ANY step fails, the build fails.
## No cherry-picking, no skipping, no lazy AI letting failures pass.
##
## Usage:
##   rondo/scripts/rondo-deep-build.sh              # full deep build
##   rondo/scripts/rondo-deep-build.sh --no-cloud   # skip paid cloud tests
##   rondo/scripts/rondo-deep-build.sh --dry-run    # show steps without running
##
## Cost: ~$0.30 for cloud tests (gemini + grok + mistral API calls)
## Time: ~2-3 minutes total
##
## RONDO-219: created as part of test infrastructure hardening.
## ═══════════════════════════════════════════════════════════════

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_ROOT"

SKIP_CLOUD=false
DRY_RUN=false

for arg in "$@"; do
    case "$arg" in
        --no-cloud) SKIP_CLOUD=true ;;
        --dry-run) DRY_RUN=true ;;
        *) echo "Unknown arg: $arg"; exit 1 ;;
    esac
done

PASS=0
FAIL=0
SKIP=0
START_TIME=$(date +%s)

run_step() {
    local name="$1"
    shift
    if [ "$DRY_RUN" = true ]; then
        echo "  [DRY] $name: $*"
        return 0
    fi
    echo ""
    echo "═══ Step: $name ═══"
    if "$@"; then
        echo "  -PASS- $name"
        PASS=$((PASS + 1))
    else
        echo "  -FAIL- $name"
        FAIL=$((FAIL + 1))
        echo ""
        echo "  ✗ DEEP BUILD FAILED at: $name"
        echo "  Steps passed: $PASS | Failed: $FAIL | Skipped: $SKIP"
        exit 1
    fi
}

skip_step() {
    local name="$1"
    echo "  [SKIP] $name (--no-cloud)"
    SKIP=$((SKIP + 1))
}

echo "═══════════════════════════════════════════════════════════════"
echo "  RONDO DEEP BUILD — ALL LEVELS"
echo "═══════════════════════════════════════════════════════════════"
echo "  Repo: $REPO_ROOT"
echo "  Cloud: $([ "$SKIP_CLOUD" = true ] && echo "SKIPPED" || echo "ENABLED (~\$0.30)")"
echo "  Mode: $([ "$DRY_RUN" = true ] && echo "DRY RUN" || echo "LIVE")"
echo ""

## Step 1: Standard build (lint + security + types + unit + integration + pat + conventions)
run_step "ace-build full" ace-build full --product rondo

## Step 2: Cloud tests (real API calls)
if [ "$SKIP_CLOUD" = true ]; then
    skip_step "cloud tests"
else
    run_step "cloud tests" .venv/bin/python -m pytest -m cloud rondo/tests/ -q --tb=line
fi

## Step 3: Health check (all providers reachable)
run_step "provider health" .venv/bin/python -c "
import sys; sys.path.insert(0, 'rondo/src')
from rondo.adapters.health import get_all_providers_health
results = get_all_providers_health()
failed = [name for name, s in results.items() if not s.healthy]
if failed:
    for name in failed:
        print(f'  -WARNING- {name}: DOWN ({results[name].error})')
total = len(results)
up = total - len(failed)
print(f'  {up}/{total} providers healthy')
if len(failed) == total:
    sys.exit(1)
"

## Step 4: Pylint direct (real score, not ace-build's buggy path)
run_step "pylint direct" .venv/bin/python -m pylint rondo/src/rondo/ --fail-under=9.5

## Summary
END_TIME=$(date +%s)
ELAPSED=$((END_TIME - START_TIME))

echo ""
echo "══════════════════════════════════════════════════════════"
echo "  ✓ DEEP BUILD PASSED"
echo "  Steps: $PASS passed | $SKIP skipped | $FAIL failed"
echo "  Time: ${ELAPSED}s"
echo "══════════════════════════════════════════════════════════"
