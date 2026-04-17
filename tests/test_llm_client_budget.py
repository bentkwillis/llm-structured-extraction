from __future__ import annotations

import json

from app.llm_client import extract_invoice_json
from app.schemas import ApiError


class _NoRequestClient:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def post(self, *args, **kwargs):
        raise AssertionError("post should not be called when timeout budget is exhausted")


class _CapturingClient:
    last_timeout: float | None = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def post(self, *args, **kwargs):
        timeout = kwargs.get("timeout")
        _CapturingClient.last_timeout = timeout

        class _Resp:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "choices": [{"message": {"content": '{"supplier_name": null, "invoice_number": null, "invoice_date": null, "due_date": null, "currency": null, "subtotal": null, "tax": null, "total": null}'}}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                }

        return _Resp()


def test_total_timeout_budget_exhausted_before_request(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr("app.llm_client.httpx.Client", _NoRequestClient)

    try:
        extract_invoice_json(prompt="x", timeout_seconds=0.0)
        assert False, "expected timeout error"
    except ValueError as e:
        parsed = ApiError.model_validate_json(str(e))
        assert parsed.code == "MODEL_TIMEOUT"
        assert parsed.failure_point == "model"


def test_remaining_timeout_is_passed_to_request(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr("app.llm_client.httpx.Client", _CapturingClient)

    content = extract_invoice_json(prompt="invoice text", timeout_seconds=0.5)

    assert isinstance(content, str)
    assert _CapturingClient.last_timeout is not None
    assert _CapturingClient.last_timeout > 0
    assert _CapturingClient.last_timeout <= 0.5
