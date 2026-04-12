# rondo-meta: mode=subprocess provider=anthropic category=config value="Loading and dispatching YAML round definitions via API"

"""Rondo API: Load YAML Round Files.

Round files define AI tasks in YAML, JSON, or Python.
YAML is the simplest — no Python knowledge needed.
"""

import tempfile
from pathlib import Path

import yaml

from rondo.engine import load_round_file
from rondo.round_loader import load_round


def main() -> None:
    """Load a YAML round file and inspect tasks."""
    with tempfile.TemporaryDirectory() as tmp:
        yaml_file = Path(tmp) / "review.yaml"
        yaml_file.write_text(
            yaml.dump(
                {
                    "name": "code-review",
                    "tasks": [
                        {"name": "security", "instruction": "Scan for vulnerabilities", "model": "gemini:flash"},
                        {"name": "style", "instruction": "Check coding style"},
                    ],
                }
            )
        )

        rd = load_round(str(yaml_file))
        print(f"Round: {rd.name}, Tasks: {len(rd.tasks)}")
        for t in rd.tasks:
            print(f"  {t.name}: {t.instruction} (model={t.model or 'default'})")

        rd2 = load_round_file(str(yaml_file))
        assert rd2.name == rd.name
        print("Also works via load_round_file()")


if __name__ == "__main__":
    main()


# -- sig: mgh-6201.cd.bd955f.e005.a10500
