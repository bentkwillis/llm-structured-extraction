from __future__ import annotations

import json
import re

from pydantic import ValidationError

from app.schemas import ApiError, InvoiceExtractionResult


def parse_invoice_result(raw: str) -> InvoiceExtractionResult:
    """Parse raw model output into a strict invoice result.
    
    Handles:
    - Markdown-wrapped JSON (```json ... ```)
    - Trailing text after JSON
    
    Rejects:
    - Non-JSON output
    - Non-object JSON
    - Schema mismatches
    """
    
    # Step 1: extract JSON from markdown if present
    cleaned = raw.strip()
    
    # Look for ```json ... ``` blocks
    markdown_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', cleaned)
    if markdown_match:
        cleaned = markdown_match.group(1).strip()
    
    # Step 2: find the JSON object boundaries
    # If there's trailing text after the closing }, ignore it
    # But only if we have a valid object structure
    if cleaned.startswith('{'):
        # Find the matching closing brace
        depth = 0
        json_end = -1
        for idx, char in enumerate(cleaned):
            if char == '{':
                depth += 1
            elif char == '}':
                depth -= 1
                if depth == 0:
                    json_end = idx + 1
                    break
        if json_end > 0:
            cleaned = cleaned[:json_end]
    
    # Step 3: parse JSON
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError(
            ApiError(
                code="NON_JSON_OUTPUT",
                message="model output was not valid JSON",
                failure_point="parsing",
            ).model_dump_json()
        ) from exc
    
    # Step 4: ensure it's a dict
    if not isinstance(payload, dict):
        raise ValueError(
            ApiError(
                code="NON_OBJECT_JSON",
                message="model output must be a JSON object",
                failure_point="parsing",
            ).model_dump_json()
        )
    
    # Step 5: strict schema validation (no silent coercion, no extra fields)
    try:
        return InvoiceExtractionResult.model_validate(payload, strict=True)
    except ValidationError as exc:
        raise ValueError(
            ApiError(
                code="SCHEMA_MISMATCH",
                message="model output did not match the invoice schema",
                failure_point="parsing",
            ).model_dump_json()
        ) from exc
