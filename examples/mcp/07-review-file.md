# rondo-meta: mode=subprocess provider=anthropic category=review value="File-scoped review workflow for real source files"

# 07 — File Review Workflow

Review a real file path without manual copy/paste.

```text
rondo_review_file(
    path="/absolute/path/to/src/module.py",
    tier="default",
    dry_run=False
)
```

Variation:

```text
rondo_review_file(
    path="/absolute/path/to/src/module.py",
    providers='["gemini:gemini-2.5-flash","grok:grok-3"]',
    dry_run=False
)
```

Why useful:
- Fast daily review loop with consistent structured output.
