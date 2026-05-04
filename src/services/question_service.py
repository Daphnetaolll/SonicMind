from __future__ import annotations

from uuid import uuid4

from src.db import connect_db
from src.repositories import question_repository


def start_question(user_id: str, question_text: str) -> str:
    # Create a durable question log before retrieval so failures can be recorded cleanly.
    question_log_id = str(uuid4())
    with connect_db() as conn:
        question_repository.create_question_log(
            conn,
            question_log_id=question_log_id,
            user_id=user_id,
            question_text=question_text,
        )
        conn.commit()
    return question_log_id


def mark_question_succeeded(question_log_id: str, answer_text: str, charge_type: str) -> None:
    # Store the final answer and charge type after quota usage has been recorded.
    with connect_db() as conn:
        question_repository.mark_question_succeeded(
            conn,
            question_log_id=question_log_id,
            answer_text=answer_text,
            charge_type=charge_type,
        )
        conn.commit()


def mark_question_failed(question_log_id: str, error_message: str) -> None:
    # Preserve the error for admins while keeping the question uncharged.
    with connect_db() as conn:
        question_repository.mark_question_failed(
            conn,
            question_log_id=question_log_id,
            error_message=error_message,
        )
        conn.commit()
