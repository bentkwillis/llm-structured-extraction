# llm-structured-extraction

## Overview
`llm-structured-extraction` is a backend API service for extracting structured invoice fields from raw text using an LLM. It is designed for reliable, production-style structured extraction with strict contracts, deterministic behavior, and explicit failure handling. The service is designed to make LLM-based extraction predictable, debuggable, and contract-driven. The model is configured via environment variables, so the service is not tightly coupled to a single provider.

## Features
- Strict output schema enforcement with fixed invoice fields
- Robust parser for noisy model output (including markdown-wrapped and trailing text scenarios)
- Failure-aware request flow with typed error codes
- Boundary-first input validation before any model call
- Structured logging with request IDs, stage attribution, and latency signals
- Deterministic response envelope across success and failure paths
- Controlled timeout behavior and limited retry only for transient model failures, bounded by a total request timeout budget

## Architecture
The service is organized into explicit layers:

- **API layer**: endpoint routing, envelope shaping, error normalization
- **Validation layer**: request boundary checks and contract gating
- **Prompt builder**: deterministic extraction prompt generation
- **LLM client**: timeout-bounded model invocation with controlled retries
- **Parser**: strict JSON extraction and schema validation from model output
- **Post-validation**: semantic checks (dates, currency, totals) with policy-driven warnings/errors

## API Contract

### Endpoint
`POST /v1/extract/invoice`

### Request (example)
```json
{
  "request_id": "req-001",
  "document_type": "invoice",
  "text": "NORTHSHORE INDUSTRIAL PARTS, INC.\nInvoice No: NS-78431-A\nIssue Date: 2026-04-11\nDue: 2026-05-11\nCurrency: USD\nSubtotal: 1054.00\nTax: 86.96\nAmount Due: 1140.96"
}
```

### Success Response (example)
```json
{
  "success": true,
  "request_id": "req-001",
  "data": {
    "supplier_name": "NORTHSHORE INDUSTRIAL PARTS, INC.",
    "invoice_number": "NS-78431-A",
    "invoice_date": "2026-04-11",
    "due_date": "2026-05-11",
    "currency": "USD",
    "subtotal": 1054.0,
    "tax": 86.96,
    "total": 1140.96
  },
  "warnings": []
}
```

### Error Response (example)
```json
{
  "success": false,
  "request_id": "req-001",
  "error": {
    "code": "MODEL_TIMEOUT",
    "message": "model request timed out after retries",
    "failure_point": "model"
  }
}
```

### Response Guarantees
- Response envelope is consistent across all outcomes (`success`, `request_id`, and `data` or `error`)
- All invoice schema fields are always present in success responses (missing values are `null`)
- No extra fields are allowed in extracted output
- Errors are typed and always include `failure_point`

## Observability
- `request_id` is the trace key across request, model, and failure logs
- Logs include `request_id`, `failure_point` (`validation` / `model` / `parsing` / `post_validation`), and latency
- Model logs include usage metrics when available (input/output/total tokens)

## Failure Handling
The service treats model output as untrusted and handles failures explicitly:

- **Invalid input**: rejected before model invocation (`validation`)
- **Model errors**: mapped to typed codes such as `MODEL_TIMEOUT`, `MODEL_PROVIDER_ERROR` (`model`)
- **Parsing failures**: malformed/non-JSON/schema mismatch mapped to parser errors (`parsing`)
- **Post-validation failures**: semantic violations mapped to typed validation outcomes (`post_validation`)

All failures return the same error envelope shape. There are no silent failures.

## Running Locally

### Install dependencies
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Required environment variables
```bash
export OPENAI_API_KEY="your_key"
export OPENAI_MODEL="gpt-4o-mini"
export OPENAI_BASE_URL="https://api.openai.com/v1"
```

### Run the API
```bash
python -m uvicorn app.main:app --reload
```

### Run tests
```bash
python -m pytest -q
```

## Testing
The suite includes focused production-behavior tests:

- **Stability tests**: repeated-request consistency and response drift checks
- **Failure injection tests**: model timeout/provider errors, malformed output, boundary failures
- **Parser robustness tests**: markdown-wrapped JSON, noisy output, malformed fragments, schema mismatch cases

## Design Principles
- Do not trust model output
- Enforce strict contracts over permissive parsing
- Fail fast on invalid input
- Keep failure modes typed and explicit
- Prioritize observability and stage-level attribution

## Scope

This service is intentionally narrow:

- Single-document extraction (invoice only)
- Synchronous request/response model
- No OCR or document ingestion pipeline
- No retrieval-augmented generation (RAG)
- No multi-step workflows or agents

This system is a **bounded, reliable extraction service**, not a full document processing platform.
