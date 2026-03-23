#!/bin/bash
## ═══════════════════════════════════════════════════════════════
## Rondo Product Setup
## ═══════════════════════════════════════════════════════════════
##
## Sets up: Rondo venv, dependencies, dispatch config, API key check.
## Idempotent: safe to run 100 times.
##
## Usage:
##   setup-rondo.sh              # full setup
##   setup-rondo.sh --update     # apply changes since last run
##   setup-rondo.sh --verify     # check only, no changes
##
## Per CORE-SOP-014 req 001, 026
## ═══════════════════════════════════════════════════════════════

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ACE2_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
RONDO_ROOT="$ACE2_ROOT/rondo"
ACE_HOME="${ACE_HOME:-$HOME/.claude}"

MODE="${1:---setup}"

PASS=0
FAIL=0
WARN=0

pass_msg()  { echo "  -PASS-     $1"; PASS=$((PASS + 1)); }
fail_msg()  { echo "  -ERROR-    $1"; FAIL=$((FAIL + 1)); }
warn_msg()  { echo "  -WARNING-  $1"; WARN=$((WARN + 1)); }

echo ""
echo "--- Rondo Setup ($MODE) ---"

## ─────────────────────────────────────────────
## 1. Rondo virtual environment (separate from main)
## ─────────────────────────────────────────────
RONDO_VENV="$RONDO_ROOT/.venv"

if [[ -d "$RONDO_VENV" ]] && [[ -f "$RONDO_VENV/bin/python3" ]]; then
   RONDO_PY=$("$RONDO_VENV/bin/python3" --version 2>&1 | awk '{print $2}')
   pass_msg "Rondo venv exists (Python $RONDO_PY)"
elif [[ "$MODE" == "--verify" ]]; then
   warn_msg "Rondo venv missing: $RONDO_VENV"
else
   echo "  Creating Rondo venv..."
   python3 -m venv "$RONDO_VENV"
   pass_msg "Rondo venv created"
fi

## ─────────────────────────────────────────────
## 2. Rondo dependencies
## ─────────────────────────────────────────────
RONDO_REQS="$RONDO_ROOT/pyproject.toml"
RONDO_UV="$RONDO_ROOT/uv.lock"

if [[ -f "$RONDO_REQS" ]]; then
   pass_msg "Rondo pyproject.toml exists"
   if [[ -f "$RONDO_UV" ]]; then
      pass_msg "Rondo uv.lock exists"
   fi

   if [[ "$MODE" != "--verify" ]] && [[ -d "$RONDO_VENV" ]]; then
      echo "  Installing Rondo dependencies..."
      if command -v uv &>/dev/null; then
         (cd "$RONDO_ROOT" && uv sync 2>/dev/null) && pass_msg "Rondo deps installed (uv)" || warn_msg "Rondo dep install had warnings"
      elif [[ -f "$RONDO_VENV/bin/pip" ]]; then
         (cd "$RONDO_ROOT" && "$RONDO_VENV/bin/pip" install -e . -q 2>/dev/null) && pass_msg "Rondo deps installed (pip)" || warn_msg "Rondo dep install had warnings"
      else
         warn_msg "Neither uv nor pip available for Rondo"
      fi
   fi
else
   warn_msg "Rondo pyproject.toml missing"
fi

## ─────────────────────────────────────────────
## 3. Dispatch configuration
## ─────────────────────────────────────────────
RONDO_CONFIG="$RONDO_ROOT/rondo.toml"

if [[ -f "$RONDO_CONFIG" ]]; then
   pass_msg "Rondo config exists: rondo.toml"
elif [[ "$MODE" == "--verify" ]]; then
   warn_msg "Rondo config missing: rondo.toml"
else
   warn_msg "Rondo config missing -- create rondo.toml when ready"
fi

## ─────────────────────────────────────────────
## 4. Claude API key (macOS Keychain)
## ─────────────────────────────────────────────
if command -v security &>/dev/null; then
   if security find-generic-password -s "claude-api-key" -a "$USER" &>/dev/null 2>&1; then
      pass_msg "Claude API key found in Keychain"
   elif [[ "$MODE" == "--verify" ]]; then
      warn_msg "Claude API key not in Keychain (required for Rondo dispatch)"
   else
      warn_msg "Claude API key not in Keychain -- add with: security add-generic-password -s claude-api-key -a $USER -w 'YOUR_KEY'"
   fi
else
   warn_msg "Cannot check Keychain (security command not found)"
fi

## ─────────────────────────────────────────────
## 5. Rondo specs
## ─────────────────────────────────────────────
RONDO_SPECS="$RONDO_ROOT/specs"
if [[ -d "$RONDO_SPECS" ]]; then
   SPEC_COUNT=$(find "$RONDO_SPECS" -name "*.md" -type f 2>/dev/null | wc -l | tr -d ' ')
   pass_msg "Rondo specs: $SPEC_COUNT files"
else
   warn_msg "Rondo specs directory missing"
fi

## ─────────────────────────────────────────────
## 6. Rondo source code
## ─────────────────────────────────────────────
RONDO_SRC="$RONDO_ROOT/src/rondo"
if [[ -d "$RONDO_SRC" ]]; then
   SRC_COUNT=$(find "$RONDO_SRC" -name "*.py" -type f 2>/dev/null | wc -l | tr -d ' ')
   pass_msg "Rondo source: $SRC_COUNT Python files"
else
   warn_msg "Rondo source directory missing: src/rondo/"
fi

## ─────────────────────────────────────────────
## Summary
## ─────────────────────────────────────────────
echo ""
echo "  Rondo: $PASS passed, $FAIL failed, $WARN warnings"

if (( FAIL > 0 )); then
   exit 1
else
   exit 0
fi
