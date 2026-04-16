from __future__ import annotations

import json

from pydantic import ValidationError

from app.schemas import ApiError, InvoiceExtractionResult


def parse_invoice_result(raw: str) -> InvoiceExtractionResult:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(
            ApiError(
                code="NON_JSON_OUTPUT",
                message="model output was not valid JSON",
                failure_point="parsing",
            ).model_dump_json()
        ) from exc

    if not isinstance(payload, dict):
        raise ValueError(
            ApiError(
                code="NON_OBJECT_JSON",
                message="model output must be a JSON object",
                failure_point="parsing",
            ).model_dump_json()
        )

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
