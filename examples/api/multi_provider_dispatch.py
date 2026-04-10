"""Rondo API: Multi-Provider Dispatch.

Send the same question to multiple AI providers and compare.
Uses rondo_run_file with different model parameters.
"""

import json

from rondo.mcp_dispatch import rondo_run_file


def main() -> None:
    """Dispatch to multiple providers (dry run)."""
    providers = ["gemini:gemini-2.5-flash", "grok:grok-3", "local:qwen2.5:32b"]
    prompt = "Name 2 benefits of microservices."

    for provider in providers:
        result = json.loads(rondo_run_file(prompt=prompt, model=provider, dry_run=True))
        name = provider.split(":")[0]
        print(f"{name:8s} | status={result['status']} | engine={result.get('engine', 'dispatch')}")


if __name__ == "__main__":
    main()


# -- sig: mgh-6201.cd.bd955f.e008.a10800
