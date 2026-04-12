#!/bin/bash
# rondo-meta: mode=subprocess,http provider=gemini,grok,mistral,ollama category=pipeline value="Shell scripting playbook for practical AI workflows"

## ═══════════════════════════════════════════════════════════════
## Rondo CLI: Real-World Scripted Prompting
## ═══════════════════════════════════════════════════════════════
##
## These are CLI versions of REAL workflows mined from 3 months
## of actual chat history. Each pattern replaces a manual task
## that was done 100+ times by hand.
##
## All patterns use --dry-run for safety. Remove it for real dispatch.
## Each pattern shows the FULL if/else decision logic in bash.
##
## Prerequisites:
##   - rondo installed and configured
##   - jq installed (JSON parsing)
##   - ace-sprint installed (for OB patterns)
##
## Usage: bash examples/cli/real-world-scripting.sh
##        Or copy individual patterns into your own scripts.
## ═══════════════════════════════════════════════════════════════

set -euo pipefail

echo "═══ Real-World CLI Patterns (mined from 90 days of chat) ═══"
echo "(Using dry-run simulation — remove comments for real dispatch)"
echo ""

## ─── Pattern 1: Multi-AI Code Review → Sprint Findings ──────────
## REPLACES: Copy code to Cursor, paste findings back, fix, repeat.
## FREQUENCY: 165 Cursor paste-backs in 90 days.
##
## Logic: Send to 3 providers → check consensus → create findings.
## If 2+ providers agree on an issue → auto-create sprint finding.
## If only 1 flags it → human review (could be hallucination).

echo "--- Pattern 1: Multi-AI Code Review → Sprint Findings ---"
## In real use:
## SPRINT="RONDO-250"
## for file in rondo/src/rondo/*.py; do
##     ## Ask 3 providers to review the same file
##     review_a=$(rondo "Review for security issues" --model gemini:flash --field issues < "$file")
##     review_b=$(rondo "Review for security issues" --model grok:grok-3 --field issues < "$file")
##     review_c=$(rondo "Review for security issues" --model mistral:large --field issues < "$file")
##
##     ## Count how many providers found each issue type
##     all_issues=$(echo "$review_a $review_b $review_c" | jq -s '[.[].issues[]] | group_by(.) | map({issue: .[0], count: length})')
##
##     ## Consensus: 2+ agree = create finding
##     echo "$all_issues" | jq -r '.[] | select(.count >= 2) | .issue' | while read -r issue; do
##         echo "CONSENSUS ($file): $issue"
##         ace-sprint finding add "$SPRINT" --category security --detail "$issue"
##     done
##
##     ## Solo flags: only 1 provider → human review
##     echo "$all_issues" | jq -r '.[] | select(.count == 1) | .issue' | while read -r issue; do
##         echo "REVIEW ($file): $issue (1 provider only)"
##     done
## done
echo "  Would: 3 providers review each .py → consensus → ace-sprint finding add"

## ─── Pattern 2: Lint-Fix-Verify Loop ─────────────────────────────
## REPLACES: ace-build → see pylint at 9.75 → fix one → rebuild → repeat.
## FREQUENCY: 1,460 build/lint messages in 90 days.
##
## Logic: Loop until pylint score hits target or max retries.
## AI suggests minimum-change fixes. Script applies and re-checks.

echo ""
echo "--- Pattern 2: Lint-Fix-Verify Loop ---"
## In real use:
## TARGET=10.0
## MAX_RETRIES=5
## attempt=0
##
## while [ $attempt -lt $MAX_RETRIES ]; do
##     ## Run linter, capture score
##     lint_output=$(cd ~/git/mhubers/ace2 && ace-build lint 2>&1)
##     score=$(echo "$lint_output" | grep -oP 'rated at \K[\d.]+')
##
##     echo "Attempt $((attempt+1)): score=$score"
##
##     ## Check if target hit
##     if (( $(echo "$score >= $TARGET" | bc -l) )); then
##         echo "-PASS- Target $TARGET reached!"
##         break
##     fi
##
##     ## Extract violations
##     violations=$(echo "$lint_output" | grep -E '^\w.*:\d+:' | head -5)
##
##     ## Ask AI to fix (minimum changes only)
##     fix=$(echo "$violations" | rondo "Fix these pylint violations with minimum changes. Return only the diff." --model gemini:flash)
##
##     ## Apply fix (in production: parse and apply diff)
##     echo "  AI suggested fix, applying..."
##
##     attempt=$((attempt+1))
## done
##
## if (( $(echo "$score < $TARGET" | bc -l) )); then
##     echo "-WARNING- Max retries hit. Score: $score"
## fi
echo "  Would: lint → AI fix → re-lint → loop until score >= 10.0"

