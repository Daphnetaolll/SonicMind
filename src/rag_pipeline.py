from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.embeddings import DEFAULT_EMBEDDING_MODEL
from src.evidence import AnswerSynthesis, Citation, EvidenceAssessment, EvidenceItem
from src.generator import (
    DEFAULT_SYSTEM_PROMPT,
    LLMConfig,
    synthesize_answer,
)
from src.memory import (
    ChatTurn,
    append_chat_turn,
    normalize_chat_history,
    rewrite_query_with_history,
)
from src.music.music_router import build_music_response
from src.music.schemas import (
    MusicRoutingResult,
    QueryUnderstandingResult,
    RankedMusicEntity,
    ResolvedMusicEntity,
    SpotifyCard,
)
from src.retriever import RetrievalResult
from src.services.router_service import route_evidence


# RAGPipelineResult carries every artifact the UI needs for answer, citations, routing, and music cards.
@dataclass
class RAGPipelineResult:
    query: str
    retrieval_query: str
    query_rewritten: bool
    answer: str
    candidate_k: int
    topk: int
    chat_history: list[ChatTurn]
    updated_chat_history: list[ChatTurn]
    history_context: str
    retrieved_documents: list[RetrievalResult]
    reranked_documents: list[RetrievalResult]
    local_evidence: list[EvidenceItem]
    site_evidence: list[EvidenceItem]
    web_evidence: list[EvidenceItem]
    used_evidence: list[EvidenceItem]
    local_assessment: EvidenceAssessment
    final_assessment: EvidenceAssessment
    certainty: str
    citations: list[Citation]
    route_steps: list[str]
    uncertainty_note: str | None
    user_prompt: str
    answer_synthesis: AnswerSynthesis
    query_understanding: QueryUnderstandingResult
    resolved_entities: list[ResolvedMusicEntity]
    ranked_entities: list[RankedMusicEntity]
    spotify_cards: list[SpotifyCard]
    music_routing: MusicRoutingResult


def answer_question(
    query: str,
    chat_history: list[Any] | None = None,
    *,
    topk: int = 3,
    candidate_k: int | None = None,
    max_history_turns: int = 3,
    model_name: str = DEFAULT_EMBEDDING_MODEL,
    llm_config: LLMConfig | None = None,
    system_prompt: str = DEFAULT_SYSTEM_PROMPT,
) -> RAGPipelineResult:
    # Normalize recent chat and rewrite coreferences before retrieval so follow-up questions stay grounded.
    history = normalize_chat_history(chat_history, max_turns=max_history_turns)
    effective_candidate_k = candidate_k or max(topk * 4, 12)
    retrieval_query, query_rewritten = rewrite_query_with_history(query, history)

    routing = route_evidence(
        retrieval_query,
        topk=topk,
        candidate_k=effective_candidate_k,
        model_name=model_name,
    )
    # Build music-specific structure before synthesis so the written answer and Spotify cards share candidates.
    music_routing = build_music_response(query, "", routing.used_evidence)
    config = llm_config or LLMConfig.from_env()
    synthesis = synthesize_answer(
        query,
        routing.used_evidence,
        routing.final_assessment,
        chat_history=history,
        config=config,
        system_prompt=system_prompt,
        music_routing=music_routing,
    )
    updated_history = append_chat_turn(history, query, synthesis.answer, max_turns=max_history_turns)

    # Return both final UI fields and diagnostic artifacts for sources, routing, and debugging.
    return RAGPipelineResult(
        query=query,
        retrieval_query=retrieval_query,
        query_rewritten=query_rewritten,
        answer=synthesis.answer,
        candidate_k=effective_candidate_k,
        topk=topk,
        chat_history=history,
        updated_chat_history=updated_history,
        history_context="\n".join(
            [f"User: {turn.user}\nAssistant: {turn.assistant}" for turn in history]
        ),
        retrieved_documents=routing.retrieved_documents,
        reranked_documents=routing.reranked_documents,
        local_evidence=routing.local_evidence,
        site_evidence=routing.site_evidence,
        web_evidence=routing.web_evidence,
        used_evidence=routing.used_evidence,
        local_assessment=routing.local_assessment,
        final_assessment=routing.final_assessment,
        certainty=synthesis.certainty,
        citations=synthesis.citations,
        route_steps=routing.route_steps,
        uncertainty_note=synthesis.uncertainty_note,
        user_prompt="",
        answer_synthesis=synthesis,
        query_understanding=music_routing.query_understanding,
        resolved_entities=music_routing.resolved_entities,
        ranked_entities=music_routing.ranked_entities,
        spotify_cards=music_routing.spotify_cards,
        music_routing=music_routing,
    )
