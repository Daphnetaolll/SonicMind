from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from backend.config.plans import get_plan
from src.db import connect_db
from src.repositories import user_repository


PLAN_CODE = "creator"
PERIOD_LENGTH_DAYS = 30


# SubscriptionStatus is the normalized plan view used by both quota logic and Streamlit UI.
@dataclass
class SubscriptionStatus:
    subscribed: bool
    status: str
    plan_code: str | None
    plan_name: str | None
    current_period_start: object | None
    current_period_end: object | None
    auto_renew: bool
    monthly_quota: int
    remaining: int
    subscription_id: str | None


def _period_window(now: datetime | None = None) -> tuple[datetime, datetime]:
    # Local demo subscriptions use rolling 30-day windows until Stripe provides billing periods.
    start = now or datetime.now(UTC)
    return start, start + timedelta(days=PERIOD_LENGTH_DAYS)


def _empty_status() -> SubscriptionStatus:
    return SubscriptionStatus(
        subscribed=False,
        status="none",
        plan_code=None,
        plan_name=None,
        current_period_start=None,
        current_period_end=None,
        auto_renew=False,
        monthly_quota=0,
        remaining=0,
        subscription_id=None,
    )


def get_subscription_status(user_id: str) -> SubscriptionStatus:
    # Legacy Streamlit screens read the new user-plan fields rather than the old monthly-100 demo table.
    from src.services.quota_service import get_quota_status

    with connect_db() as conn:
        row = user_repository.get_user_by_id(conn, user_id)
    if not row:
        return _empty_status()

    plan = get_plan(row.get("plan"))
    if plan.code == "free":
        return _empty_status()

    quota = get_quota_status(user_id)
    return SubscriptionStatus(
        subscribed=row.get("subscription_status") in {"trial", "active"},
        status=row.get("subscription_status") or "none",
        plan_code=plan.code,
        plan_name=plan.name,
        current_period_start=quota.period_start,
        current_period_end=quota.period_end,
        auto_renew=True,
        monthly_quota=plan.monthly_limit or 0,
        remaining=quota.remaining_monthly_questions or 0,
        subscription_id=None,
    )


def activate_monthly_subscription(user_id: str) -> SubscriptionStatus:
    # The old demo upgrade button now maps to the Creator plan without creating real billing records.
    plan = get_plan(PLAN_CODE)
    period_start, period_end = _period_window()
    with connect_db() as conn:
        user_repository.update_user_plan(
            conn,
            user_id=user_id,
            plan=plan.code,
            subscription_status="active",
            billing_period_start=period_start,
            billing_period_end=period_end,
        )
        conn.commit()

    return get_subscription_status(user_id)
