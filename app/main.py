from __future__ import annotations

import json
import time
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from app.schemas import (
    ExtractInvoiceRequest,
    SuccessEnvelope,
    ErrorEnvelope,
    ApiError,
    ValidationConfig,
)
from app.validation import validate_extract_request

app = FastAPI()
cfg = ValidationConfig()

def _log(request_id: str | None, latency_ms: int, failure_point: str | None) -> None:
    print(
        json.dumps(
            {
                "request_id": request_id,
                "latency_ms": latency_ms,
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

@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(request: Request, exc: RequestValidationError):
    started = time.perf_counter()
    request_id = await _extract_request_id(request)

    first = exc.errors()[0] if exc.errors() else None
    if first:
        loc = ".".join(str(p) for p in first.get("loc",[]))
        msg = first.get("msg", "Invalid request payload")
        message = f"{loc}: {msg}" if loc else msg
    else:
        message = "Invalid request payload"
    
    latency_ms = int((time.perf_counter() - started) * 1000)
    return _validation_error_response(request_id, message, latency_ms)

@app.post("/v1/extract/invoice")
async def extract_invoice(req: ExtractInvoiceRequest, request: Request):
    started = time.perf_counter()
    request_id = req.request_id

    try:
        validate_extract_request(req, cfg)

        body = SuccessEnvelope(
            request_id=request_id,
            data={"status": "validated"},
        )
        latency_ms = int((time.perf_counter() - started) * 1000)
        _log(request_id, latency_ms, None)
        return JSONResponse(status_code=200, content=body.model_dump())

    except ValueError as e:
        parsed = ApiError.model_validate_json(str(e))
        latency_ms = int((time.perf_counter() - started) * 1000)
        _log(request_id, latency_ms, parsed.failure_point)
        err = ErrorEnvelope(request_id=request_id, error=parsed)
        return JSONResponse(status_code=400, content=err.model_dump())