from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from backend.config.plans import ACTIVE_SUBSCRIPTION_STATUSES, get_plan
from src.db import connect_db
from src.repositories import billing_repository, subscription_repository, user_repository
from src.services.auth_service import AuthUser


PROVIDER = "stripe"
SUPPORTED_CHECKOUT_PLANS = {"creator", "pro"}


class BillingConfigurationError(RuntimeError):
    """Raised when backend-only Stripe configuration is missing or malformed."""


class BillingProviderError(RuntimeError):
    """Raised when Stripe declines or fails a billing operation."""


class BillingValidationError(ValueError):
    """Raised when a browser asks for an unsupported billing action."""


@dataclass(frozen=True)
class BillingUrlResult:
    # BillingUrlResult keeps route models decoupled from Stripe SDK objects.
    url: str


@dataclass(frozen=True)
class BillingWebhookResult:
    # Webhook responses are intentionally small so provider payload details stay in the database only.
    received: bool
    processed: bool
    duplicate: bool
    event_type: str | None = None


def _stripe_module() -> Any:
    # Import Stripe lazily so tests can mock this boundary without requiring real credentials.
    try:
        import stripe  # type: ignore[import-not-found]
    except ImportError as exc:
        raise BillingConfigurationError("Stripe SDK is not installed.") from exc
    return stripe


def _env_value(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    stripped = value.strip()
    return stripped if stripped else None


def _configured_stripe() -> Any:
    # The secret key is read only on the backend and never echoed in errors or responses.
    secret_key = _env_value("STRIPE_SECRET_KEY")
    if not secret_key:
        raise BillingConfigurationError("Stripe billing is not configured.")
    stripe = _stripe_module()
    stripe.api_key = secret_key
    return stripe


def _frontend_base_url() -> str:
    # Success and cancel redirects point back to the React app, not to the API host.
    return (_env_value("FRONTEND_BASE_URL") or "http://localhost:5173").rstrip("/")


def _plan_price_ids() -> dict[str, str | None]:
    return {
        "creator": _env_value("STRIPE_CREATOR_PRICE_ID"),
        "pro": _env_value("STRIPE_PRO_PRICE_ID"),
    }


def _price_id_for_plan(plan_code: str) -> str:
    # Only server-side env vars map SonicMind plans to Stripe prices.
    if plan_code not in SUPPORTED_CHECKOUT_PLANS:
        raise BillingValidationError("Only Creator and Pro subscriptions are available.")
    price_id = _plan_price_ids().get(plan_code)
    if not price_id or not price_id.startswith("price_"):
        raise BillingConfigurationError("Stripe price ids are not configured correctly.")
    return price_id


def _plan_code_for_price(price_id: str | None) -> str | None:
    if not price_id:
        return None
    for plan_code, configured_price_id in _plan_price_ids().items():
        if configured_price_id and configured_price_id == price_id:
            return plan_code
    return None


def _stripe_get(value: Any, key: str, default: Any = None) -> Any:
    # Stripe objects are dict-like but tests use simple objects and dicts interchangeably.
    if isinstance(value, dict):
        return value.get(key, default)
    if hasattr(value, "get"):
        try:
            return value.get(key, default)
        except TypeError:
            pass
    return getattr(value, key, default)


def _stripe_id(value: Any) -> str | None:
    # Stripe sometimes returns ids directly and sometimes nested objects with an id field.
    if not value:
        return None
    if isinstance(value, str):
        return value
    return _stripe_get(value, "id")


def _stripe_to_dict(value: Any) -> dict[str, Any]:
    if hasattr(value, "to_dict_recursive"):
        return dict(value.to_dict_recursive())
    if isinstance(value, dict):
        return dict(value)
    return dict(getattr(value, "__dict__", {}) or {})


def _timestamp_to_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    return datetime.fromtimestamp(int(value), tz=UTC)


def _map_stripe_status(status: str | None) -> str:
    # The local schema keeps only the statuses that affect SonicMind access decisions.
    if status == "trialing":
        return "trial"
    if status == "active":
        return "active"
    if status == "past_due":
        return "past_due"
    if status == "canceled":
        return "canceled"
    if status in {"incomplete_expired", "unpaid"}:
        return "expired"
    return "past_due"


def _extract_subscription_price_id(subscription: Any) -> str | None:
    # SonicMind supports one monthly price per subscription in the first Stripe version.
    items = _stripe_get(subscription, "items", {}) or {}
    data = _stripe_get(items, "data", []) or []
    if not data:
        return None
    price = _stripe_get(data[0], "price", {}) or {}
    return _stripe_id(price)


def create_checkout_session(*, user: AuthUser, plan_code: str) -> BillingUrlResult:
    # Checkout creation starts payment only; webhook reconciliation is the only access grant path.
    plan = get_plan(plan_code)
    price_id = _price_id_for_plan(plan.code)
    stripe = _configured_stripe()
    frontend_url = _frontend_base_url()

    with connect_db() as conn:
        customer_id = subscription_repository.get_latest_provider_customer_id(
            conn,
            user_id=user.id,
            provider=PROVIDER,
        )

    session_params: dict[str, Any] = {
        "mode": "subscription",
        "line_items": [{"price": price_id, "quantity": 1}],
        "success_url": f"{frontend_url}/pricing?checkout=success&plan={plan.code}&session_id={{CHECKOUT_SESSION_ID}}",
        "cancel_url": f"{frontend_url}/pricing?checkout=canceled",
        "client_reference_id": user.id,
        "metadata": {"user_id": user.id, "plan_code": plan.code},
        "subscription_data": {"metadata": {"user_id": user.id, "plan_code": plan.code}},
    }
    if customer_id:
        session_params["customer"] = customer_id
    else:
        session_params["customer_email"] = user.email

    try:
        session = stripe.checkout.Session.create(**session_params)
    except Exception as exc:  # pragma: no cover - exact Stripe exception class varies by SDK version.
        raise BillingProviderError("Stripe checkout is unavailable right now.") from exc

    url = _stripe_get(session, "url")
    if not url:
        raise BillingProviderError("Stripe checkout did not return a redirect URL.")
    return BillingUrlResult(url=str(url))


def create_portal_session(*, user: AuthUser) -> BillingUrlResult:
    # The Stripe-hosted portal owns payment-method updates, invoices, and cancellation controls.
    stripe = _configured_stripe()
    frontend_url = _frontend_base_url()
    with connect_db() as conn:
        customer_id = subscription_repository.get_latest_provider_customer_id(
            conn,
            user_id=user.id,
            provider=PROVIDER,
        )
    if not customer_id:
        raise BillingValidationError("No Stripe customer is linked to this account yet.")

    try:
        session = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=f"{frontend_url}/pricing",
        )
    except Exception as exc:  # pragma: no cover - exact Stripe exception class varies by SDK version.
        raise BillingProviderError("Stripe billing portal is unavailable right now.") from exc

    url = _stripe_get(session, "url")
    if not url:
        raise BillingProviderError("Stripe billing portal did not return a redirect URL.")
    return BillingUrlResult(url=str(url))


