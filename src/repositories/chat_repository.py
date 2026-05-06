from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb


def insert_chat_message(
    conn: Any,
    *,
    message_id: str,
    user_id: str,
    question: str,
    answer: str,
    sources: list[dict],
    spotify_results: list[dict],
) -> dict[str, Any]:
    # Paid-plan chat history stores only browser-safe answer artifacts, not provider secrets.
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO chat_messages (
                id,
                user_id,
                question,
                answer,
                sources_json,
                spotify_results_json
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (message_id, user_id, question, answer, Jsonb(sources), Jsonb(spotify_results)),
        )
        row = cur.fetchone()
    return dict(row)


def list_chat_messages(conn: Any, *, user_id: str, limit: int = 25) -> list[dict[str, Any]]:
    # Newest-first history keeps the sidebar/API response small for the portfolio MVP.
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, question, answer, sources_json, spotify_results_json, created_at
            FROM chat_messages
            WHERE user_id = %s
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (user_id, limit),
        )
        rows = cur.fetchall()
    return [dict(row) for row in rows]


def delete_chat_messages(conn: Any, *, user_id: str) -> int:
    # Users on paid plans can clear their saved history without touching quota records.
    with conn.cursor() as cur:
        cur.execute(
            """
            DELETE FROM chat_messages
            WHERE user_id = %s
            """,
            (user_id,),
        )
        return int(cur.rowcount or 0)
