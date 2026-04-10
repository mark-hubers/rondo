# Rondo CLI Examples

10 examples showing every way to use Rondo from the command line.
Each example is a one-liner you can copy-paste and run.

## Quick Start

```bash
# 1. Simple prompt → JSON
rondo "What is Docker?"

# 2. Choose a specific provider
rondo "Explain Kubernetes" --model gemini:flash

# 3. Pipe data in
echo "import os; os.system('rm -rf /')" | rondo "Is this code safe?"

# 4. Review a file
rondo "Review this code for bugs" ./src/app.py

# 5. Named return field
rondo "Find security issues" --field vulnerabilities

# 6. Plain text mode (no JSON)
rondo "Explain Docker in simple terms" --text

# 7. Dry run (see what would be sent)
rondo run examples/01-simple-review.yaml --dry-run

# 8. Budget-capped batch
rondo run examples/03-budget-capped.yaml --max-budget 0.50

# 9. Multi-provider comparison
rondo run examples/02-multi-provider.yaml

# 10. Chain commands (pipe JSON output to next step)
rondo "Find bugs" --field bugs < app.py | jq '.bugs[]' | rondo "Fix this bug"
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

Use `--text` for plain text output.
Use `--field <name>` to put the main answer in a named field.
