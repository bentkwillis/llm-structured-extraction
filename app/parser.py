from __future__ import annotations
import json
from app.schemas import InvoiceExtractionResult, ApiError

def parse_invoice_result(raw: str) -> InvoiceExtractionResult:
    try:
        payload = json.loads(raww)
    except json.JSONDecodeError as exc:
        raise ValueError(
            ApiError(
                cide="NON_JSON_OUTPUT",
                message="model output was not valid JSON",
                failure_point="parsing",
            ).model_dump_json()
        ) from exc
    
    try:
        return InvoiceExtractionResult.model_validate(payload)
    except Exception as exc:
        raise ValueError(
            ApiError(
                code="SCHEMA_MISMATCH",
                message="model output did not match the invoice schema",
                failure_point="parsing",
            ).model_dump_json()
        ) from exc