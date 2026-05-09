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
                provider_price_id,
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
                provider_price_id,
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


def get_latest_provider_customer_id(conn: Any, *, user_id: str, provider: str) -> str | None:
    # Reuse the same Stripe customer across repeat checkouts whenever we already know it.
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT provider_customer_id
            FROM subscriptions
            WHERE user_id = %s
              AND provider = %s
              AND provider_customer_id IS NOT NULL
            ORDER BY updated_at DESC, created_at DESC
            LIMIT 1
            """,
            (user_id, provider),
        )
        row = cur.fetchone()
    return str(row["provider_customer_id"]) if row else None


def get_provider_subscription(
    conn: Any,
    *,
    provider: str,
    provider_subscription_id: str,
) -> dict[str, Any] | None:
    # Webhooks use provider ids as the durable lookup key because Stripe may retry events.
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
                provider_price_id,
                created_at,
                updated_at
            FROM subscriptions
            WHERE provider = %s
              AND provider_subscription_id = %s
            LIMIT 1
            """,
            (provider, provider_subscription_id),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def get_current_provider_subscription(conn: Any, *, user_id: str, provider: str) -> dict[str, Any] | None:
    # Quota checks need the current provider-backed subscription, not just denormalized user fields.
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
                provider_price_id,
                created_at,
                updated_at
            FROM subscriptions
            WHERE user_id = %s
              AND provider = %s
              AND status IN ('trial', 'active')
              AND (current_period_end IS NULL OR current_period_end >= NOW())
            ORDER BY current_period_end DESC NULLS LAST, updated_at DESC
            LIMIT 1
            """,
            (user_id, provider),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def upsert_provider_subscription(
    conn: Any,
    *,
    subscription_id: str,
    user_id: str,
    status: str,
    plan_code: str,
    current_period_start: object | None,
    current_period_end: object | None,
    auto_renew: bool,
    monthly_quota: int,
    provider: str,
    provider_customer_id: str | None,
    provider_subscription_id: str,
    provider_price_id: str | None,
) -> dict[str, Any]:
    # Provider subscription ids are unique, so webhook retries update the same local row.
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
                provider,
                provider_customer_id,
                provider_subscription_id,
                provider_price_id
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (provider, provider_subscription_id)
            WHERE provider_subscription_id IS NOT NULL
            DO UPDATE SET
                user_id = EXCLUDED.user_id,
                status = EXCLUDED.status,
                plan_code = EXCLUDED.plan_code,
                current_period_start = EXCLUDED.current_period_start,
                current_period_end = EXCLUDED.current_period_end,
                auto_renew = EXCLUDED.auto_renew,
                monthly_quota = EXCLUDED.monthly_quota,
                provider_customer_id = EXCLUDED.provider_customer_id,
                provider_price_id = EXCLUDED.provider_price_id,
                updated_at = NOW()
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
                provider_customer_id,
                provider_subscription_id,
                provider_price_id,
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
