# rondo-meta: mode=subprocess provider=anthropic category=config value="Per-call override behavior for config-backed dispatch options"

"""Rondo API: Config Template Override.

Rondo has built-in return prompt templates for each AI provider.
You can override any template in ~/.rondo/config.toml without
changing Rondo's code.

COALESCE order: your config.toml -> code defaults -> generic default
"""

import os
import tempfile
from pathlib import Path

from rondo.smart_return import build_return_prompt


def main() -> None:
    """Show how config.toml overrides code templates."""
    # -- Default: uses code template for Gemini
    default_prompt = build_return_prompt(provider="gemini:flash")
    print(f"Default Gemini template: {len(default_prompt)} chars")
    print(f"First line: {default_prompt.strip().splitlines()[0]}")

    # -- Override: create a custom config with a different template
    with tempfile.TemporaryDirectory() as tmp:
        config = Path(tmp) / "config.toml"
        config.write_text('[return_prompts.gemini]\nprompt = "CUSTOM: Return JSON with fields: answer, confidence."\n')
        os.environ["RONDO_CONFIG"] = str(config)
        try:
            custom_prompt = build_return_prompt(provider="gemini:flash")
            print(f"\nCustom Gemini template: {len(custom_prompt)} chars")
            print(f"Content: {custom_prompt.strip()}")
        finally:
            del os.environ["RONDO_CONFIG"]

    print("\nCOALESCE: config.toml wins over code defaults")


if __name__ == "__main__":
    main()


# -- sig: mgh-6201.cd.bd955f.e007.a10700
