#!/bin/bash
## ═══════════════════════════════════════════════════════════════
## Rondo CLI: Scripted Prompting Examples
## ═══════════════════════════════════════════════════════════════
##
## These show how to script AI decisions from the command line.
## The structured JSON return makes if/else branching possible.
## Without structured returns, you'd need to parse text blobs.
##
## Prerequisites:
##   - rondo installed
##   - jq installed (JSON parsing)
##   - At least one provider key set
##
## Usage: bash examples/cli/scripted-prompting.sh
##        Or copy individual patterns into your own scripts.
## ═══════════════════════════════════════════════════════════════

set -euo pipefail

echo "═══ CLI Scripted Prompting Examples ═══"
echo "(Using --dry-run for safety — remove for real dispatch)"
echo ""

## ─── Pattern 1: Retry on Failure ──────────────────────────────
## If the first provider can't answer, try a different one.
## The 'passed' field tells you if the AI succeeded.

echo "--- Pattern 1: Retry on Failure ---"
## In real use (no --dry-run on inline; use rondo run FILE --dry-run to preview):
## result=$(rondo "review this code for bugs" --model gemini:default)
## passed=$(echo "$result" | jq -r '.passed')
## if [ "$passed" = "false" ] || [ "$passed" = "null" ]; then
##     echo "Primary failed — trying premium model..."
##     result=$(rondo "review this code for bugs" --model opus)
## fi
## echo "$result" | jq '.issues'
echo "  Would: try gemini:default → if fails → try opus"

## ─── Pattern 2: Confidence Check ──────────────────────────────
## If the AI isn't confident enough, add context and retry.
## The 'confidence' field (0.0-1.0) drives the decision.

echo ""
echo "--- Pattern 2: Confidence Escalation ---"
## result=$(rondo "Is this login handler secure?" --model gemini:default)
## confidence=$(echo "$result" | jq -r '.confidence')
## if (( $(echo "$confidence < 0.8" | bc -l) )); then
##     echo "Low confidence ($confidence) — adding context..."
##     result=$(echo "Focus on SQL injection and XSS" | rondo "Is this login handler secure?")
## fi
echo "  Would: check confidence → if < 0.8 → retry with more context"

## ─── Pattern 3: Find-Fix-Verify Pipeline ──────────────────────
## Chain AI calls: find bugs → fix each → verify each fix.
## The 'issues' array lets you loop with jq.

echo ""
echo "--- Pattern 3: Find → Fix → Verify ---"
## Step 1: Find bugs
## bugs=$(rondo "Find bugs in this code" --field bugs < app.py)
##
## Step 2: Fix each bug
## echo "$bugs" | jq -r '.bugs[]' | while read -r bug; do
##     fix=$(rondo "Fix this bug: $bug" --field fix)
##     echo "Fixed: $bug → $(echo "$fix" | jq -r '.fix' | head -1)"
##
##     ## Step 3: Verify the fix
##     verify=$(echo "$fix" | jq -r '.fix' | rondo "Does this fix work?" --field verified)
##     passed=$(echo "$verify" | jq -r '.passed')
##     if [ "$passed" = "false" ]; then
##         echo "  WARNING: Fix not verified — needs human review"
##     fi
## done
echo "  Would: find bugs → fix each → verify each → flag failures"

## ─── Pattern 4: Multi-AI Tiebreaker ──────────────────────────
## Ask 2 AIs the same question. If they disagree, ask a 3rd.
## Compare the 'passed' field across providers.

echo ""
echo "--- Pattern 4: Multi-AI Tiebreaker ---"
## review_a=$(rondo "Is this code safe?" --model gemini:default)
## review_b=$(rondo "Is this code safe?" --model grok:grok-3)
##
## passed_a=$(echo "$review_a" | jq -r '.passed')
## passed_b=$(echo "$review_b" | jq -r '.passed')
##
## if [ "$passed_a" != "$passed_b" ]; then
##     echo "AIs disagree — calling tiebreaker..."
##     review_c=$(rondo "Is this code safe?" --model mistral:large)
##     passed_c=$(echo "$review_c" | jq -r '.passed')
##     ## Majority vote
##     true_count=0
##     [ "$passed_a" = "true" ] && ((true_count++))
##     [ "$passed_b" = "true" ] && ((true_count++))
##     [ "$passed_c" = "true" ] && ((true_count++))
##     [ $true_count -ge 2 ] && echo "MAJORITY: safe" || echo "MAJORITY: unsafe"
## fi
echo "  Would: gemini + grok → disagree → mistral tiebreaker → majority vote"

## ─── Pattern 5: Budget-Aware Routing ──────────────────────────
## Start cheap (local/$0), escalate to cloud only if needed.
## Track spending and stop before exceeding budget.

echo ""
echo "--- Pattern 5: Budget-Aware Routing ---"
## budget=0.10
## spent=0.00
##
## ## Try local first (FREE)
## result=$(rondo "Explain quantum computing" --model local:qwen2.5:32b)
## quality=$(echo "$result" | jq -r '._meta.quality')
##
## if [ "$quality" -lt 7 ]; then
##     ## Local not good enough — try cloud cheap
##     cost=0.003
##     spent=$(echo "$spent + $cost" | bc)
##     if (( $(echo "$spent <= $budget" | bc -l) )); then
##         result=$(rondo "Explain quantum computing" --model gemini:default)
##     else
##         echo "Budget exceeded — using local result"
##     fi
## fi
echo "  Would: local (free) → if quality < 7 → cloud → check budget"

## ─── Pattern 6: Loop Through Files ────────────────────────────
## Review every Python file in a directory.
## Collect all findings into a report.

echo ""
echo "--- Pattern 6: Review All Files ---"
## report=""
## for file in src/*.py; do
##     result=$(rondo "Review for security issues" --field issues < "$file")
##     issues=$(echo "$result" | jq -r '.issues | length')
##     if [ "$issues" -gt 0 ]; then
##         report+="$file: $issues issues found\n"
##         echo "$result" | jq -r '.issues[]' | sed "s/^/  /"
##     fi
## done
## echo -e "$report" > security-report.txt
echo "  Would: for each .py file → review → collect issues → write report"

## ─── Pattern 7: Create Tasks from Findings ────────────────────
## AI finds issues → create tickets/sprints from structured data.
## The 'issues' array + 'metadata' drive task creation.

echo ""
echo "--- Pattern 7: Findings → Tasks ---"
## result=$(rondo "Full security audit of this codebase" --field findings)
## echo "$result" | jq -r '.findings[]' | while read -r finding; do
##     severity=$(echo "$result" | jq -r ".issues[] | select(. == \"$finding\") | .severity // \"medium\"")
##     echo "Creating task: [$severity] $finding"
##     ## In real use: create GitHub issue, Jira ticket, or ace-sprint
##     ## gh issue create --title "$finding" --label "security,$severity"
## done
echo "  Would: audit → for each finding → create ticket with severity"

echo ""
echo "═══ All patterns use structured JSON returns ═══"
echo "Without jq + structured JSON, none of this scripting works."
echo "That's why Rondo's smart return matters."
