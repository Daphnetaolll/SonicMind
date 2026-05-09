from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from backend.config.plans import (
    ACTIVE_SUBSCRIPTION_STATUSES,
    DEFAULT_PLAN_CODE,
    PlanConfig,
    get_plan,
)
from src.db import connect_db
from src.repositories import credit_repository, subscription_repository, usage_repository, user_repository


PERIOD_LENGTH_DAYS = 30


# QuotaStatus is the single UI-facing answer for whether a user can ask another question.
@dataclass
class QuotaStatus:
    allowed: bool
    charge_type: str
    remaining: int
    subscription_id: str | None = None
    period_start: object | None = None
    period_end: object | None = None
    current_plan: str = DEFAULT_PLAN_CODE
    current_plan_name: str = "Free"
    price_label: str = "$0/month"
    remaining_daily_questions: int | None = None
    remaining_monthly_questions: int | None = None
    extra_question_credits: int = 0
    limit_message: str | None = None
    max_answer_tokens: int = 400
    rag_top_k: int = 3
    spotify_limit: int = 5
    save_history: bool = False
    favorites: bool = False
    playlist_style: bool = False


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _free_day_window(now: datetime) -> tuple[datetime, datetime]:
    # Free-plan limits reset at midnight UTC, independent of the user's browser timezone.
    start = now.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=1)


def _demo_paid_rollover_enabled() -> bool:
    # Demo rollover is allowed for local seed users, but production access must come from Stripe webhooks.
    app_env = os.getenv("APP_ENV", "development").strip().lower()
    configured = os.getenv("SONICMIND_ENABLE_DEMO_BILLING_ROLLOVER", "true").strip().lower()
    return app_env != "production" and configured in {"1", "true", "yes", "on"}


def _monthly_window(row: dict, plan: PlanConfig, now: datetime) -> tuple[datetime | None, datetime | None, bool]:
    """
    Paid plans use the stored billing window. Local demo users may roll forward only
    outside production; Stripe-backed users rely on webhook-supplied periods.
    """
    start = row.get("billing_period_start")
    end = row.get("billing_period_end")
    if start and end and end > now:
        return start, end, False
    if not _demo_paid_rollover_enabled():
        return start, end, False

    new_start = now
    new_end = now + timedelta(days=PERIOD_LENGTH_DAYS)
    return new_start, new_end, True


def _effective_plan(row: dict) -> PlanConfig:
    # Inactive paid subscriptions fall back to Free until a real billing provider can reconcile them.
    plan = get_plan(row.get("plan"))
    if plan.code != "free" and row.get("subscription_status") not in ACTIVE_SUBSCRIPTION_STATUSES:
        return get_plan("free")
    return plan


def _base_status(
    *,
    plan: PlanConfig,
    allowed: bool,
    charge_type: str,
    remaining: int,
    period_start: object | None,
    period_end: object | None,
    subscription_id: str | None,
    remaining_daily_questions: int | None,
    remaining_monthly_questions: int | None,
    extra_question_credits: int,
) -> QuotaStatus:
    # Keep all plan feature flags attached to every quota response for frontend gating.
    return QuotaStatus(
        allowed=allowed,
        charge_type=charge_type,
        remaining=remaining,
        subscription_id=subscription_id,
        period_start=period_start,
        period_end=period_end,
        current_plan=plan.code,
        current_plan_name=plan.name,
        price_label=plan.price_label,
        remaining_daily_questions=remaining_daily_questions,
        remaining_monthly_questions=remaining_monthly_questions,
        extra_question_credits=extra_question_credits,
        limit_message=None if allowed else plan.limit_message,
        max_answer_tokens=plan.max_answer_tokens,
        rag_top_k=plan.rag_top_k,
        spotify_limit=plan.spotify_limit,
        save_history=plan.save_history,
        favorites=plan.favorites,
        playlist_style=plan.playlist_style,
    )


def _free_quota_status(
    conn: object,
    *,
    user_id: str,
    plan: PlanConfig,
    extra_credits: int,
    now: datetime,
) -> QuotaStatus:
    # Free access is always daily and never depends on provider subscription records.
    period_start, period_end = _free_day_window(now)
    used = usage_repository.count_charged_questions(
        conn,
        user_id=user_id,
        period_start=period_start,
        period_end=period_end,
        charge_types=("free",),
    )
    remaining_daily = max((plan.daily_limit or 0) - used, 0)
    if remaining_daily > 0:
        return _base_status(
            plan=plan,
            allowed=True,
            charge_type="free",
            remaining=remaining_daily,
            period_start=period_start,
            period_end=period_end,
            subscription_id=None,
            remaining_daily_questions=remaining_daily,
            remaining_monthly_questions=None,
            extra_question_credits=extra_credits,
        )
    return _base_status(
        plan=plan,
        allowed=extra_credits > 0,
        charge_type="extra_credit" if extra_credits > 0 else "none",
        remaining=extra_credits,
        period_start=period_start,
        period_end=period_end,
        subscription_id=None,
        remaining_daily_questions=0,
        remaining_monthly_questions=None,
        extra_question_credits=extra_credits,
    )