def construct_stripe_event(*, payload: bytes, stripe_signature: str | None) -> Any:
    # Stripe requires the exact raw request body and the Stripe-Signature header for verification.
    webhook_secret = _env_value("STRIPE_WEBHOOK_SECRET")
    if not webhook_secret:
        raise BillingConfigurationError("Stripe webhook is not configured.")
    if not stripe_signature:
        raise BillingValidationError("Missing Stripe signature.")
    stripe = _configured_stripe()
    try:
        return stripe.Webhook.construct_event(payload=payload, sig_header=stripe_signature, secret=webhook_secret)
    except Exception as exc:
        raise BillingValidationError("Invalid Stripe webhook signature or payload.") from exc


def _retrieve_subscription(stripe: Any, subscription_id: str | None) -> Any | None:
    if not subscription_id:
        return None
    try:
        return stripe.Subscription.retrieve(subscription_id)
    except Exception as exc:  # pragma: no cover - exact Stripe exception class varies by SDK version.
        raise BillingProviderError("Stripe subscription lookup failed.") from exc


def _sync_subscription(
    conn: Any,
    *,
    subscription: Any,
    fallback_user_id: str | None = None,
) -> tuple[str | None, str | None]:
    provider_subscription_id = _stripe_id(subscription)
    if not provider_subscription_id:
        return None, None

    existing = subscription_repository.get_provider_subscription(
        conn,
        provider=PROVIDER,
        provider_subscription_id=provider_subscription_id,
    )
    metadata = _stripe_get(subscription, "metadata", {}) or {}
    user_id = _stripe_get(metadata, "user_id") or fallback_user_id or (existing or {}).get("user_id")
    price_id = _extract_subscription_price_id(subscription) or (existing or {}).get("provider_price_id")
    plan_code = _plan_code_for_price(price_id) or (existing or {}).get("plan_code")
    if not user_id or not plan_code:
        return user_id, (existing or {}).get("id")

    plan = get_plan(plan_code)
    mapped_status = _map_stripe_status(_stripe_get(subscription, "status"))
    period_start = _timestamp_to_datetime(_stripe_get(subscription, "current_period_start"))
    period_end = _timestamp_to_datetime(_stripe_get(subscription, "current_period_end"))
    customer_id = _stripe_id(_stripe_get(subscription, "customer"))
    cancel_at_period_end = bool(_stripe_get(subscription, "cancel_at_period_end", False))
    local_subscription = subscription_repository.upsert_provider_subscription(
        conn,
        subscription_id=(existing or {}).get("id") or str(uuid4()),
        user_id=user_id,
        status=mapped_status,
        plan_code=plan.code,
        current_period_start=period_start,
        current_period_end=period_end,
        auto_renew=not cancel_at_period_end and mapped_status in ACTIVE_SUBSCRIPTION_STATUSES,
        monthly_quota=plan.monthly_limit or 0,
        provider=PROVIDER,
        provider_customer_id=customer_id,
        provider_subscription_id=provider_subscription_id,
        provider_price_id=price_id,
    )

    has_current_paid_access = (
        mapped_status in ACTIVE_SUBSCRIPTION_STATUSES
        and period_end is not None
        and period_end > datetime.now(UTC)
    )
    if has_current_paid_access:
        user_repository.update_user_plan(
            conn,
            user_id=user_id,
            plan=plan.code,
            subscription_status=mapped_status,
            billing_period_start=period_start,
            billing_period_end=period_end,
        )
    else:
        user_repository.update_user_plan(
            conn,
            user_id=user_id,
            plan="free",
            subscription_status=mapped_status,
            billing_period_start=None,
            billing_period_end=None,
        )

    return user_id, local_subscription["id"]


