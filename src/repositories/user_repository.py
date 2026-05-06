from __future__ import annotations

from typing import Any


def create_user(
    conn: Any,
    *,
    user_id: str,
    email: str,
    password_hash: str,
    display_name: str | None = None,
) -> dict[str, Any]:
    # Return only safe user fields after insert; password_hash is intentionally omitted.
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO users (id, email, password_hash, display_name)
            VALUES (%s, %s, %s, %s)
            RETURNING
                id,
                email,
                display_name,
                plan,
                subscription_status,
                billing_period_start,
                billing_period_end,
                extra_question_credits,
                created_at,
                updated_at,
                deleted_at
            """,
            (user_id, email, password_hash, display_name),
        )
        row = cur.fetchone()
    return dict(row)


def get_user_by_email(conn: Any, email: str) -> dict[str, Any] | None:
    # Authentication needs the password hash, so this lookup is service-layer only.
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                id,
                email,
                password_hash,
                display_name,
                plan,
                subscription_status,
                billing_period_start,
                billing_period_end,
                extra_question_credits,
                created_at,
                updated_at,
                deleted_at
            FROM users
            WHERE email = %s
            """,
            (email,),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def get_user_by_id(conn: Any, user_id: str) -> dict[str, Any] | None:
    # Session lookups include deleted_at so auth_service can reject soft-deleted accounts.
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                id,
                email,
                password_hash,
                display_name,
                plan,
                subscription_status,
                billing_period_start,
                billing_period_end,
                extra_question_credits,
                created_at,
                updated_at,
                deleted_at
            FROM users
            WHERE id = %s
            """,
            (user_id,),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def update_user_plan(
    conn: Any,
    *,
    user_id: str,
    plan: str,
    subscription_status: str,
    billing_period_start: object | None,
    billing_period_end: object | None,
) -> dict[str, Any]:
    # Dev-only plan changes update the user record directly until a real billing provider exists.
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE users
            SET
                plan = %s,
                subscription_status = %s,
                billing_period_start = %s,
                billing_period_end = %s,
                updated_at = NOW()
            WHERE id = %s
            RETURNING
                id,
                email,
                display_name,
                plan,
                subscription_status,
                billing_period_start,
                billing_period_end,
                extra_question_credits,
                created_at,
                updated_at,
                deleted_at
            """,
            (plan, subscription_status, billing_period_start, billing_period_end, user_id),
        )
        row = cur.fetchone()
    return dict(row)


def update_extra_credit_snapshot(conn: Any, *, user_id: str, extra_question_credits: int) -> None:
    # Keep a denormalized balance on users for simple admin/debug screens.
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE users
            SET extra_question_credits = %s, updated_at = NOW()
            WHERE id = %s
            """,
            (extra_question_credits, user_id),
        )
