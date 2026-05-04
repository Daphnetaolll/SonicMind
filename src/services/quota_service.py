from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from src.db import connect_db
from src.repositories import usage_repository
from src.services.subscription_service import get_subscription_status


# QuotaStatus is the single UI-facing answer for whether a user can ask another question.
@dataclass
class QuotaStatus:
    allowed: bool
    charge_type: str
    remaining: int
    subscription_id: str | None
    period_start: object | None
    period_end: object | None


def get_quota_status(user_id: str) -> QuotaStatus:
    # Prefer an active subscription balance; otherwise fall back to the free-trial ledger.
    subscription = get_subscription_status(user_id)
    if subscription.subscribed:
        return QuotaStatus(
            allowed=subscription.remaining > 0,
            charge_type="subscription",
            remaining=subscription.remaining,
            subscription_id=subscription.subscription_id,
            period_start=subscription.current_period_start,
            period_end=subscription.current_period_end,
        )

    with connect_db() as conn:
        remaining = usage_repository.get_free_balance(conn, user_id)
        return QuotaStatus(
            allowed=remaining > 0,
            charge_type="free" if remaining > 0 else "none",
            remaining=remaining,
            subscription_id=None,
            period_start=None,
            period_end=None,
        )


def record_successful_question_usage(
    *,
    user_id: str,
    question_log_id: str,
    source: str = "quota_service.record_successful_question_usage",
) -> QuotaStatus:
    # Charge usage only after answer generation succeeds so failed questions do not consume quota.
    status = get_quota_status(user_id)
    if not status.allowed:
        raise ValueError("No remaining quota.")

    event_type = "subscription_usage" if status.charge_type == "subscription" else "free_usage"

    with connect_db() as conn:
        usage_repository.insert_usage_event(
            conn,
            entry_id=str(uuid4()),
            user_id=user_id,
            subscription_id=status.subscription_id,
            question_log_id=question_log_id,
            event_type=event_type,
            delta=-1,
            source=source,
            period_start=status.period_start,
            period_end=status.period_end,
        )
        conn.commit()

    return get_quota_status(user_id)
