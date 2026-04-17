from __future__ import annotations

from dataclasses import dataclass
import json

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@dataclass
class ModelError(ValueError):
    code: str
    message: str
    failure_point: str

    def __str__(self) -> str:
        return self.message


def _payload(request_id: str = "pm-001") -> dict:
    return {
        "request_id": request_id,
        "document_type": "invoice",
        "text": "Invoice text long enough for validation and prompt building.",
    }


def _assert_standard_error_envelope(body: dict) -> None:
    assert set(body.keys()) == {"success", "request_id", "error"}
    assert body["success"] is False
    assert isinstance(body["request_id"], str) or body["request_id"] is None
    assert set(body["error"].keys()) == {"code", "message", "failure_point"}


def test_parser_accepts_json_with_trailing_text(monkeypatch) -> None:
    def fake_model_output(*args, **kwargs) -> str:
        return (
            "{"
            '"supplier_name":"ACME",'
            '"invoice_number":"INV-200",'
            '"invoice_date":"2026-04-11",'
            '"due_date":"2026-05-11",'
            '"currency":"USD",'
            '"subtotal":100.0,'
            '"tax":10.0,'
            '"total":110.0'
            "} trailing explanation that should be ignored"
        )

    monkeypatch.setattr("app.main.extract_invoice_json", fake_model_output)

    resp = client.post("/v1/extract/invoice", json=_payload("pm-trailing-001"))
    body = resp.json()

    assert resp.status_code == 200
    assert body["success"] is True
    assert body["request_id"] == "pm-trailing-001"
    assert body["data"]["invoice_number"] == "INV-200"


def test_parser_accepts_leading_noise_before_json(monkeypatch) -> None:
    request_id = "pm-leading-001"

    def fake_model_output(*args, **kwargs) -> str:
        return (
            "Some explanation before "
            '{"supplier_name":"ACME","invoice_number":"INV-300","invoice_date":"2026-04-11",'
            '"due_date":"2026-05-11","currency":"USD","subtotal":100.0,"tax":10.0,"total":110.0}'
        )

    monkeypatch.setattr("app.main.extract_invoice_json", fake_model_output)

    resp = client.post("/v1/extract/invoice", json=_payload(request_id))
    body = resp.json()

    assert resp.status_code == 200
    assert body["success"] is True
    assert body["request_id"] == request_id
    assert body["data"]["invoice_number"] == "INV-300"


def test_parser_handles_braces_inside_string_values(monkeypatch) -> None:
    request_id = "pm-braces-001"

    def fake_model_output(*args, **kwargs) -> str:
        return (
            '{"supplier_name":"ACME {North}","invoice_number":"INV-301","invoice_date":"2026-04-11",'
            '"due_date":"2026-05-11","currency":"USD","subtotal":100.0,"tax":10.0,"total":110.0}'
            " trailing"
        )

    monkeypatch.setattr("app.main.extract_invoice_json", fake_model_output)

    resp = client.post("/v1/extract/invoice", json=_payload(request_id))
    body = resp.json()

    assert resp.status_code == 200
    assert body["success"] is True
    assert body["request_id"] == request_id
    assert body["data"]["supplier_name"] == "ACME {North}"


def test_parser_selects_valid_invoice_object_with_multiple_json_objects(monkeypatch) -> None:
    request_id = "pm-multi-001"

    def fake_model_output(*args, **kwargs) -> str:
        return (
            '{} irrelevant {} '
            '{"supplier_name":"ACME","invoice_number":"INV-302","invoice_date":"2026-04-11",'
            '"due_date":"2026-05-11","currency":"USD","subtotal":100.0,"tax":10.0,"total":110.0}'
        )

    monkeypatch.setattr("app.main.extract_invoice_json", fake_model_output)

    resp = client.post("/v1/extract/invoice", json=_payload(request_id))
    body = resp.json()

    assert resp.status_code == 200
    assert body["success"] is True
    assert body["request_id"] == request_id
    assert body["data"]["invoice_number"] == "INV-302"


def test_parser_rejects_partial_json(monkeypatch) -> None:
    def fake_model_output(*args, **kwargs) -> str:
        return '{"supplier_name":"ACME","invoice_number":"INV-201"'

    monkeypatch.setattr("app.main.extract_invoice_json", fake_model_output)

    resp = client.post("/v1/extract/invoice", json=_payload("pm-partial-001"))
    body = resp.json()

    assert resp.status_code == 400
    _assert_standard_error_envelope(body)
    assert body["error"]["failure_point"] == "parsing"
    assert body["error"]["code"] in {"NON_JSON_OUTPUT", "INVALID_MODEL_OUTPUT"}


def test_parser_rejects_unexpected_extra_fields(monkeypatch) -> None:
    def fake_model_output(*args, **kwargs) -> str:
        return json.dumps(
            {
                "supplier_name": "ACME",
                "invoice_number": "INV-202",
                "invoice_date": "2026-04-11",
                "due_date": "2026-05-11",
                "currency": "USD",
                "subtotal": 100.0,
                "tax": 10.0,
                "total": 110.0,
                "extra_field": "should-not-exist",
            }
        )

    monkeypatch.setattr("app.main.extract_invoice_json", fake_model_output)

    resp = client.post("/v1/extract/invoice", json=_payload("pm-extra-001"))
    body = resp.json()

    assert resp.status_code == 400
    _assert_standard_error_envelope(body)
    assert body["error"]["failure_point"] == "parsing"
    assert body["error"]["code"] in {"SCHEMA_MISMATCH", "INVALID_MODEL_OUTPUT"}


def test_model_provider_error_returns_standard_envelope(monkeypatch) -> None:
    def fake_model_output(*args, **kwargs) -> str:
        raise ValueError(
            '{"code":"MODEL_PROVIDER_ERROR","message":"upstream HTTP 502","failure_point":"model"}'
        )

    monkeypatch.setattr("app.main.extract_invoice_json", fake_model_output)

    resp = client.post("/v1/extract/invoice", json=_payload("pm-provider-001"))
    body = resp.json()

    assert resp.status_code == 400
    _assert_standard_error_envelope(body)
    assert body["error"]["code"] == "MODEL_PROVIDER_ERROR"
    assert body["error"]["failure_point"] == "model"


def test_model_empty_response_returns_controlled_error(monkeypatch) -> None:
    def fake_model_output(*args, **kwargs) -> str:
        raise ValueError(
            '{"code":"MODEL_PROVIDER_ERROR","message":"model returned empty content","failure_point":"model"}'
        )

    monkeypatch.setattr("app.main.extract_invoice_json", fake_model_output)

    resp = client.post("/v1/extract/invoice", json=_payload("pm-empty-001"))
    body = resp.json()

    assert resp.status_code == 400
    _assert_standard_error_envelope(body)
    assert body["error"]["code"] == "MODEL_PROVIDER_ERROR"
    assert body["error"]["failure_point"] == "model"


def test_model_timeout_error_envelope_shape(monkeypatch) -> None:
    request_id = "pm-timeout-001"

    def fake_model_output(*args, **kwargs) -> str:
        raise ModelError(
            code="MODEL_TIMEOUT",
            message="model request timed out",
            failure_point="model",
        )

    monkeypatch.setattr("app.main.extract_invoice_json", fake_model_output)

    resp = client.post("/v1/extract/invoice", json=_payload(request_id))
    body = resp.json()

    assert resp.status_code == 400
    _assert_standard_error_envelope(body)
    assert body["request_id"] == request_id
    assert body["error"]["code"] == "MODEL_TIMEOUT"
    assert body["error"]["failure_point"] == "model"
