"""Rondo API Example 01: Simple Dispatch.

The simplest way to use Rondo from Python.
Send a prompt, get structured JSON back.
"""

import json

from rondo.mcp_dispatch import rondo_run_file
from rondo.smart_return import normalize_response, validate_return_json


def main() -> None:
    """Dispatch a simple prompt and print the structured result."""
    # -- Send prompt to default provider
    raw = rondo_run_file(
        prompt="What are 3 benefits of unit testing?",
        model="sonnet",
        dry_run=True,  # -- set False for real dispatch
    )
    result = json.loads(raw)
    print(f"Status: {result['status']}")

    # -- For real dispatch, validate + normalize the response
    if result.get("tasks") and not result.get("dry_run", True):
        output = result["tasks"][0].get("raw_output", "")
        validated = validate_return_json(output)
        normalized = normalize_response(validated)
        print(f"Passed: {normalized['passed']}")
        print(f"Quality: {normalized['_meta']['quality']}/10")
        print(f"Answer: {normalized['result'][:100]}")


if __name__ == "__main__":
    main()


# -- sig: mgh-6201.cd.bd955f.e001.a10100