## ─── Pattern 3: Spec-Code Drift Scanner ──────────────────────────
## REPLACES: Cursor found "spec says 18 tools, code registers 21".
## FREQUENCY: 5+ real mismatches caught in 90 days.
##
## Logic: Extract requirements from spec → check each against code.

echo ""
echo "--- Pattern 3: Spec-Code Drift Scanner ---"
## In real use:
## SPEC="specs/REQ-111.md"
## CODE_DIR="rondo/src/rondo/"
##
## ## Extract requirements (AI-assisted)
## reqs=$(rondo "Extract all SHALL/MUST requirements as JSON array" --field requirements < "$SPEC")
##
## ## Check each requirement against the code
## echo "$reqs" | jq -r '.requirements[]' | while read -r req; do
##     ## Send requirement + code to AI for verification
##     check=$(cat "$CODE_DIR"/*.py | rondo "Does this code satisfy: $req" --field verdict)
##     verdict=$(echo "$check" | jq -r '.verdict')
##
##     case "$verdict" in
##         PASS)     echo "  PASS: $req" ;;
##         FAIL)     echo "  FAIL: $req" && ace-sprint finding add "$SPRINT" --detail "Spec drift: $req" ;;
##         CONFLICT) echo "  CONFLICT: $req" && ace-sprint finding add "$SPRINT" --category critical --detail "Contradiction: $req" ;;
##     esac
## done
echo "  Would: extract reqs → check each against code → create findings for FAILs"

## ─── Pattern 4: Build Failure Triage ─────────────────────────────
## REPLACES: Manually sorting "pre-existing subprocess warnings".
## FREQUENCY: Every sprint close.
##
## Logic: Diff current failures against known baseline.

echo ""
echo "--- Pattern 4: Build Failure Triage ---"
## In real use:
## BASELINE="reports/failure-baseline.json"
##
## ## Run build, capture failures
## failures=$(cd ~/git/mhubers/ace2 && ace-build test --json 2>&1 | jq '.failures')
##
## ## Diff against baseline
## new_failures=$(jq -n --argjson current "$failures" --slurpfile baseline "$BASELINE" \
##     '$current | map(select(. as $f | $baseline[0] | map(.test) | index($f.test) | not))')
##
## known_count=$(jq -n --argjson current "$failures" --slurpfile baseline "$BASELINE" \
##     '$current | map(select(. as $f | $baseline[0] | map(.test) | index($f.test))) | length')
##
## new_count=$(echo "$new_failures" | jq 'length')
##
## echo "Known: $known_count, New: $new_count"
##
## if [ "$new_count" -gt 0 ]; then
##     echo "-WARNING- New regressions:"
##     echo "$new_failures" | jq -r '.[] | "  \(.test): \(.error)"'
## else
##     echo "-PASS- Clean sprint — no new regressions"
## fi
echo "  Would: build → diff failures vs baseline → flag only NEW regressions"

## ─── Pattern 5: Essay Fact-Check Pipeline ────────────────────────
## REPLACES: Agent gave wrong verdicts, Mark re-verified manually.
## FREQUENCY: 685 fact-check messages in 90 days.
##
## Logic: LOCAL data first (free, reliable), web only if needed.

echo ""
echo "--- Pattern 5: Essay Fact-Check Pipeline ---"
## In real use:
## ESSAY="essays/usher-syndrome.md"
##
## ## Step 1: Extract claims (local LLM, free)
## claims=$(rondo "Extract all factual claims as JSON" --model local:qwen2.5:8b --field claims < "$ESSAY")
##
## ## Step 2: Check each claim locally first
## echo "$claims" | jq -r '.claims[]' | while read -r claim; do
##     ## Search local research files
##     local_match=$(grep -rl "$claim" research/ 2>/dev/null | head -1)
##
##     if [ -n "$local_match" ]; then
##         echo "  VERIFIED (local): $claim → $local_match"
##     else
##         ## No local data → check web (costs money)
##         web_check=$(rondo "Verify this medical claim: $claim" --model gemini:flash --field verified)
##         verified=$(echo "$web_check" | jq -r '.verified')
##         if [ "$verified" = "true" ]; then
##             echo "  VERIFIED (web): $claim"
##         else
##             echo "  UNVERIFIED: $claim → NEEDS HUMAN REVIEW"
##         fi
##     fi
## done
echo "  Would: extract claims → local check first → web only if needed"

## ─── Pattern 6: Multi-Platform Publish ───────────────────────────
## REPLACES: Separate LinkedIn + FB + Substack drafts per essay.
## FREQUENCY: 4,500+ publishing messages in 90 days.
##
## Logic: One essay → all platform variants with quality checks.

