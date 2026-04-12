# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
# rondo-meta: mode=subprocess provider=anthropic category=basic value="Smart-return JSON structure and parsing flow"

"""Rondo API Example 02: Smart Return — validate + normalize responses.

Shows how Rondo validates AI responses and normalizes them to a
consistent JSON shape regardless of which provider answered.
"""

import json

from rondo.smart_return import build_return_prompt, normalize_response, validate_return_json


def main() -> None:
    """Demonstrate smart return validation and normalization."""
    # -- 1. Build a return prompt for a specific provider
    gemini_prompt = build_return_prompt(provider="gemini:flash")
    grok_prompt = build_return_prompt(provider="grok:grok-3")
    print(f"Gemini template: {len(gemini_prompt)} chars")
    print(f"Grok template: {len(grok_prompt)} chars")

    # -- 2. Validate a JSON response (simulated)
    good_response = json.dumps(
        {
            "passed": True,
            "confidence": 0.95,
            "result": "All tests pass",
            "issues": [],
            "suggestions": ["Add more edge case tests"],
            "metadata": {"language": "python"},
            "_meta": {"quality": 9, "complete": True, "limitations": ""},
        }
    )
    validated = validate_return_json(good_response)
    print(f"Valid JSON: {validated['_json_valid']}")
    print(f"Fields complete: {validated['_fields_complete']}")

    # -- 3. Handle bad responses gracefully
    bad_response = "This is not JSON at all"
    bad_validated = validate_return_json(bad_response)
    print(f"Bad response: json_valid={bad_validated['_json_valid']}, parse_error={bad_validated.get('_parse_error')}")

    # -- 4. Normalize (fills missing fields, hoists nested _meta)
    partial = {"passed": True, "result": "answer"}
    normalized = normalize_response(partial)
    print(f"After normalize: {len(normalized)} fields (was 2)")


if __name__ == "__main__":
    main()


# -- sig: mgh-6201.cd.bd955f.e002.a10200
