from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from src.db import connect_db
from src.repositories import subscription_repository, usage_repository


PLAN_CODE = "monthly-100"
PLAN_NAME = "Monthly 100 Questions"
MONTHLY_QUOTA = 100
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
    # Demo subscriptions use rolling 30-day windows rather than a payment-provider billing cycle.
    start = now or datetime.now(UTC)
    return start, start + timedelta(days=PERIOD_LENGTH_DAYS)


def _build_status(subscription: dict | None, remaining: int = 0) -> SubscriptionStatus:
    # Convert raw repository rows into a stable dataclass so UI code does not depend on SQL shape.
    if not subscription:
        return SubscriptionStatus(
            subscribed=False,
            status="none",
            plan_code=None,
            plan_name=None,
            current_period_start=None,
            current_period_end=None,
            auto_renew=False,
            monthly_quota=0,
            remaining=remaining,
            subscription_id=None,
        )

    return SubscriptionStatus(
        subscribed=subscription["status"] == "active",
        status=subscription["status"],
        plan_code=subscription["plan_code"],
        plan_name=PLAN_NAME if subscription["plan_code"] == PLAN_CODE else subscription["plan_code"],
        current_period_start=subscription["current_period_start"],
        current_period_end=subscription["current_period_end"],
        auto_renew=bool(subscription["auto_renew"]),
        monthly_quota=int(subscription["monthly_quota"]),
        remaining=remaining,
        subscription_id=subscription["id"],
    )


def get_subscription_status(user_id: str) -> SubscriptionStatus:
    # Lazily renew active local-demo subscriptions and grant the next monthly question balance.
    with connect_db() as conn:
        latest = subscription_repository.get_latest_subscription(conn, user_id)
        if not latest:
            return _build_status(None)

        current = latest
        now = datetime.now(UTC)
        period_end = current["current_period_end"]
        if (
            current["status"] == "active"
            and current["auto_renew"]
            and period_end is not None
            and period_end < now
        ):
            period_start, next_period_end = _period_window(now)
            current = subscription_repository.update_subscription_period(
                conn,
                subscription_id=current["id"],
                status="active",
                current_period_start=period_start,
                current_period_end=next_period_end,
                auto_renew=True,
            )
            usage_repository.insert_usage_event(
                conn,
                entry_id=str(uuid4()),
                user_id=user_id,
                subscription_id=current["id"],
                question_log_id=None,
                event_type="subscription_grant",
                delta=int(current["monthly_quota"]),
                source="subscription_service.auto_renew",
                period_start=period_start,
                period_end=next_period_end,
                notes="Automatic monthly renewal grant.",
            )
            conn.commit()

        if current["status"] == "active":
            remaining = usage_repository.get_subscription_balance(
                conn,
                user_id=user_id,
                subscription_id=current["id"],
                period_start=current["current_period_start"],
                period_end=current["current_period_end"],
            )
        else:
            remaining = 0

    return _build_status(current, remaining=remaining)


def activate_monthly_subscription(user_id: str) -> SubscriptionStatus:
    # Activate the local demo plan and grant its first monthly quota without touching real payments.
    with connect_db() as conn:
        active = subscription_repository.get_active_subscription(conn, user_id)
        if active:
            remaining = usage_repository.get_subscription_balance(
                conn,
                user_id=user_id,
                subscription_id=active["id"],
                period_start=active["current_period_start"],
                period_end=active["current_period_end"],
            )
            return _build_status(active, remaining=remaining)

        period_start, period_end = _period_window()
        subscription = subscription_repository.create_subscription(
            conn,
            subscription_id=str(uuid4()),
            user_id=user_id,
            status="active",
            plan_code=PLAN_CODE,
            current_period_start=period_start,
            current_period_end=period_end,
            auto_renew=True,
            monthly_quota=MONTHLY_QUOTA,
            provider="local_demo",
        )
        usage_repository.insert_usage_event(
            conn,
            entry_id=str(uuid4()),
            user_id=user_id,
            subscription_id=subscription["id"],
            question_log_id=None,
            event_type="subscription_grant",
            delta=MONTHLY_QUOTA,
            source="subscription_service.activate_monthly_subscription",
            period_start=period_start,
            period_end=period_end,
            notes="Initial subscription grant.",
        )
        conn.commit()

    return get_subscription_status(user_id)
