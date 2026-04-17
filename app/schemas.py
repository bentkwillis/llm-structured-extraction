from __future__ import annotations

from pydantic import BaseModel, Field, ConfigDict

class ExtractInvoiceRequest(BaseModel):
    request_id: str = Field(min_length=1, max_length=128)
    document_type: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1)

class InvoiceExtractionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    supplier_name: str | None = None
    invoice_number: str | None = None
    invoice_date: str | None = None
    due_date: str | None = None
    currency: str | None = None
    subtotal: float | None = None
    tax: float | None = None
    total: float | None = None

class ApiError(BaseModel):
    code: str
    message: str
    failure_point: str # validation | model | parsing | post_validation

class ErrorEnvelope(BaseModel):
    success: bool = False
    request_id: str | None
    error: ApiError

class SuccessEnvelope(BaseModel):
    success: bool = True
    request_id: str
    data: InvoiceExtractionResult
    warnings: list[str] = Field(default_factory=list)  # Non-fatal validation issues

class ValidationConfig(BaseModel):
    model_config = ConfigDict(frozen=True)
    min_text_chars: int = 20
    max_text_chars: int = 50_000
    allowed_document_type: str = "invoice"