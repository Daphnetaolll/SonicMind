from __future__ import annotations

from dataclasses import asdict, is_dataclass
from uuid import uuid4

from src.db import connect_db
from src.repositories import chat_repository


def _json_safe(value):
    # Convert dataclasses and nested lists into JSON-safe values for Postgres JSONB columns.
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def save_chat_message(
    *,
    user_id: str,
    question: str,
    answer: str,
    sources: list,
    spotify_results: list,
) -> None:
    # Save paid-plan history after the answer succeeds; failures here should not expose secrets.
    with connect_db() as conn:
        chat_repository.insert_chat_message(
            conn,
            message_id=str(uuid4()),
            user_id=user_id,
            question=question,
            answer=answer,
            sources=_json_safe(sources),
            spotify_results=_json_safe(spotify_results),
        )
        conn.commit()


def get_saved_history(user_id: str, *, limit: int = 25) -> list[dict]:
    # History reads do not consume question quota.
    with connect_db() as conn:
        return chat_repository.list_chat_messages(conn, user_id=user_id, limit=limit)


def delete_saved_history(user_id: str) -> int:
    # Deleting history is available to paid plans and never changes usage records.
    with connect_db() as conn:
        deleted = chat_repository.delete_chat_messages(conn, user_id=user_id)
        conn.commit()
        return deleted
