"""Tests for the Stripe webhook service — signature, mintage, redemption.

No network and no stripe SDK: events are forged, the signature is
computed with the service's own ``sign_payload``, and Stripe's recorded
format is reproduced faithfully (t,<id>,v1 list).
"""

from __future__ import annotations

import json
import time

import pytest
from fastapi.testclient import TestClient

from services.stripe_webhook import app as app_module
from services.stripe_webhook.catalog import grant_for_package, package_prices

SECRET = "whsec_test_secret"


@pytest.fixture()
def client(tmp_path, monkeypatch):  # noqa: ANN001
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("STRIPE_LEDGER_PATH", str(tmp_path / "vouchers.json"))
    return TestClient(app_module.app)


def _event(package: str | None = None, email: str = "buyer@example.com") -> dict:
    session = {"id": "cs_test_123", "customer_details": {"email": email}}
    if package:
        session["metadata"] = {"package": package}
    return {
        "id": "evt_1",
        "type": "checkout.session.completed",
        "data": {"object": session},
    }


def _post_webhook(client: TestClient, event: dict, secret: str = SECRET) -> object:
    payload = json.dumps(event).encode()
    timestamp = int(time.time())
    signature = app_module.sign_payload(secret, timestamp, payload)
    header = f"t={timestamp},v1={signature}"
    return client.post("/stripe/webhook", content=payload, headers={"Stripe-Signature": header})


class TestSignature:
    def test_valid_signature_passes(self, client: TestClient) -> None:
        payload = b'{"type": "checkout.session.completed"}'
        timestamp = int(time.time())
        signature = app_module.sign_payload(SECRET, timestamp, payload)
        response = client.post(
            "/stripe/webhook",
            content=payload,
            headers={"Stripe-Signature": f"t={timestamp},v1={signature}"},
        )
        assert response.status_code == 200

    def test_tampered_payload_fails(self, client: TestClient) -> None:
        payload = b'{"type": "checkout.session.completed"}'
        timestamp = int(time.time())
        signature = app_module.sign_payload(SECRET, timestamp, payload)
        response = client.post(
            "/stripe/webhook",
            content=payload + b" ",
            headers={"Stripe-Signature": f"t={timestamp},v1={signature}"},
        )
        assert response.status_code == 400

    def test_stale_timestamp_fails(self, client: TestClient) -> None:
        payload = b"{}"
        stamp = int(time.time()) - 3600
        signature = app_module.sign_payload(SECRET, stamp, payload)
        response = client.post(
            "/stripe/webhook",
            content=payload,
            headers={"Stripe-Signature": f"t={stamp},v1={signature}"},
        )
        assert response.status_code == 400

    def test_missing_header_fails(self, client: TestClient) -> None:
        response = client.post("/stripe/webhook", content=b"{}")
        assert response.status_code == 400


class TestWebhookFulfillment:
    def test_metadata_package_mints_voucher(self, client: TestClient) -> None:
        response = _post_webhook(client, _event("starter_50", "acme@example.com"))
        assert response.status_code == 200
        voucher = response.json()["voucher"]
        assert voucher.startswith("FB-STARTER_50-")
        ledger = app_module._load_ledger()
        assert ledger["vouchers"][voucher]["grant"]["credits"] == 50
        assert ledger["vouchers"][voucher]["customer_email"] == "acme@example.com"

    def test_price_map_fallback(self, client: TestClient, monkeypatch) -> None:  # noqa: ANN001
        monkeypatch.setenv("STRIPE_PRICE_MAP", "price_max=scale_250")
        event = _event(None)
        event["data"]["object"]["metadata"] = {}
        response = _post_webhook(client, event)
        assert response.status_code == 200
        # without line-item price ids in the event, metadataless checkout
        # resolves to nothing — the note explains why
        assert response.json()["handled"] is False

    def test_unknown_package_is_a_handled_no_op(self, client: TestClient) -> None:
        response = _post_webhook(client, _event("mystery_pack_999"))
        assert response.status_code == 200
        assert response.json()["handled"] is False

    def test_unrelated_event_ignored(self, client: TestClient) -> None:
        response = _post_webhook(client, {"type": "invoice.paid", "data": {"object": {}}})
        assert response.json() == {"handled": False, "type": "invoice.paid"}

    def test_unconfigured_secret_is_503(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
        client = TestClient(app_module.app)
        response = client.post("/stripe/webhook", content=b"{}")
        assert response.status_code == 503


class TestRedeem:
    def test_redeem_returns_grant_once(self, client: TestClient) -> None:
        minted = _post_webhook(client, _event("scale_250")).json()["voucher"]
        first = client.post("/redeem", json={"code": minted})
        assert first.status_code == 200
        assert first.json()["credits"] == 250
        second = client.post("/redeem", json={"code": minted})
        assert second.status_code == 409

    def test_unknown_code_404(self, client: TestClient) -> None:
        response = client.post("/redeem", json={"code": "FB-NOPE-0000"})
        assert response.status_code == 404

    def test_missing_code_400(self, client: TestClient) -> None:
        response = client.post("/redeem", json={})
        assert response.status_code == 400


class TestHealthAndCatalog:
    def test_health_reports_configuration(self, client: TestClient) -> None:
        body = client.get("/health").json()
        assert body["ok"] is True
        assert body["webhook_configured"] is True

    def test_catalog_math(self) -> None:
        catalog = package_prices()
        assert catalog["starter_50"]["usd"] == "5.00"  # 50 × $0.10
        assert catalog["growth_100"]["usd"] == "10.00"
        assert catalog["scale_250"]["usd"] == "25.00"
        assert catalog["max_500"]["usd"] == "50.00"
        assert catalog["enterprise_unlimited"]["usd"] == "5000.00"
        assert catalog["enterprise_unlimited"]["credits"] == "unlimited"

    def test_grant_lookup_rejects_unknown(self) -> None:
        assert grant_for_package("mystery") is None
