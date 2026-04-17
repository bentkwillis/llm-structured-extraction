from __future__ import annotations

import re
from datetime import date

from app.schemas import ApiError, InvoiceExtractionResult

ISO_CURRENCY = {
    "USD", "EUR", "GBP", "CAD", "AUD", "NZD", "JPY", "CNY", "CHF", "SEK", "NOK", "DKK"
}

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

def _validate_date(value: str | None, field_name: str) -> str | None:
    """Validate date format. Return warning message or None if valid."""
    if value is None:
        return None
    if not DATE_RE.match(value):
        return f"{field_name} is not in YYYY-MM-DD format"
    try:
        date.fromisoformat(value)
    except ValueError:
        return f"{field_name} is not a real calendar date"
    return None
    
def validate_invoice_result(result: InvoiceExtractionResult) -> list[str]:
    """Validate invoice result. Return list of warnings (never raises)."""
    warnings: list[str] = []

    # Date validation: warn but don't fail
    date_warning = _validate_date(result.invoice_date, "invoice_date")
    if date_warning:
        warnings.append(date_warning)

    date_warning = _validate_date(result.due_date, "due_date")
    if date_warning:
        warnings.append(date_warning)

    # Currency validation: fail if invalid
    if result.currency is not None and result.currency not in ISO_CURRENCY:
        raise ValueError(
            ApiError(
                code="INVALID_CURRENCY",
                message="currency must be a valid ISO 4217 code",
                failure_point="post_validation",
            ).model_dump_json()
        )

    # Totals validation: warn if inconsistent
    if (
        result.subtotal is not None
        and result.tax is not None
        and result.total is not None
    ):
        expected_total = round(result.subtotal + result.tax, 2)
        actual_total = round(result.total, 2)
        if expected_total != actual_total:
            warnings.append(
                f"totals do not match: subtotal ({result.subtotal}) + tax ({result.tax}) = {expected_total}, but total is {actual_total}"
            )

    return warnings