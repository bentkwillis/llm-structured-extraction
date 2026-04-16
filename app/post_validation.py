from __future__ import annotations

import re
from datetime import date

from app.schemas import ApiError, InvoiceExtractionResult

ISO_CURRENCY = {
    "USD", "EUR", "GBP", "CAD", "AUD", "NZD", "JPY", "CNY", "CHF", "SEK", "NOK", "DKK"
}

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

def _validate_date(value: str | None, field_name: str) -> None:
    if value is None:
        return
    if not DATE_RE.match(value):
        raise ValueError(
            ApiError(
                code="INVALID_DATE_FORMAT",
                message=f"{field_name} must be YYYY-MM-DD",
                failure_point="post_validation",
            ).model_dump_json()
        )
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(
            ApiError(
                code="INVALID_DATE_VALUE",
                message=f"{field_name} is not a real calendar date",
                failure_point="post_validation",
            ).model_dump_json()
        ) from exc
    
def validate_invoice_result(result: InvoiceExtractionResult) -> None:
    _validate_date(result.invoice_date, "invoice_date")
    _validate_date(result.due_date, "due_date")

    if result.currency is not None and result.currency not in ISO_CURRENCY:
        raise ValueError(
            ApiError(
                code="INVALID_CURRENCY",
                message="currency must be a valid ISO 4217 code",
                failure_point="post_validation",
            ).model_dump_json()
        )
    
    if result.subtotal is not None and result.tax is not None and result.total is not None:
        expected_total = round(result.subtotal + result.tax, 2)
        actual_total = round(result.total, 2)
        if expected_total != actual_total:
            raise ValueError(
                ApiError(
                    code="TOTAL_MISMATCH",
                    message="subtotal + tax must equal total",
                    failure_point="post_validation",
                ).model_dump_json()
            )