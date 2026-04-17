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
    stage_latency_ms: dict[str, int] | None = None,
    retry_count: int | None = None,
) -> None:
    print(
        json.dumps(
            {
                "request_id": request_id,
                "latency_ms": latency_ms,
                "text_chars": text_chars,
                "prompt_chars": prompt_chars,
                "failure_point": failure_point,
                "stage_latency_ms": stage_latency_ms,
                "retry_count": retry_count,
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

def _safe_api_error_from_value_error(e: Exception) -> ApiError:
    if all(hasattr(e, attr) for attr in ("code", "message", "failure_point")):
        code = getattr(e, "code")
        message = getattr(e, "message")
        failure_point = getattr(e, "failure_point")
        if all(isinstance(v, str) and v for v in (code, message, failure_point)):
            return ApiError(code=code, message=message, failure_point=failure_point)

    try:
        return ApiError.model_validate_json(str(e))
    except Exception:
        return ApiError(
            code="INTERNAL_ERROR",
            message="unexpected processing error",
            failure_point="system",
        )


@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(request: Request, exc: RequestValidationError):
    started = time.perf_counter()
    request_id = await _extract_request_id(request)

    first = exc.errors()[0] if exc.errors() else None
    if first:
        loc = ".".join(str(p) for p in first.get("loc", []))
        msg = first.get("msg", "Invalid request payload")
        message = f"{loc}: {msg}" if loc else msg
    else:
        message = "Invalid request payload"

    latency_ms = int((time.perf_counter() - started) * 1000)
    return _validation_error_response(request_id, message, latency_ms)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    started = time.perf_counter()
    request_id = await _extract_request_id(request)

    latency_ms = int((time.perf_counter() - started) * 1000)
    _log(
        request_id = request_id,
        latency_ms=latency_ms,
        failure_point="system",
        text_chars=None,
        prompt_chars=None,
    )

    err = ErrorEnvelope(
        request_id=request_id,
        error=ApiError(
            code="INTERNAL_ERROR",
            message="an unexpected error occurred",
            failure_point="system",
        ),
    )
    return JSONResponse(status_code=500, content=err.model_dump())

@app.post("/v1/extract/invoice")
async def extract_invoice(req: ExtractInvoiceRequest):
    started = time.perf_counter()
    request_id = req.request_id
    text_chars = len(req.text)
    prompt_chars: int | None = None
    stage_latency_ms: dict[str, int] = {}

    try:
        t0 = time.perf_counter()
        validate_extract_request(req, cfg)
        stage_latency_ms["validation"] = int((time.perf_counter() - t0) * 1000)

        t0 = time.perf_counter()
        prompt = build_invoice_prompt(req.text)
        prompt_chars = len(prompt)
        stage_latency_ms["prompt_build"] = int((time.perf_counter() - t0) * 1000)

        if not prompt.strip():
            raise ValueError(
                ApiError(
                    code="INVALID_REQUEST",
                    message="prompt is empty after prompt build",
                    failure_point="validation",
                ).model_dump_json()
            )
        
        if text_chars < cfg.min_text_chars:
            raise ValueError(
                ApiError(
                    code="TEXT_TOO_SHORT",
                    message=f"text must be at least {cfg.min_text_chars} characters",
                    failure_point="validation",
                ).model_dump_json()
            )
            

        t0 = time.perf_counter()
        raw_model_output = extract_invoice_json(
            prompt=prompt,
            request_id=request_id,
            timeout_seconds=8.0,
        )
        stage_latency_ms["model"] = int((time.perf_counter() - t0) * 1000)

        t0 = time.perf_counter()
        parsed_result = parse_invoice_result(raw_model_output)
        stage_latency_ms["parsing"] = int((time.perf_counter() - t0) * 1000)

        t0 = time.perf_counter()
        warnings = validate_invoice_result(parsed_result)
        stage_latency_ms["post_validation"] = int((time.perf_counter() - t0) * 1000)

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
            stage_latency_ms=stage_latency_ms,
            retry_count=None,
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
            stage_latency_ms=stage_latency_ms,
            retry_count=None,
        )
        err = ErrorEnvelope(request_id=request_id, error=parsed)
        return JSONResponse(status_code=400, content=err.model_dump())
    
