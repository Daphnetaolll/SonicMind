from __future__ import annotations

from src.evidence import EvidenceItem
from src.retriever import RetrievalResult, retrieve_topk
from src.reranker import rerank_documents


def _to_evidence(item: RetrievalResult) -> EvidenceItem:
    # Convert FAISS retrieval rows into the shared evidence shape used by routing and synthesis.
    return EvidenceItem(
        rank=item.rank,
        source_type="local",
        source_name=item.title or item.source or "Local knowledge base",
        title=item.title or item.chunk_id,
        snippet=item.text[:280].strip(),
        full_text=item.text.strip(),
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
    retrieved = retrieve_topk(query, k=candidate_k, model_name=model_name)
    reranked = rerank_documents(query, retrieved)
    used = reranked[:topk]
    return ([_to_evidence(item) for item in used], retrieved, reranked)