def get_quota_status(user_id: str) -> QuotaStatus:
    # Evaluate quota from durable backend records; frontend counters are never trusted.
    now = _utc_now()
    with connect_db() as conn:
        row = user_repository.get_user_by_id(conn, user_id)
        if not row:
            return _base_status(
                plan=get_plan("free"),
                allowed=False,
                charge_type="none",
                remaining=0,
                period_start=None,
                period_end=None,
                subscription_id=None,
                remaining_daily_questions=0,
                remaining_monthly_questions=None,
                extra_question_credits=0,
            )

        plan = _effective_plan(row)
        extra_credits = credit_repository.get_active_credit_balance(conn, user_id=user_id, now=now)
        user_repository.update_extra_credit_snapshot(
            conn,
            user_id=user_id,
            extra_question_credits=extra_credits,
        )

        if plan.daily_limit is not None:
            status = _free_quota_status(conn, user_id=user_id, plan=plan, extra_credits=extra_credits, now=now)
            conn.commit()
            return status

        provider_subscription = subscription_repository.get_current_provider_subscription(
            conn,
            user_id=user_id,
            provider="stripe",
        )
        subscription_id = provider_subscription["id"] if provider_subscription else None
        if provider_subscription:
            plan = get_plan(provider_subscription["plan_code"])
            period_start = provider_subscription.get("current_period_start")
            period_end = provider_subscription.get("current_period_end")
        else:
            if not _demo_paid_rollover_enabled():
                free_plan = get_plan("free")
                status = _free_quota_status(conn, user_id=user_id, plan=free_plan, extra_credits=extra_credits, now=now)
                conn.commit()
                return status
            period_start, period_end, needs_period_update = _monthly_window(row, plan, now)
            if needs_period_update:
                user_repository.update_user_plan(
                    conn,
                    user_id=user_id,
                    plan=plan.code,
                    subscription_status=row.get("subscription_status") or "active",
                    billing_period_start=period_start,
                    billing_period_end=period_end,
                )

        if not period_start or not period_end or period_end <= now:
            free_plan = get_plan("free")
            status = _free_quota_status(conn, user_id=user_id, plan=free_plan, extra_credits=extra_credits, now=now)
            conn.commit()
            return status

        if provider_subscription:
            user_repository.update_user_plan(
                conn,
                user_id=user_id,
                plan=provider_subscription["plan_code"],
                subscription_status=provider_subscription["status"],
                billing_period_start=period_start,
                billing_period_end=period_end,
            )

        monthly_limit = plan.monthly_limit or 0
        used = usage_repository.count_charged_questions(
            conn,
            user_id=user_id,
            period_start=period_start,
            period_end=period_end,
            charge_types=("subscription",),
        )
        remaining_monthly = max(monthly_limit - used, 0)
        conn.commit()

    if remaining_monthly > 0:
        return _base_status(
            plan=plan,
            allowed=True,
            charge_type="subscription",
            remaining=remaining_monthly,
            period_start=period_start,
            period_end=period_end,
            subscription_id=subscription_id,
            remaining_daily_questions=None,
            remaining_monthly_questions=remaining_monthly,
            extra_question_credits=extra_credits,
        )

    return _base_status(
        plan=plan,
        allowed=extra_credits > 0,
        charge_type="extra_credit" if extra_credits > 0 else "none",
        remaining=extra_credits,
        period_start=period_start,
        period_end=period_end,
        subscription_id=subscription_id,
        remaining_daily_questions=None,
        remaining_monthly_questions=0,
        extra_question_credits=extra_credits,
    )


def record_successful_question_usage(
    *,
    user_id: str,
    question_log_id: str,
    quota: QuotaStatus | None = None,
    source: str = "quota_service.record_successful_question_usage",
) -> QuotaStatus:
    # Charge usage only after answer generation succeeds so failed questions do not consume quota.
    status = quota or get_quota_status(user_id)
    if not status.allowed:
        raise ValueError("No remaining quota.")

    if status.charge_type == "extra_credit":
        event_type = "extra_credit_usage"
    elif status.charge_type == "subscription":
        event_type = "subscription_usage"
    else:
        event_type = "free_usage"

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
        if status.charge_type == "extra_credit":
            now = _utc_now()
            credit_repository.insert_credit_transaction(
                conn,
                transaction_id=str(uuid4()),
                user_id=user_id,
                credit_amount=-1,
                purchased_at=now,
                expires_at=None,
                source="usage",
                note=f"Question usage for {question_log_id}.",
            )
            balance = credit_repository.get_active_credit_balance(conn, user_id=user_id, now=now)
            user_repository.update_extra_credit_snapshot(
                conn,
                user_id=user_id,
                extra_question_credits=balance,
            )
        conn.commit()

    return get_quota_status(user_id)
