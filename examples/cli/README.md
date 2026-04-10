# Rondo CLI Examples

10 examples showing every way to use Rondo from the command line.

## Prerequisites

- Rondo installed (`pip install -e rondo/`)
- At least one provider key set (e.g., `GEMINI_API_KEY`)
- Run `rondo providers` to check which providers are available

## Examples

```bash
# 1. Simple prompt → structured JSON back
rondo "What is Docker?"

# 2. Choose a specific provider
rondo "Explain Kubernetes" --model gemini:flash

# 3. Pipe data in via stdin
echo "import os; os.system('rm -rf /')" | rondo "Is this code safe?"

# 4. Named return field — scripts always know where to find the answer
rondo "Find security issues" --field vulnerabilities

# 5. Plain text mode (skip JSON, get human-readable output)
rondo "Explain Docker in simple terms" --text

# 6. Run a YAML round file (multiple tasks defined in YAML)
rondo run examples/rounds/01-simple-review.yaml --dry-run

# 7. Budget-capped batch (stops before exceeding limit)
rondo run examples/rounds/03-budget-capped.yaml --max-budget 0.50

# 8. Multi-provider comparison (same task to 3 AIs)
rondo run examples/rounds/02-multi-provider.yaml --dry-run

# 9. View provider health and learned scores
rondo providers
rondo learn

# 10. Chain commands — use jq to extract fields for the next step
rondo "Find bugs" --field bugs < app.py | jq -r '.bugs[]' | while read bug; do
    rondo "Fix this bug: $bug" --field fix
done
```

## Output Format

Default: structured JSON with smart return fields.

```json
{
  "passed": true,
  "confidence": 0.95,
  "result": "your answer here",
  "issues": [],
  "suggestions": [],
  "metadata": {},
  "_meta": {"quality": 9, "complete": true, "limitations": "..."}
}
```

- `--text` → plain text (no JSON)
- `--field <name>` → main answer in a named field
- `--model <provider:model>` → choose provider

## If Something Fails

- `rondo providers` → check which providers are up
- `rondo learn` → see provider quality scores
- Add `--dry-run` to any command to see what would be sent without dispatching
