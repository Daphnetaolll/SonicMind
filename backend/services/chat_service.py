from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.rag_pipeline import RAGPipelineResult, answer_question
from src.services.question_service import (
    mark_question_failed,
    mark_question_succeeded,
    start_question,
)
from src.services.quota_service import QuotaStatus, record_successful_question_usage
from backend.services.history_service import save_chat_message


@dataclass
class ChatServiceResult:
    """The UI-facing result of one charged RAG question."""

    result: RAGPipelineResult
    remaining_quota: QuotaStatus


def answer_user_question(
    *,
    user_id: str,
    question: str,
    quota: QuotaStatus,
    chat_history: list[Any] | None,
    topk: int,
    max_history_turns: int,
) -> ChatServiceResult:
    """
    Orchestrate the durable question lifecycle outside Streamlit:
    create a log, run the existing RAG pipeline, charge quota only on success,
    then mark the question succeeded. This preserves the old behavior while
    giving FastAPI one clean function to call later.
    """
    question_log_id = start_question(user_id, question)
    try:
        result = answer_question(
            question,
            chat_history=chat_history,
            topk=topk,
            max_history_turns=max_history_turns,
            max_answer_tokens=quota.max_answer_tokens,
            spotify_limit=quota.spotify_limit,
            playlist_style=quota.playlist_style,
        )
        charge_type = quota.charge_type
        mark_question_succeeded(
            question_log_id,
            result.answer,
            charge_type=charge_type,
        )
        remaining_quota = record_successful_question_usage(
            user_id=user_id,
            question_log_id=question_log_id,
            quota=quota,
        )
        if quota.save_history:
            try:
                save_chat_message(
                    user_id=user_id,
                    question=question,
                    answer=result.answer,
                    sources=result.used_evidence,
                    spotify_results=result.spotify_cards,
                )
            except Exception:
                # History is a paid convenience feature; it should not break a successful answer response.
                pass
    except Exception as exc:
        mark_question_failed(question_log_id, str(exc))
        raise

    return ChatServiceResult(result=result, remaining_quota=remaining_quota)
