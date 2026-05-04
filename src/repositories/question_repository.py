from __future__ import annotations

from typing import Any


def create_question_log(
    conn: Any,
    *,
    question_log_id: str,
    user_id: str,
    question_text: str,
) -> dict[str, Any]:
    # Start every request as uncharged until the answer generation path succeeds.
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO question_logs (id, user_id, question_text, status, charged, charge_type)
            VALUES (%s, %s, %s, 'started', FALSE, 'none')
            RETURNING *
            """,
            (question_log_id, user_id, question_text),
        )
        row = cur.fetchone()
    return dict(row)


def mark_question_succeeded(
    conn: Any,
    *,
    question_log_id: str,
    answer_text: str,
    charge_type: str,
) -> dict[str, Any]:
    # Mark successful questions as charged so logs and usage ledger stay consistent.
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE question_logs
            SET
                answer_text = %s,
                status = 'succeeded',
                charged = TRUE,
                charge_type = %s,
                completed_at = NOW()
            WHERE id = %s
            RETURNING *
            """,
            (answer_text, charge_type, question_log_id),
        )
        row = cur.fetchone()
    return dict(row)


def mark_question_failed(
    conn: Any,
    *,
    question_log_id: str,
    error_message: str,
) -> dict[str, Any]:
    # Failed questions keep charge_type=none so users are not billed for errors.
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE question_logs
            SET
                status = 'failed',
                charged = FALSE,
                charge_type = 'none',
                error_message = %s,
                completed_at = NOW()
            WHERE id = %s
            RETURNING *
            """,
            (error_message, question_log_id),
        )
        row = cur.fetchone()
    return dict(row)
