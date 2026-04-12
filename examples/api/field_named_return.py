# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
# rondo-meta: mode=subprocess provider=anthropic category=basic value="Named JSON field contract for script-friendly outputs"

"""Rondo API: Named Return Fields.

Use build_return_prompt(field_name="bugs") to tell the AI
to put its main answer in a specific field.
Scripts can then always do: jq .bugs
"""

from rondo.smart_return import build_return_prompt


def main() -> None:
    """Show how --field adds a named field to the return prompt."""
    # Without field: generic "result" field
    default = build_return_prompt(provider="gemini:flash")
    print(f"Default prompt ({len(default)} chars): mentions 'result' field")

    # With field: specific named field
    with_field = build_return_prompt(provider="gemini:flash", field_name="bugs")
    print(f"With --field bugs ({len(with_field)} chars): mentions 'bugs' field")
    assert "bugs" in with_field

    # With custom schema: full override
    custom = build_return_prompt(custom_schema='{"answer": "string", "score": "number"}')
    print(f"Custom schema ({len(custom)} chars): user-defined fields")
    assert "answer" in custom

    print("\nCOALESCE: --return > --field > defaults")


if __name__ == "__main__":
    main()


# -- sig: mgh-6201.cd.bd955f.e009.a10900