echo ""
echo "--- Pattern 6: Multi-Platform Publish ---"
## In real use:
## ESSAY="essays/usher-syndrome.md"
##
## ## Extract thesis (local, free)
## thesis=$(rondo "Extract the thesis and 3 key data points" --model local:qwen2.5:8b --field thesis < "$ESSAY")
##
## ## Generate each platform variant
## linkedin=$(echo "$thesis" | rondo "Write a LinkedIn post. Max 1500 chars. First person, professional but personal. No em dashes." --field post)
## facebook=$(echo "$thesis" | rondo "Write a Facebook post. Max 300 chars. Casual community tone. Include [link]." --field post)
## subtitle=$(echo "$thesis" | rondo "Write a Substack subtitle. Max 100 chars. Compelling, not clickbait." --field subtitle)
##
## ## Quality checks
## li_len=$(echo "$linkedin" | jq -r '.post' | wc -c)
## fb_len=$(echo "$facebook" | jq -r '.post' | wc -c)
##
## if [ "$li_len" -gt 1500 ]; then
##     echo "LinkedIn too long ($li_len chars) — regenerating with stricter limit..."
##     linkedin=$(echo "$thesis" | rondo "Rewrite shorter. HARD LIMIT 1500 chars." --field post)
## fi
##
## echo "LinkedIn ($li_len chars): $(echo "$linkedin" | jq -r '.post' | head -2)"
## echo "Facebook ($fb_len chars): $(echo "$facebook" | jq -r '.post')"
## echo "Subtitle: $(echo "$subtitle" | jq -r '.subtitle')"
echo "  Would: essay → thesis → LinkedIn + FB + subtitle with length checks"

## ─── Pattern 7: Community Reply + Variant Lookup ─────────────────
## REPLACES: Paste message → fact-check → variant lookup → draft.
## FREQUENCY: 123+ community reply messages in 90 days.
##
## Logic: Classify → fact-check → lookup → draft in Mark's voice.

echo ""
echo "--- Pattern 7: Community Reply + Variant Lookup ---"
## In real use:
## MESSAGE="$1"  # Incoming message as argument
##
## ## Classify question type
## category=$(echo "$MESSAGE" | rondo "Classify: genetics/testing/trials/living_with" --field category --model local:qwen2.5:8b)
## cat_type=$(echo "$category" | jq -r '.category')
##
## ## Fact-check incoming message
## errors=$(echo "$MESSAGE" | rondo "What factual errors are in this message about Usher syndrome?" --field errors)
##
## ## Variant lookup if genetics question
## if [ "$cat_type" = "genetics" ]; then
##     variant=$(echo "$MESSAGE" | grep -oP 'c\.\d+\w+' | head -1)
##     if [ -n "$variant" ]; then
##         lookup=$(rondo "Look up USH2A variant $variant in ClinVar" --field variant)
##         echo "Variant: $variant → $(echo "$lookup" | jq -r '.variant.classification')"
##     fi
## fi
##
## ## Draft reply
## reply=$(echo "$errors" | rondo "Draft a short reply in Mark's voice. Correct gently. Link relevant essay." --field reply)
## echo "Reply: $(echo "$reply" | jq -r '.reply')"
echo "  Would: classify → fact-check → variant lookup → draft reply"

## ─── Pattern 8: Research Freshness → Essay Impact ────────────────
## REPLACES: Manually checking "does this new paper matter?"
## FREQUENCY: 661 research messages in 90 days.
##
## Logic: Match scan results to essay index → classify impact.

echo ""
echo "--- Pattern 8: Research Freshness → Essay Impact ---"
## In real use:
## SCAN="data/nightly-scan/latest.json"
## ESSAYS="essays/essay-index.md"
##
## ## For each scan finding, check against published essays
## jq -r '.findings[] | @base64' "$SCAN" | while read -r finding_b64; do
##     finding=$(echo "$finding_b64" | base64 -d)
##     title=$(echo "$finding" | jq -r '.title')
##
##     ## Ask AI: does this impact any published essay?
##     impact=$(echo "$finding" | rondo "Does this research finding contradict or add to any of these essays? $(cat $ESSAYS)" --field impact)
##     level=$(echo "$impact" | jq -r '.impact.level')
##
##     case "$level" in
##         HIGH)   echo "  HIGH: $title → UPDATE ESSAY" ;;
##         MEDIUM) echo "  MEDIUM: $title → queue update" ;;
##         LOW)    echo "  LOW: $title → log only" ;;
##     esac
## done
echo "  Would: scan results → match to essays → HIGH/MEDIUM/LOW impact"

echo ""
echo "═══ All 8 patterns mined from real work ═══"
echo "Each replaces a manual task done 100+ times."
echo "Structured JSON returns make if/else branching possible."
