from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb


def insert_billing_event(
    conn: Any,
    *,
    event_id: str,
    user_id: str | None,
    subscription_id: str | None,
    provider: str,
    event_type: str,
    provider_event_id: str,
    raw_payload: dict[str, Any],
) -> dict[str, Any] | None:
    # Stripe retries the same event id, so this insert is the idempotency gate for webhook processing.
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO billing_events (
                id,
                user_id,
                subscription_id,
                provider,
                event_type,
                provider_event_id,
                raw_payload
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (provider_event_id) DO NOTHING
            RETURNING *
            """,
            (event_id, user_id, subscription_id, provider, event_type, provider_event_id, Jsonb(raw_payload)),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def mark_billing_event_processed(
    conn: Any,
    *,
    provider_event_id: str,
    user_id: str | None,
    subscription_id: str | None,
) -> None:
    # Mark processing only after local subscription/user state has been reconciled in the same transaction.
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE billing_events
            SET
                user_id = %s,
                subscription_id = %s,
                processed_at = NOW()
            WHERE provider_event_id = %s
            """,
            (user_id, subscription_id, provider_event_id),
        )
