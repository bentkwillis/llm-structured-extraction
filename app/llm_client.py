from __future__ import annotations

import json
import os
import time

import httpx

from app.schemas import ApiError


def _model_error(code: str, message: str) -> ValueError:
    return ValueError(
        ApiError(
            code=code,
            message=message,
            failure_point="model",
        ).model_dump_json()
    )


def _log_model_call(
    request_id: str | None,
    latency_ms: int,
    model: str,
    token_usage: dict | None,
    failure_point: str | None,
    retry_count: int = 0,
) -> None:
    print(
        json.dumps(
            {
                "request_id": request_id,
                "latency_ms": latency_ms,
                "model": model,
                "input_tokens": token_usage.get("prompt_tokens") if token_usage else None,
                "output_tokens": token_usage.get("completion_tokens") if token_usage else None,
                "total_tokens": token_usage.get("total_tokens") if token_usage else None,
                "failure_point": failure_point,
                "retry_count": retry_count,
            }
        )
    )


def extract_invoice_json(
    prompt: str,
    request_id: str | None = None,
    timeout_seconds: float = 8.0,
    max_retries: int = 1,
) -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

    if not api_key:
        raise _model_error("MODEL_PROVIDER_ERROR", "OPENAI_API_KEY is not set")

    url = f"{base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "temperature": 0,
        "max_tokens": 300,
        "messages": [
            {
                "role": "system",
                "content": "Extract invoice fields. Return only raw JSON text.",
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
    }

    started = time.perf_counter()
    deadline = started + timeout_seconds
    attempt = 0

    try:
        with httpx.Client() as client:
            while attempt <= max_retries:
                remaining = deadline - time.perf_counter()
                if remaining <= 0:
                    latency_ms = int((time.perf_counter() - started) * 1000)
                    _log_model_call(request_id, latency_ms, model, None, "model", attempt)
                    raise _model_error("MODEL_TIMEOUT", "model request timed out after retries")

                try:
                    response = client.post(url, headers=headers, json=payload, timeout=remaining)
                    response.raise_for_status()

                    data = response.json()
                    content = data["choices"][0]["message"]["content"]

                    if not isinstance(content, str) or not content.strip():
                        latency_ms = int((time.perf_counter() - started) * 1000)
                        _log_model_call(request_id, latency_ms, model, data.get("usage"), "model", attempt)
                        raise _model_error("MODEL_PROVIDER_ERROR", "model returned empty content")

                    latency_ms = int((time.perf_counter() - started) * 1000)
                    _log_model_call(request_id, latency_ms, model, data.get("usage"), None, attempt)
                    return content

                except httpx.TimeoutException:
                    if attempt < max_retries and (deadline - time.perf_counter()) > 0:
                        attempt += 1
                        continue
                    latency_ms = int((time.perf_counter() - started) * 1000)
                    _log_model_call(request_id, latency_ms, model, None, "model", attempt)
                    raise _model_error("MODEL_TIMEOUT", "model request timed out after retries") from None

                except httpx.HTTPStatusError as exc:
                    status = exc.response.status_code
                    is_transient = status == 429 or status >= 500
                    if is_transient and attempt < max_retries:
                        attempt += 1
                        continue
                    latency_ms = int((time.perf_counter() - started) * 1000)
                    _log_model_call(request_id, latency_ms, model, None, "model", attempt)
                    raise _model_error(
                        "MODEL_PROVIDER_ERROR",
                        f"model provider returned HTTP {status}",
                    ) from exc

                except httpx.RequestError as exc:
                    if attempt < max_retries:
                        attempt += 1
                        continue
                    latency_ms = int((time.perf_counter() - started) * 1000)
                    _log_model_call(request_id, latency_ms, model, None, "model", attempt)
                    raise _model_error("MODEL_PROVIDER_ERROR", "model provider request failed") from exc

    except httpx.TimeoutException:
        latency_ms = int((time.perf_counter() - started) * 1000)
        _log_model_call(request_id, latency_ms, model, None, "model", attempt)
        raise _model_error("MODEL_TIMEOUT", "model request timed out") from None

    except (KeyError, json.JSONDecodeError) as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        _log_model_call(request_id, latency_ms, model, None, "model", attempt)
        raise _model_error("MODEL_PROVIDER_ERROR", "model response format was unexpected") from exc