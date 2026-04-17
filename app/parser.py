from __future__ import annotations

import json
import re

from pydantic import ValidationError

from app.schemas import ApiError, InvoiceExtractionResult


def _json_object_candidates(text: str):
    in_string = False
    escape = False
    depth = 0
    start: int | None = None

    for idx, char in enumerate(text):
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
            continue

        if char == "{":
            if depth == 0:
                start = idx
            depth += 1
            continue

        if char == "}" and depth > 0:
            depth -= 1
            if depth == 0 and start is not None:
                yield text[start : idx + 1]
                start = None


def _extract_payload(raw: str) -> dict:
    sources = [raw.strip()]
    markdown_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', raw.strip())
    if markdown_match:
        sources.insert(0, markdown_match.group(1).strip())

    saw_any_json_object = False
    last_dict_payload: dict | None = None

    for source in sources:
        for candidate in _json_object_candidates(source):
            saw_any_json_object = True
            try:
                parsed = json.loads(candidate)
            except json.JSONDecodeError:
                continue

            if isinstance(parsed, dict):
                last_dict_payload = parsed

    if last_dict_payload is not None:
        return last_dict_payload

    if saw_any_json_object:
        raise ValueError(
            ApiError(
                code="NON_JSON_OUTPUT",
                message="model output was not valid JSON",
                failure_point="parsing",
            ).model_dump_json()
        )

    raise ValueError(
        ApiError(
            code="NON_JSON_OUTPUT",
            message="model output was not valid JSON",
            failure_point="parsing",
        ).model_dump_json()
    )


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
    
    payload = _extract_payload(raw)

    # Strict schema validation (no silent coercion, no extra fields)
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
