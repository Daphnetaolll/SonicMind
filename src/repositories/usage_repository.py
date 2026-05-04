from __future__ import annotations

from typing import Any


def insert_usage_event(
    conn: Any,
    *,
    entry_id: str,
    user_id: str,
    subscription_id: str | None,
    question_log_id: str | None,
    event_type: str,
    delta: int,
    source: str,
    period_start: object | None = None,
    period_end: object | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    # Append-only ledger events make quota balances auditable and easy to recalculate.
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO usage_ledger (
                id,
                user_id,
                subscription_id,
                question_log_id,
                event_type,
                delta,
                source,
                period_start,
                period_end,
                notes
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                entry_id,
                user_id,
                subscription_id,
                question_log_id,
                event_type,
                delta,
                source,
                period_start,
                period_end,
                notes,
            ),
        )
        row = cur.fetchone()
    return dict(row)


def get_free_balance(conn: Any, user_id: str) -> int:
    # Free balance is the sum of grants, usages, adjustments, and refunds outside subscriptions.
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COALESCE(SUM(delta), 0) AS balance
            FROM usage_ledger
            WHERE user_id = %s
              AND event_type IN ('free_grant', 'free_usage', 'manual_adjustment', 'refund_usage')
            """,
            (user_id,),
        )
        row = cur.fetchone()
    return int(row["balance"])


def get_subscription_balance(
    conn: Any,
    *,
    user_id: str,
    subscription_id: str,
    period_start: object | None,
    period_end: object | None,
) -> int:
    # Subscription balance is scoped to the active plan period so renewals do not mix with old usage.
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COALESCE(SUM(delta), 0) AS balance
            FROM usage_ledger
            WHERE user_id = %s
              AND subscription_id = %s
              AND (
                    (%s IS NULL AND %s IS NULL)
                    OR (period_start = %s AND period_end = %s)
                  )
            """,
            (user_id, subscription_id, period_start, period_end, period_start, period_end),
        )
        row = cur.fetchone()
    return int(row["balance"])
