from __future__ import annotations

from typing import Any


def get_latest_subscription(conn: Any, user_id: str) -> dict[str, Any] | None:
    # Read the newest subscription record for status screens and renewal checks.
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                id,
                user_id,
                status,
                plan_code,
                current_period_start,
                current_period_end,
                auto_renew,
                monthly_quota,
                provider,
                provider_customer_id,
                provider_subscription_id,
                created_at,
                updated_at
            FROM subscriptions
            WHERE user_id = %s
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (user_id,),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def get_active_subscription(conn: Any, user_id: str) -> dict[str, Any] | None:
    # Find the current usable plan before creating a duplicate local demo subscription.
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                id,
                user_id,
                status,
                plan_code,
                current_period_start,
                current_period_end,
                auto_renew,
                monthly_quota,
                provider,
                provider_customer_id,
                provider_subscription_id,
                created_at,
                updated_at
            FROM subscriptions
            WHERE user_id = %s
              AND status = 'active'
              AND (current_period_end IS NULL OR current_period_end >= NOW())
            ORDER BY current_period_end DESC NULLS LAST
            LIMIT 1
            """,
            (user_id,),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def create_subscription(
    conn: Any,
    *,
    subscription_id: str,
    user_id: str,
    status: str,
    plan_code: str,
    current_period_start: object,
    current_period_end: object,
    auto_renew: bool,
    monthly_quota: int,
    provider: str,
) -> dict[str, Any]:
    # Insert local-demo subscription records; real provider ids can be added later by billing events.
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO subscriptions (
                id,
                user_id,
                status,
                plan_code,
                current_period_start,
                current_period_end,
                auto_renew,
                monthly_quota,
                provider
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                subscription_id,
                user_id,
                status,
                plan_code,
                current_period_start,
                current_period_end,
                auto_renew,
                monthly_quota,
                provider,
            ),
        )
        row = cur.fetchone()
    return dict(row)


def update_subscription_period(
    conn: Any,
    *,
    subscription_id: str,
    status: str,
    current_period_start: object,
    current_period_end: object,
    auto_renew: bool,
) -> dict[str, Any]:
    # Advance subscription periods during local auto-renewal while preserving the same subscription id.
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE subscriptions
            SET
                status = %s,
                current_period_start = %s,
                current_period_end = %s,
                auto_renew = %s,
                updated_at = NOW()
            WHERE id = %s
            RETURNING *
            """,
            (status, current_period_start, current_period_end, auto_renew, subscription_id),
        )
        row = cur.fetchone()
    return dict(row)
