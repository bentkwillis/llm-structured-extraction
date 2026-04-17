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
) -> None:
    print(
        json.dumps(
            {
                "request_id": request_id,
                "latency_ms": latency_ms,
                "model": model,
                "token_usage": token_usage,
                "failure_point": failure_point,
            }
        )
    )


def extract_invoice_json(
    prompt: str,
    request_id: str | None = None,
    timeout_seconds: float = 8.0,
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

    try:
        with httpx.Client(timeout=timeout_seconds) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()

        data = response.json()
        content = data["choices"][0]["message"]["content"]

        if not isinstance(content, str) or not content.strip():
            latency_ms = int((time.perf_counter() - started) * 1000)
            _log_model_call(request_id, latency_ms, model, data.get("usage"), "model")
            raise _model_error("MODEL_PROVIDER_ERROR", "model returned empty content")

        latency_ms = int((time.perf_counter() - started) * 1000)
        _log_model_call(request_id, latency_ms, model, data.get("usage"), None)
        return content

    except httpx.TimeoutException as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        _log_model_call(request_id, latency_ms, model, None, "model")
        raise _model_error("MODEL_TIMEOUT", "model request timed out") from exc

    except httpx.HTTPStatusError as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        _log_model_call(request_id, latency_ms, model, None, "model")
        raise _model_error(
            "MODEL_PROVIDER_ERROR",
            f"model provider returned HTTP {exc.response.status_code}",
        ) from exc

    except httpx.RequestError as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        _log_model_call(request_id, latency_ms, model, None, "model")
        raise _model_error("MODEL_PROVIDER_ERROR", "model provider request failed") from exc

    except (KeyError, ValueError, json.JSONDecodeError) as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        _log_model_call(request_id, latency_ms, model, None, "model")
        raise _model_error("MODEL_PROVIDER_ERROR", "model response format was unexpected") from exc