from __future__ import annotations

from fastapi.testclient import TestClient

from backend.main import app
from backend.services.billing_service import BillingUrlResult, BillingWebhookResult
from backend.services.token_service import create_access_token
from src.services.auth_service import AuthUser


client = TestClient(app)


def test_checkout_endpoint_returns_stripe_url_without_granting_access(monkeypatch) -> None:
    # The endpoint starts Stripe Checkout, while actual plan changes remain webhook-only.
    user = AuthUser(id="user-billing-1", email="daphne@example.com", display_name=None)
    captured: dict = {}

    def fake_checkout(**kwargs):
        captured.update(kwargs)
        return BillingUrlResult(url="https://checkout.stripe.test/session")

    monkeypatch.setattr("backend.main.get_user", lambda user_id: user if user_id == user.id else None)
    monkeypatch.setattr("backend.main.create_checkout_session", fake_checkout)

    response = client.post(
        "/api/billing/checkout-session",
        headers={"Authorization": f"Bearer {create_access_token(user_id=user.id)}"},
        json={"plan_code": "creator"},
    )

    assert response.status_code == 200
    assert response.json() == {"url": "https://checkout.stripe.test/session"}
    assert captured["user"] == user
    assert captured["plan_code"] == "creator"


def test_portal_endpoint_returns_stripe_url(monkeypatch) -> None:
    # Billing portal creation is authenticated and delegated to the billing service.
    user = AuthUser(id="user-billing-2", email="pro@example.com", display_name=None, plan="pro")
    monkeypatch.setattr("backend.main.get_user", lambda user_id: user if user_id == user.id else None)
    monkeypatch.setattr(
        "backend.main.create_portal_session",
        lambda user: BillingUrlResult(url="https://billing.stripe.test/session"),
    )

    response = client.post(
        "/api/billing/portal-session",
        headers={"Authorization": f"Bearer {create_access_token(user_id=user.id)}"},
    )

    assert response.status_code == 200
    assert response.json() == {"url": "https://billing.stripe.test/session"}


def test_webhook_endpoint_verifies_raw_body_and_signature(monkeypatch) -> None:
    # Webhooks do not use bearer auth; the route passes raw bytes and Stripe-Signature to verification.
    captured: dict = {}

    def fake_construct(**kwargs):
        captured.update(kwargs)
        return {"id": "evt_test", "type": "checkout.session.completed"}

    monkeypatch.setattr("backend.main.construct_stripe_event", fake_construct)
    monkeypatch.setattr(
        "backend.main.process_stripe_event",
        lambda event: BillingWebhookResult(
            received=True,
            processed=True,
            duplicate=False,
            event_type=event["type"],
        ),
    )

    response = client.post(
        "/api/billing/webhook",
        content=b'{"id":"evt_test"}',
        headers={"stripe-signature": "t=test,v1=signature"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "received": True,
        "processed": True,
        "duplicate": False,
        "event_type": "checkout.session.completed",
    }
    assert captured["payload"] == b'{"id":"evt_test"}'
    assert captured["stripe_signature"] == "t=test,v1=signature"
