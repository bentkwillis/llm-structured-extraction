from __future__ import annotations

import json
import time
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

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

@app.post("/v1/extract/invoice")
async def extract_invoice(req: ExtractInvoiceRequest, request: Request):
    started = time.perf_counter()
    request_id = req.request_id

    try:
        validate_extract_request(req, cfg)

        # Placeholder success reponse for Step 1 only (no LLM call yet)
        body = SuccessEnvelope(
            request_id=request_id,
            data={"status": "validated"},
        )
        latency_ms = int((time.perf_counter() - started) * 1000)
        print(
            json.dumps(
                {
                    "request_id": request_id,
                    "latency_ms": latency_ms,
                    "failure_point": None,
                }
            )
        )
        return JSONResponse(status_code=200, content=body.model_dump())
    
    except ValueError as e:
        parsed = ApiError.model_validate_json(str(e))
        latency_ms = int((time.perf_counter() - started) * 1000)
        print(
            json.dumps(
                {
                    "request_id": request_id,
                    "latency_ms": latency_ms,
                    "failure_point": parsed.failure_point,
                }
            )
        )
        err = ErrorEnvelope(request_id=request_id, error=parsed)
        return JSONResponse(status_code=400, content=err.model_dump())