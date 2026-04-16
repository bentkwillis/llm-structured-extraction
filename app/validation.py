from __future__ import annotations

from app.schemas import ExtractInvoiceRequest, ValidationConfig, ApiError

def validate_extract_request(payload: ExtractInvoiceRequest, cfg: ValidationConfig) -> None:
    # Fail fast on unsupported type
    if payload.document_type != cfg.allowed_document_type:
        raise ValueError(
            ApiError(
                code="INVALID_DOCUMENT_TYPE",
                message=f"document_type must be '{cfg.allowed_document_type}'",
                failure_point="validation",
            ).model_dump_json()

        )

    text_len = len(payload.text.strip())

    # Empty or too-short text
    if text_len < cfg.min_text_chars:
        raise ValueError(
            ApiError(
                code="TEXT_TOO_SHORT",
                message=f"text must be at least {cfg.min_text_chars} characters",
                failure_point="validation",
            ).model_dump_json()
        )
    
    # Oversized payload
    if text_len > cfg.max_text_chars:
        raise ValueError(
            ApiError(
                code="TEXT_TOO_LARGE",
                message=f"text must be <= {cfg.max_text_chars} characters",
                failure_point="validation",
            ).model_dump_json()
        )