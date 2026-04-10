# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Rondo smart return — prompt engineering for structured JSON output.

REQ-111 reqs 420-433: injects return-format instructions into prompts
so AI providers return structured JSON by default. Per-provider templates
tuned for optimal JSON compliance.

Import direction:
    smart_return.py → imports config (RondoConfig only)
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# -- Default return prompt — works across most providers
_DEFAULT_RETURN_PROMPT = """
RESPONSE FORMAT (mandatory):
Return ONLY valid JSON. No markdown fences. No text outside the JSON object.

Required fields in your JSON response:
- "passed" (boolean): true if the task succeeded or no issues found, false otherwise
- "confidence" (number 0.0 to 1.0): how confident you are in this assessment
- "result" (string): your main answer or finding
- "issues" (array of strings): problems found (empty array if none)
- "suggestions" (array of strings): actionable improvements (empty array if none)
- "metadata" (object): additional context — language detected, files reviewed, line counts, frameworks, anything relevant
- "_meta" (object): {"quality": number 1-10 rating of your own answer, "complete": boolean did you fully answer, "limitations": string what you might have missed}

Include ALL fields even if empty. Be thorough in metadata.
""".strip()

# -- Provider-specific templates (REQ-111 reqs 430-433)
_PROVIDER_TEMPLATES: dict[str, str] = {
    "gemini": """
RESPONSE FORMAT (mandatory):
Respond with a JSON object exactly matching this structure. No markdown. No explanation outside JSON.
{"passed": true, "confidence": 0.95, "result": "your answer", "issues": [], "suggestions": [], "metadata": {}, "_meta": {"quality": 8, "complete": true, "limitations": ""}}
Replace values with your actual assessment. Include ALL fields.
""".strip(),
    "grok": """
You are a JSON API endpoint. Return ONLY a valid JSON object.
CRITICAL: "_meta" MUST be a TOP-LEVEL field, NOT nested inside "metadata".
Fields at top level: "passed" (boolean), "confidence" (number 0-1), "result" (string), "issues" (array), "suggestions" (array), "metadata" (object with context), "_meta" (object with quality 1-10, complete boolean, limitations string).
No markdown. No explanation. JSON only.
""".strip(),
    "mistral": """
RESPONSE FORMAT (mandatory):
Return ONLY valid JSON. Do NOT wrap in markdown code fences (no ```json). No text outside the JSON.
Required top-level fields: "passed" (boolean), "confidence" (number 0-1), "result" (string), "issues" (array), "suggestions" (array), "metadata" (object), "_meta" (object with quality 1-10, complete boolean, limitations string).
Include ALL fields.
""".strip(),
    "openai": """
RESPONSE FORMAT (mandatory):
Return ONLY valid JSON. No markdown. No explanation outside JSON.
Required fields: "passed" (boolean), "confidence" (float 0-1), "result" (string), "issues" (array of strings), "suggestions" (array of strings), "metadata" (object), "_meta" (object: quality number 1-10, complete boolean, limitations string).
Include ALL fields even if empty.
""".strip(),
    "local": """
Reply with JSON only. No other text.
{"passed": true/false, "confidence": 0.0-1.0, "result": "your answer", "issues": [], "suggestions": [], "metadata": {}, "_meta": {"quality": 1-10, "complete": true/false, "limitations": ""}}
""".strip(),
}


def build_return_prompt(
    provider: str = "",
    field_name: str = "",
    custom_schema: str = "",
) -> str:
    """Build the return-format instruction to append to a user's prompt.

    REQ-111 reqs 420-425: COALESCE order:
        custom_schema (--return) → field_name (--field) + defaults → defaults only

    Args:
        provider: Provider name for template selection (e.g., "gemini", "grok").
        field_name: User-requested field name for main answer (e.g., "bugs").
        custom_schema: User-provided full return schema (overrides everything).

    Returns:
        Return prompt string to append to the user's prompt.
        Empty string if text mode (caller should not append anything).
    """
    # -- COALESCE level 1: user-specified full schema
    if custom_schema:
        return f"\nRESPONSE FORMAT: Return ONLY valid JSON matching this schema:\n{custom_schema}\n"

    # -- Pick provider template or default
    provider_key = provider.split(":")[0] if provider else ""
    template = _PROVIDER_TEMPLATES.get(provider_key, _DEFAULT_RETURN_PROMPT)

    # -- COALESCE level 2: named field + defaults
    if field_name:
        return f'\n{template}\nAlso put your main answer in the field: "{field_name}"\n'

    # -- COALESCE level 3: defaults only
    return f"\n{template}\n"


def validate_return_json(response: str) -> dict[str, Any]:
    """Validate and parse AI response as JSON with smart fallback.

    REQ-111 reqs 440-443: auto-rating + graceful degradation.

    Returns dict with:
        _json_valid (bool): was the response valid JSON?
        _fields_complete (bool): did it include all standard fields?
        + all parsed fields from the response
    """
    standard_fields = {"passed", "confidence", "result", "issues", "suggestions", "metadata"}

    # -- Try direct parse
    try:
        data = json.loads(response)
        if isinstance(data, dict):
            fields_present = standard_fields & set(data.keys())
            data["_json_valid"] = True
            data["_fields_complete"] = len(fields_present) >= 4  # -- at least 4 of 6
            return data
    except (json.JSONDecodeError, TypeError):
        pass

    # -- Try balanced-brace extraction (REQ-100 U-26 pattern)
    try:
        start = response.index("{")
        depth = 0
        for i, ch in enumerate(response[start:], start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidate = response[start : i + 1]
                    data = json.loads(candidate)
                    if isinstance(data, dict):
                        fields_present = standard_fields & set(data.keys())
                        data["_json_valid"] = True
                        data["_fields_complete"] = len(fields_present) >= 4
                        return data
    except (ValueError, json.JSONDecodeError, TypeError):
        pass

    # -- Graceful degradation (REQ-111 req 443)
    return {
        "passed": None,
        "result": response[:5000] if response else "",
        "_json_valid": False,
        "_fields_complete": False,
        "_parse_error": True,
    }


def normalize_response(data: dict[str, Any]) -> dict[str, Any]:
    """Normalize provider responses to a common JSON shape.

    REQ-111 reqs 470-475: regardless of which provider answered,
    the user always gets the same field structure.

    Handles:
    - Grok: _meta nested inside metadata → hoist to top level
    - Missing fields → fill with defaults
    - Extra fields → preserved (not stripped)
    """
    # -- REQ-111 req 474: Grok nests _meta inside metadata
    metadata = data.get("metadata", {})
    if isinstance(metadata, dict) and "_meta" in metadata and "_meta" not in data:
        data["_meta"] = metadata.pop("_meta")

    # -- REQ-111 req 472: ensure all standard fields present with defaults
    defaults = {
        "passed": None,
        "confidence": 0.0,
        "result": "",
        "issues": [],
        "suggestions": [],
        "metadata": {},
        "_meta": {"quality": 0, "complete": False, "limitations": "not provided"},
    }
    for field_name, default_value in defaults.items():
        if field_name not in data:
            data[field_name] = default_value

    # -- Ensure _meta has all sub-fields
    meta = data.get("_meta", {})
    if isinstance(meta, dict):
        meta.setdefault("quality", 0)
        meta.setdefault("complete", False)
        meta.setdefault("limitations", "not provided")

    return data


# -- sig: mgh-6201.cd.bd955f.5ead.a3bcd0
