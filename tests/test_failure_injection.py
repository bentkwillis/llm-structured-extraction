from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def _base_payload(text: str, request_id: str = "fi-001") -> dict:
    return {
        "request_id": request_id,
        "document_type": "invoice",
        "text": text,
    }


def test_invalid_json_from_model_returns_controlled_error(monkeypatch) -> None:
    def fake_model_output(*args, **kwargs) -> str:
        return "not-json-at-all"

    monkeypatch.setattr("app.main.extract_invoice_json", fake_model_output)

    resp = client.post(
        "/v1/extract/invoice",
        json=_base_payload("Invoice text with enough length for validation."),
    )

    body = resp.json()
    assert resp.status_code == 400
    assert body["success"] is False
    assert body["error"]["failure_point"] == "parsing"


def test_markdown_wrapped_output_is_accepted(monkeypatch) -> None:
    def fake_model_output(*args, **kwargs) -> str:
        return """```json
{
  "supplier_name": "ACME",
  "invoice_number": "INV-100",
  "invoice_date": "2026-04-11",
  "due_date": "2026-05-11",
  "currency": "USD",
  "subtotal": 100.0,
  "tax": 10.0,
  "total": 110.0
}
```"""

    monkeypatch.setattr("app.main.extract_invoice_json", fake_model_output)

    resp = client.post(
        "/v1/extract/invoice",
        json=_base_payload("Invoice text that should parse from markdown fences."),
    )

    body = resp.json()
    assert resp.status_code == 200
    assert body["success"] is True
    assert body["data"]["invoice_number"] == "INV-100"


def test_model_timeout_returns_controlled_error(monkeypatch) -> None:
    def fake_model_output(*args, **kwargs) -> str:
        raise ValueError(
            '{"code":"MODEL_TIMEOUT","message":"model request timed out","failure_point":"model"}'
        )

    monkeypatch.setattr("app.main.extract_invoice_json", fake_model_output)

    resp = client.post(
        "/v1/extract/invoice",
        json=_base_payload("Invoice text with enough length for timeout path."),
    )

    body = resp.json()
    assert resp.status_code == 400
    assert body["success"] is False
    assert body["error"]["code"] == "MODEL_TIMEOUT"
    assert body["error"]["failure_point"] == "model"


def test_garbage_input_fails_boundary_validation() -> None:
    resp = client.post(
        "/v1/extract/invoice",
        json=_base_payload("hi", request_id="fi-004"),
    )

    body = resp.json()
    assert resp.status_code == 400
    assert body["success"] is False
    assert body["error"]["failure_point"] == "validation"


def test_null_heavy_output_succeeds(monkeypatch) -> None:
    def fake_model_output(*args, **kwargs) -> str:
        return """{
          "supplier_name": null,
          "invoice_number": null,
          "invoice_date": null,
          "due_date": null,
          "currency": null,
          "subtotal": null,
          "tax": null,
          "total": null
        }"""

    monkeypatch.setattr("app.main.extract_invoice_json", fake_model_output)

    resp = client.post(
        "/v1/extract/invoice",
        json=_base_payload("Invoice text where fields are missing."),
    )

    body = resp.json()
    assert resp.status_code == 200
    assert body["success"] is True
    assert body["warnings"] == []


def test_inconsistent_totals_returns_warning_not_crash(monkeypatch) -> None:
    def fake_model_output(*args, **kwargs) -> str:
        return """{
          "supplier_name": "ACME",
          "invoice_number": "INV-101",
          "invoice_date": "2026-04-11",
          "due_date": "2026-05-11",
          "currency": "USD",
          "subtotal": 100.0,
          "tax": 10.0,
          "total": 109.99
        }"""

    monkeypatch.setattr("app.main.extract_invoice_json", fake_model_output)

    resp = client.post(
        "/v1/extract/invoice",
        json=_base_payload("Invoice text with inconsistent math totals."),
    )

    body = resp.json()
    assert resp.status_code == 200
    assert body["success"] is True
    assert any("totals do not match" in w for w in body["warnings"])