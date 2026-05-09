from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.services import billing_service
from src.services.auth_service import AuthUser


class FakeConn:
    # Minimal context manager for service tests that mock repository functions.
    def __init__(self) -> None:
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def commit(self) -> None:
        self.committed = True


def _stripe_checkout_fake(captured: dict):
    class FakeCheckoutSession:
        @staticmethod
        def create(**kwargs):
            captured.update(kwargs)
            return {"url": "https://checkout.stripe.test/session"}

    return SimpleNamespace(
        api_key=None,
        checkout=SimpleNamespace(Session=FakeCheckoutSession),
    )


def test_create_checkout_session_uses_env_price_id(monkeypatch) -> None:
    # Checkout uses only backend env price ids and does not grant plan access locally.
    captured: dict = {}
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_placeholder")
    monkeypatch.setenv("STRIPE_CREATOR_PRICE_ID", "price_creator_test")
    monkeypatch.setenv("STRIPE_PRO_PRICE_ID", "price_pro_test")
    monkeypatch.setenv("FRONTEND_BASE_URL", "https://sonicmind.example")
    monkeypatch.setattr(billing_service, "_stripe_module", lambda: _stripe_checkout_fake(captured))
    monkeypatch.setattr(billing_service, "connect_db", lambda: FakeConn())
    monkeypatch.setattr(
        billing_service.subscription_repository,
        "get_latest_provider_customer_id",
        lambda conn, user_id, provider: None,
    )

    result = billing_service.create_checkout_session(
        user=AuthUser(id="user-1", email="daphne@example.com", display_name=None),
        plan_code="creator",
    )

    assert result.url == "https://checkout.stripe.test/session"
    assert captured["line_items"] == [{"price": "price_creator_test", "quantity": 1}]
    assert captured["client_reference_id"] == "user-1"
    assert captured["success_url"].startswith("https://sonicmind.example/pricing?checkout=success")


def test_create_checkout_session_rejects_product_id_env(monkeypatch) -> None:
    # Stripe Checkout requires price_ ids; prod_ ids are products and should fail before provider calls.
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_placeholder")
    monkeypatch.setenv("STRIPE_CREATOR_PRICE_ID", "prod_wrong_value")

    with pytest.raises(billing_service.BillingConfigurationError):
        billing_service.create_checkout_session(
            user=AuthUser(id="user-1", email="daphne@example.com", display_name=None),
            plan_code="creator",
        )


def test_process_stripe_event_skips_duplicate_provider_event(monkeypatch) -> None:
    # billing_events.provider_event_id is the idempotency key for Stripe webhook retries.
    fake_conn = FakeConn()
    monkeypatch.setattr(billing_service, "_configured_stripe", lambda: SimpleNamespace())
    monkeypatch.setattr(billing_service, "connect_db", lambda: fake_conn)
    monkeypatch.setattr(
        billing_service.billing_repository,
        "insert_billing_event",
        lambda *args, **kwargs: None,
    )

    result = billing_service.process_stripe_event(
        {"id": "evt_duplicate", "type": "customer.subscription.updated", "data": {"object": {}}}
    )

    assert result.duplicate is True
    assert result.processed is False
    assert fake_conn.committed is True


def test_process_subscription_updated_upserts_subscription_and_user(monkeypatch) -> None:
    # A verified subscription webhook writes provider ids and then updates the denormalized user plan.
    fake_conn = FakeConn()
    captured_subscription: dict = {}
    captured_user: dict = {}
    captured_event: dict = {}
    monkeypatch.setenv("STRIPE_CREATOR_PRICE_ID", "price_creator_test")
    monkeypatch.setenv("STRIPE_PRO_PRICE_ID", "price_pro_test")
    monkeypatch.setattr(billing_service, "_configured_stripe", lambda: SimpleNamespace())
    monkeypatch.setattr(billing_service, "connect_db", lambda: fake_conn)
    monkeypatch.setattr(
        billing_service.billing_repository,
        "insert_billing_event",
        lambda *args, **kwargs: {"id": "billing-event-1"},
    )
    monkeypatch.setattr(
        billing_service.billing_repository,
        "mark_billing_event_processed",
        lambda conn, **kwargs: captured_event.update(kwargs),
    )
    monkeypatch.setattr(
        billing_service.subscription_repository,
        "get_provider_subscription",
        lambda conn, provider, provider_subscription_id: None,
    )

    def fake_upsert(conn, **kwargs):
        captured_subscription.update(kwargs)
        return {"id": "local-sub-1"}

    monkeypatch.setattr(billing_service.subscription_repository, "upsert_provider_subscription", fake_upsert)
    monkeypatch.setattr(
        billing_service.user_repository,
        "update_user_plan",
        lambda conn, **kwargs: captured_user.update(kwargs),
    )

    result = billing_service.process_stripe_event(
        {
            "id": "evt_subscription_updated",
            "type": "customer.subscription.updated",
            "data": {
                "object": {
                    "id": "sub_test_123",
                    "status": "active",
                    "customer": "cus_test_123",
                    "metadata": {"user_id": "user-1"},
                    "current_period_start": 1_700_000_000,
                    "current_period_end": 4_100_000_000,
                    "items": {"data": [{"price": {"id": "price_creator_test"}}]},
                }
            },
        }
    )

    assert result.processed is True
    assert captured_subscription["provider_subscription_id"] == "sub_test_123"
    assert captured_subscription["provider_customer_id"] == "cus_test_123"
    assert captured_subscription["plan_code"] == "creator"
    assert captured_user["user_id"] == "user-1"
    assert captured_user["plan"] == "creator"
    assert captured_event["subscription_id"] == "local-sub-1"