def _sync_from_checkout_session(conn: Any, *, stripe: Any, session: Any) -> tuple[str | None, str | None]:
    mode = _stripe_get(session, "mode")
    if mode != "subscription":
        return None, None
    subscription_id = _stripe_id(_stripe_get(session, "subscription"))
    metadata = _stripe_get(session, "metadata", {}) or {}
    user_id = _stripe_get(session, "client_reference_id") or _stripe_get(metadata, "user_id")
    subscription = _retrieve_subscription(stripe, subscription_id)
    if not subscription:
        return user_id, None
    return _sync_subscription(conn, subscription=subscription, fallback_user_id=user_id)


def _sync_from_invoice(conn: Any, *, stripe: Any, invoice: Any) -> tuple[str | None, str | None]:
    subscription_id = _stripe_id(_stripe_get(invoice, "subscription"))
    subscription = _retrieve_subscription(stripe, subscription_id)
    if not subscription:
        return None, None
    return _sync_subscription(conn, subscription=subscription)


def process_stripe_event(event: Any) -> BillingWebhookResult:
    # Process the event and billing_events row in one transaction so failed work can be retried by Stripe.
    stripe = _configured_stripe()
    event_id = _stripe_get(event, "id")
    event_type = _stripe_get(event, "type")
    data = _stripe_get(event, "data", {}) or {}
    data_object = _stripe_get(data, "object", {}) or {}
    if not event_id or not event_type:
        raise BillingValidationError("Stripe event is missing required identifiers.")

    with connect_db() as conn:
        inserted = billing_repository.insert_billing_event(
            conn,
            event_id=str(uuid4()),
            user_id=None,
            subscription_id=None,
            provider=PROVIDER,
            event_type=str(event_type),
            provider_event_id=str(event_id),
            raw_payload=_stripe_to_dict(event),
        )
        if inserted is None:
            conn.commit()
            return BillingWebhookResult(received=True, processed=False, duplicate=True, event_type=str(event_type))

        user_id: str | None = None
        local_subscription_id: str | None = None
        if event_type == "checkout.session.completed":
            user_id, local_subscription_id = _sync_from_checkout_session(conn, stripe=stripe, session=data_object)
        elif event_type in {"customer.subscription.created", "customer.subscription.updated", "customer.subscription.deleted"}:
            user_id, local_subscription_id = _sync_subscription(conn, subscription=data_object)
        elif event_type in {"invoice.paid", "invoice.payment_failed"}:
            user_id, local_subscription_id = _sync_from_invoice(conn, stripe=stripe, invoice=data_object)

        billing_repository.mark_billing_event_processed(
            conn,
            provider_event_id=str(event_id),
            user_id=user_id,
            subscription_id=local_subscription_id,
        )
        conn.commit()

    return BillingWebhookResult(received=True, processed=True, duplicate=False, event_type=str(event_type))
