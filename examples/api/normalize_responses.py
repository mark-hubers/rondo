# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
# rondo-meta: mode=subprocess provider=anthropic category=config value="Normalizing varied model payloads into one stable shape"

"""Rondo API: Normalize Provider Responses.

Each AI provider returns JSON slightly differently.
normalize_response() makes them all consistent.
"""

from rondo.smart_return import normalize_response, validate_return_json


def main() -> None:
    """Handle each provider quirk via normalization."""
    # Grok: nests _meta inside metadata
    grok = validate_return_json('{"passed": true, "result": "ok", "metadata": {"_meta": {"quality": 8}}}')
    print(f"Grok before: _meta in metadata={'_meta' in grok.get('metadata', {})}")
    grok = normalize_response(grok)
    print(f"Grok after:  _meta at top level={'_meta' in grok}, quality={grok['_meta']['quality']}")

    # Gemini: missing _meta entirely
    gemini = normalize_response(validate_return_json('{"passed": true, "result": "ok"}'))
    print(f"\nGemini: _meta filled with defaults: quality={gemini['_meta']['quality']}")

    # Mistral: markdown fences (extract_json handles this)
    mistral = normalize_response(
        validate_return_json('```json\n{"passed": true, "result": "ok", "_meta": {"quality": 9}}\n```')
    )
    print(f"Mistral: json_valid={mistral['_json_valid']}, quality={mistral['_meta']['quality']}")

    print("\nAll 3 -> same field structure after normalize_response()")


if __name__ == "__main__":
    main()


# -- sig: mgh-6201.cd.bd955f.e006.a10600
