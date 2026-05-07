from __future__ import annotations

import os

from backend.services.memory_logging import log_memory
from src.evidence import EvidenceItem
from src.retriever import RetrievalResult, retrieve_topk


def _reranker_enabled() -> bool:
    # The current reranker is lightweight, but this flag preserves a production kill switch.
    return os.getenv("ENABLE_RERANKER", "false").strip().lower() in {"1", "true", "yes"}


def _max_source_chars() -> int:
    try:
        return max(400, int(os.getenv("MAX_SOURCE_CHARS", "2000")))
    except ValueError:
        return 2000


def _trim_source_text(text: str) -> str:
    # Bound source payload size returned to React and passed toward answer synthesis.
    stripped = text.strip()
    limit = _max_source_chars()
    if len(stripped) <= limit:
        return stripped
    return stripped[:limit].rstrip() + "..."


def _to_evidence(item: RetrievalResult) -> EvidenceItem:
    # Convert FAISS retrieval rows into the shared evidence shape used by routing and synthesis.
    full_text = _trim_source_text(item.text)
    return EvidenceItem(
        rank=item.rank,
        source_type="local",
        source_name=item.title or item.source or "Local knowledge base",
        title=item.title or item.chunk_id,
        snippet=full_text[:280].strip(),
        full_text=full_text,
        retrieval_score=item.score,
        trust_level="high",
        url=item.source if item.source and item.source.startswith("http") else None,
        chunk_id=item.chunk_id,
        metadata={"path": item.path or "", "source": item.source or ""},
    )


def retrieve_local_evidence(
    query: str,
    *,
    topk: int = 3,
    candidate_k: int = 12,
    model_name: str,
) -> tuple[list[EvidenceItem], list[RetrievalResult], list[RetrievalResult]]:
    # Retrieve a wider candidate set, rerank it, and expose both diagnostics and final evidence.
    log_memory("before_local_evidence_retrieval", topk=topk, candidate_k=candidate_k)
    retrieved = retrieve_topk(query, k=candidate_k, model_name=model_name)
    if _reranker_enabled():
        from src.reranker import rerank_documents

        reranked = rerank_documents(query, retrieved)
    else:
        reranked = retrieved
    used = reranked[:topk]
    log_memory("after_local_evidence_retrieval", retrieved=len(retrieved), used=len(used))
    return ([_to_evidence(item) for item in used], retrieved, reranked)
