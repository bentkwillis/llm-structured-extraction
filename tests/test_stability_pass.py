from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def _payload(request_id: str) -> dict:
    return {
        "request_id": request_id,
        "document_type": "invoice",
        "text": (
            "NORTHSHORE INDUSTRIAL PARTS, INC.\n"
            "Invoice No: NS-78431-A\n"
            "Issue Date: 2026-04-11\n"
            "Due: 2026-05-11\n"
            "Currency: USD\n"
            "Subtotal: 1054.00\n"
            "Tax: 86.96\n"
            "Amount Due: 1140.96\n"
        ),
    }


def _assert_success_envelope_shape(body: dict) -> None:
    assert set(body.keys()) == {"success", "request_id", "data", "warnings"}
    assert body["success"] is True
    assert isinstance(body["request_id"], str)
    assert isinstance(body["warnings"], list)

    data = body["data"]
    assert set(data.keys()) == {
        "supplier_name",
        "invoice_number",
        "invoice_date",
        "due_date",
        "currency",
        "subtotal",
        "tax",
        "total",
    }


def test_repeated_requests_are_stable(monkeypatch) -> None:
    # Make model output deterministic so we can detect drift in our own system behavior.
    fixed_model_output = """{
      "supplier_name": "NORTHSHORE INDUSTRIAL PARTS, INC.",
      "invoice_number": "NS-78431-A",
      "invoice_date": "2026-04-11",
      "due_date": "2026-05-11",
      "currency": "USD",
      "subtotal": 1054.0,
      "tax": 86.96,
      "total": 1140.96
    }"""

    def fake_model_output(*args, **kwargs) -> str:
        return fixed_model_output

    monkeypatch.setattr("app.main.extract_invoice_json", fake_model_output)

    first_body: dict | None = None
    for i in range(25):
        resp = client.post("/v1/extract/invoice", json=_payload(f"stability-{i:03d}"))
        assert resp.status_code == 200
        body = resp.json()

        _assert_success_envelope_shape(body)

        # Ignore request_id for equality checks because it is intentionally unique.
        comparable = {k: v for k, v in body.items() if k != "request_id"}

        if first_body is None:
            first_body = comparable
        else:
            assert comparable == first_body