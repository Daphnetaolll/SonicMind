from __future__ import annotations

import re
from typing import Iterable

from src.retriever import RetrievalResult


def _extract_query_hints(query: str) -> list[str]:
    # Strip common question framing so title/text matches focus on the actual topic.
    cleaned = re.sub(r"[^a-z0-9]+", " ", query.lower()).strip()
    common_phrases = [
        "what is",
        "tell me about",
        "what are the characteristics of",
        "what are the key traits of",
        "where did",
        "where does",
        "what subgenres does",
        "what styles does",
        "what types of",
        "explain",
    ]
    for phrase in common_phrases:
        cleaned = cleaned.replace(phrase, "")

    hints: list[str] = []
    if cleaned:
        hints.append(cleaned)
        if cleaned.endswith(" music"):
            hints.append(cleaned[:-6].strip())
    return [hint for hint in hints if hint]


def _is_definition_query(query: str) -> bool:
    lowered = query.lower()
    markers = ("what is", "define", "meaning of", "explain")
    return any(marker in lowered for marker in markers)


def _is_enumeration_query(query: str) -> bool:
    lowered = query.lower()
    markers = ("what are", "which", "types", "styles", "subgenres", "categories", "include")
    return any(marker in lowered for marker in markers)


def rerank_documents(query: str, docs: Iterable[RetrievalResult]) -> list[RetrievalResult]:
    """
    Lightweight reranker:
    - Uses simple heuristics aligned with common question types
    - Promotes better definition chunks for definition questions
    - Promotes list-like chunks and title diversity for enumeration questions
    """
    items = list(docs)
    if not items:
        return []

    # Apply small heuristic bonuses on top of vector scores for common definition/enumeration questions.
    query_hints = _extract_query_hints(query)
    is_definition_query = _is_definition_query(query)
    is_enumeration_query = _is_enumeration_query(query)
    definition_markers = ("is a", "refers to", "is an", "typically", "overview", "also known as")
    enumeration_markers = ("styles", "subgenres", "types", "categories", "includes", "for example", "such as")

    def heuristic_score(item: RetrievalResult) -> float:
        text = item.text.lower()
        title = (item.title or "").lower()
        bonus = 0.0

        if is_definition_query and item.chunk_id.endswith("-0"):
            bonus += 0.05
        if is_enumeration_query and item.chunk_id.endswith("-0"):
            bonus -= 0.02

        if is_definition_query and any(marker in item.text for marker in definition_markers):
            bonus += 0.05
        if is_enumeration_query and any(marker in item.text for marker in enumeration_markers):
            bonus += 0.08

        for hint in query_hints:
            if hint and title and hint in title:
                bonus += 0.08
                break

        for hint in query_hints:
            if hint and hint in text:
                bonus += 0.03
                break

        if is_enumeration_query and ("," in item.text or ";" in item.text):
            bonus += 0.02

        return item.score + bonus

    scored_docs = sorted(items, key=heuristic_score, reverse=True)

    if is_enumeration_query:
        # Enumeration answers benefit from title diversity before repeated chunks from the same source.
        reranked: list[RetrievalResult] = []
        seen_titles: set[str] = set()

        for item in scored_docs:
            title_key = (item.title or "").strip().lower()
            if title_key and title_key not in seen_titles:
                reranked.append(item)
                seen_titles.add(title_key)

        for item in scored_docs:
            if item not in reranked:
                reranked.append(item)
    else:
        reranked = scored_docs

    return [
        RetrievalResult(
            rank=idx,
            score=item.score,
            chunk_id=item.chunk_id,
            title=item.title,
            source=item.source,
            path=item.path,
            text=item.text,
        )
        for idx, item in enumerate(reranked, start=1)
    ]
