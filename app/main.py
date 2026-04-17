from __future__ import annotations

import json
import time
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from app.parser import parse_invoice_result
from app.post_validation import validate_invoice_result
from app.validation import validate_extract_request
from app.prompt_builder import build_invoice_prompt
from app.llm_client import extract_invoice_json

from app.schemas import (
    ExtractInvoiceRequest,
    SuccessEnvelope,
    ErrorEnvelope,
    ApiError,
    ValidationConfig,
)

app = FastAPI()
cfg = ValidationConfig()

def _log(
    request_id: str | None,
    latency_ms: int,
    failure_point: str | None,
    text_chars: int | None = None,
    prompt_chars: int | None = None,
) -> None:
    print(
        json.dumps(
            {
                "request_id": request_id,
                "latency_ms": latency_ms,
                "text_chars": text_chars,
                "prompt_chars": prompt_chars,
                "failure_point": failure_point,
            }
        )
    )

async def _extract_request_id(request: Request) -> str | None:
    try:
        payload = await request.json()
        if isinstance(payload, dict):
            rid = payload.get("request_id")
            if isinstance(rid, str) and rid.strip():
                return rid
    except Exception:
        return None
    return None

def _validation_error_response(
        request_id: str | None, message: str, latency_ms: int
) -> JSONResponse:
    err = ErrorEnvelope(
        request_id=request_id,
        error=ApiError(
            code="INVALID_REQUEST",
            message=message,
            failure_point="validation",
        ),
    )
    _log(request_id, latency_ms, "validation")
    return JSONResponse(status_code=400, content=err.model_dump())

def _safe_api_error_from_value_error(e: ValueError) -> ApiError:
    try:
        return ApiError.model_validate_json(str(e))
    except Exception:
        return ApiError(
            code="INTERNAL_ERROR",
            message="unexpected processing error",
            failure_point="model",
        )

@app.post("/v1/extract/invoice")
async def extract_invoice(req: ExtractInvoiceRequest):
    started = time.perf_counter()
    request_id = req.request_id
    text_chars = len(req.text)
    prompt_chars: int | None = None

    try:
        validate_extract_request(req, cfg)

        prompt = build_invoice_prompt(req.text)
        prompt_chars = len(prompt)

        raw_model_output = extract_invoice_json(
            prompt=prompt,
            request_id=request_id,
            timeout_seconds=8.0,
        )

        parsed_result = parse_invoice_result(raw_model_output)
        warnings = validate_invoice_result(parsed_result)

        body = SuccessEnvelope(
            request_id=request_id,
            data=parsed_result,
            warnings=warnings,
        )

        latency_ms = int((time.perf_counter() - started) * 1000)
        _log(
            request_id=request_id,
            latency_ms=latency_ms,
            failure_point=None,
            text_chars=text_chars,
            prompt_chars=prompt_chars,
        )
        return JSONResponse(status_code=200, content=body.model_dump())

    except ValueError as e:
        parsed = _safe_api_error_from_value_error(e)
        latency_ms = int((time.perf_counter() - started) * 1000)
        _log(
            request_id=request_id,
            latency_ms=latency_ms,
            failure_point=parsed.failure_point,
            text_chars=text_chars,
            prompt_chars=prompt_chars,
        )
        err = ErrorEnvelope(request_id=request_id, error=parsed)
        return JSONResponse(status_code=400, content=err.model_dump())