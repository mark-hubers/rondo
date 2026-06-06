# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
# rondo-meta: mode=http provider=gemini,grok,ollama category=review value="Fan-out to multiple providers with one prompt"

"""Rondo API: multi-provider dispatch (live).

Sends the same prompt to several ``model=`` values (HTTP adapters + optional local).
Uses ``dry_run=False`` so each call is a **real** dispatch (cost / latency apply).

Run::

    cd rondo && uv run python examples/api/multi_provider_dispatch.py

Requires provider API keys (and Ollama if you keep ``local:`` in the list).
"""

import json

from rondo.mcp_dispatch import rondo_run_file


def main() -> None:
    """Dispatch to multiple providers (live HTTP/local adapters)."""
    providers = ["gemini:gemini-flash-latest", "grok:grok-4.3", "local:qwen2.5:32b"]
    prompt = "Name 2 benefits of microservices."

    for provider in providers:
        result = json.loads(rondo_run_file(prompt=prompt, model=provider, dry_run=False))
        name = provider.split(":")[0]
        print(f"{name:8s} | status={result['status']} | engine={result.get('engine', 'dispatch')}")


if __name__ == "__main__":
    main()


# -- sig: mgh-6201.cd.bd955f.e008.a10800
