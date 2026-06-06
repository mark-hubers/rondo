#!/usr/bin/env bash
# Smoke-check documented example paths and CLI behavior (no network calls).
# Run from repo root: bash examples/verify-examples.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RONDO="${RONDO:-rondo}"

cd "$ROOT"

echo "== rondo version =="
$RONDO --version

echo "== preflight =="
$RONDO preflight || true

echo "== dry-run round (Python) =="
# Note: some builds exit 1 when all tasks are "skipped" in dry-run — still a successful smoke test.
set +e
$RONDO run examples/rounds/round_hello.py --dry-run
dr=$?
set -e
if [[ "$dr" -ne 0 && "$dr" -ne 1 ]]; then
  echo "unexpected exit $dr from dry-run" >&2
  exit "$dr"
fi

echo "== matrix dry-run (REQ-113, no network) =="
$RONDO matrix run examples/rounds/06-experiment-matrix.yaml --dry-run | head -3

echo "== paths used in docs =="
test -f examples/rounds/phases_overnight.py
test -f examples/rounds/01-simple-review.yaml
test -f examples/rounds/round_hello.py
test -f examples/rounds/06-experiment-matrix.yaml
echo "OK: example files exist"

echo "== inline + --dry-run must fail (documents CLI limitation) =="
set +e
$RONDO "must fail dry run" --dry-run 2>&1 | head -3
dr2=$?
set -e
if [[ "$dr2" -eq 0 ]]; then
  echo "WARN: expected nonzero exit when --dry-run passed to inline mode" >&2
fi

echo "== inline note =="
echo "Multi-word inline prompts are not run here (would call APIs). See docs/EXAMPLE-VERIFICATION.md."

echo "DONE: manual checks — YAML dry-run needs PyYAML in rondo env; MCP checks in docs/EXAMPLE-VERIFICATION.md"
