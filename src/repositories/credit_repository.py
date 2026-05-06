from __future__ import annotations

from typing import Any


def insert_credit_transaction(
    conn: Any,
    *,
    transaction_id: str,
    user_id: str,
    credit_amount: int,
    purchased_at: object,
    expires_at: object | None,
    source: str,
    note: str | None = None,
) -> dict[str, Any]:
    # Credit transactions stay append-only so later Stripe webhooks can reconcile balances.
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO credit_transactions (
                id,
                user_id,
                credit_amount,
                purchased_at,
                expires_at,
                source,
                note
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (transaction_id, user_id, credit_amount, purchased_at, expires_at, source, note),
        )
        row = cur.fetchone()
    return dict(row)


def get_active_credit_balance(conn: Any, *, user_id: str, now: object) -> int:
    """
    Count unexpired purchased credits plus all credit-usage rows.
    This MVP keeps FIFO expiration for later billing work while preventing expired packs from adding balance.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COALESCE(SUM(credit_amount), 0) AS balance
            FROM credit_transactions
            WHERE user_id = %s
              AND (
                    credit_amount < 0
                    OR expires_at > %s
                  )
            """,
            (user_id, now),
        )
        row = cur.fetchone()
    return max(int(row["balance"]), 0)
