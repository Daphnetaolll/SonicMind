from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from heapq import nlargest
from pathlib import Path
from typing import Any

from backend.services.memory_logging import log_memory
from src.embeddings import DEFAULT_EMBEDDING_MODEL, EmbeddingConfig, TextEmbedder
from src.indexer import load_faiss_index

INDEX_PATH = Path("data/index/faiss.index")
META_PATH = Path("data/processed/chunk_meta.jsonl")
CHUNKS_PATH = Path("data/processed/chunks.jsonl")
LEXICAL_DEFAULT_BACKEND = "lexical"
SEMANTIC_BACKENDS = {"faiss", "semantic"}
STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "do",
    "does",
    "for",
    "from",
    "how",
    "in",
    "is",
    "it",
    "its",
    "me",
    "music",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "was",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
    "with",
}


# RetrievalResult keeps FAISS scores tied to the original chunk metadata and text.
@dataclass
class RetrievalResult:
    rank: int
    score: float
    chunk_id: str
    title: str | None
    source: str | None
    path: str | None
    text: str


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    # Load JSONL records from the processed corpus files used by retrieval.
    items = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items


def build_chunk_lookup(chunks_path: Path) -> dict[str, dict[str, Any]]:
    # Index chunks by id so FAISS metadata rows can recover full source text.
    chunks = load_jsonl(chunks_path)
    lookup = {c["chunk_id"]: c for c in chunks}
    return lookup


@lru_cache(maxsize=4)
def _cached_index(index_path: str):
    # Keep the FAISS index in memory so repeated chat requests do not reload the same binary artifact.
    log_memory("before_faiss_load", path=Path(index_path).name)
    index = load_faiss_index(Path(index_path))
    log_memory("after_faiss_load", path=Path(index_path).name)
    return index


@lru_cache(maxsize=4)
def _cached_jsonl(path: str) -> tuple[dict[str, Any], ...]:
    # JSONL corpus metadata is immutable between rebuilds, so it is safe to cache until explicitly cleared.
    jsonl_path = Path(path)
    log_memory("before_knowledge_jsonl_load", path=jsonl_path.name)
    records = tuple(load_jsonl(jsonl_path))
    log_memory("after_knowledge_jsonl_load", path=jsonl_path.name, records=len(records))
    return records


@lru_cache(maxsize=4)
def _cached_chunk_lookup(chunks_path: str) -> dict[str, dict[str, Any]]:
    path = Path(chunks_path)
    log_memory("before_chunk_lookup_load", path=path.name)
    lookup = build_chunk_lookup(path)
    log_memory("after_chunk_lookup_load", path=path.name, records=len(lookup))
    return lookup


@lru_cache(maxsize=4)
def _cached_embedder(model_name: str) -> TextEmbedder:
    # SentenceTransformer construction may contact Hugging Face; reuse it across requests to avoid rate limits.
    if os.getenv("ENABLE_LOCAL_EMBEDDING_MODEL", "true").strip().lower() in {"0", "false", "no"}:
        raise RuntimeError("Local embedding model is disabled.")

    log_memory("before_embedding_model_load", model=model_name)
    embedder = TextEmbedder(EmbeddingConfig(model_name=model_name, normalize=True))
    log_memory("after_embedding_model_load", model=model_name)
    return embedder


def clear_retrieval_cache() -> None:
    """Clear cached retrieval artifacts after rebuilding the local knowledge base."""
    _cached_index.cache_clear()
    _cached_jsonl.cache_clear()
    _cached_chunk_lookup.cache_clear()
    _cached_embedder.cache_clear()


def _retrieval_backend() -> str:
    # Keep production chat lightweight unless semantic FAISS retrieval is explicitly enabled.
    return os.getenv("SONICMIND_RETRIEVAL_BACKEND", LEXICAL_DEFAULT_BACKEND).strip().lower()


def _fallback_mode() -> str:
    # Keyword fallback keeps chat alive when semantic RAG cannot fit in the available memory.
    return os.getenv("RAG_FALLBACK_MODE", "keyword").strip().lower()


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _bounded_k(k: int) -> int:
    # Cap retrieval fanout from env so plan settings cannot create runaway prompt or rerank memory.
    limit = max(1, _env_int("RAG_CANDIDATE_K", 12))
    return max(1, min(k, limit))


def _tokens(text: str) -> list[str]:
    return [
        token
        for token in re.findall(r"[a-z0-9][a-z0-9\-]+", text.lower())
        if token not in STOPWORDS and len(token) > 2
    ]


def _normalized_phrase(text: str) -> str:
    return " ".join(_tokens(text))


def _lexical_score(query: str, title: str, text: str) -> float:
    query_tokens = _tokens(query)
    if not query_tokens:
        return 0.0

    lowered_title = title.lower()
    lowered_text = text.lower()
    phrase = _normalized_phrase(query)
    score = 0.0

    if phrase and phrase in lowered_title:
        score += 0.55
    if phrase and phrase in lowered_text:
        score += 0.45

    for token in query_tokens:
        if token in lowered_title:
            score += 0.2
        if token in lowered_text:
            score += min(lowered_text.count(token), 4) * 0.1

    coverage = sum(1 for token in set(query_tokens) if token in lowered_title or token in lowered_text) / len(set(query_tokens))
    score += coverage * 0.4
    return min(score, 1.0)


def _lexical_retrieve_topk(query: str, k: int) -> list[RetrievalResult]:
    # Lexical retrieval avoids loading large embedding models on memory-constrained production instances.
    log_memory("before_lexical_retrieval", k=k)
    if not META_PATH.exists():
        raise FileNotFoundError("Missing chunk_meta.jsonl. Run scripts/embed_corpus.py first.")
    if not CHUNKS_PATH.exists():
        raise FileNotFoundError("Missing chunks.jsonl. Run scripts/preprocess.py first.")

    meta = _cached_jsonl(str(META_PATH))
    chunk_lookup = _cached_chunk_lookup(str(CHUNKS_PATH))

    def scored_rows():
        # Stream candidate scores into heap selection instead of sorting the entire corpus.
        for index, item in enumerate(meta):
            chunk_id = item.get("chunk_id")
            full = chunk_lookup.get(chunk_id, {})
            title = item.get("title") or ""
            text = full.get("text", "")
            yield (_lexical_score(query, title, text), index, item, full)

    top_rows = nlargest(k, scored_rows(), key=lambda row: (row[0], -row[1]))

    results: list[RetrievalResult] = []
    for rank, (score, _index, item, full) in enumerate(top_rows, start=1):
        chunk_id = item.get("chunk_id")
        results.append(
            RetrievalResult(
                rank=rank,
                score=float(score),
                chunk_id=chunk_id,
                title=item.get("title"),
                source=item.get("source"),
                path=item.get("path"),
                text=full.get("text", ""),
            )
        )
    log_memory("after_lexical_retrieval", k=k, results=len(results))
    return results


def _semantic_retrieve_topk(query: str, k: int, model_name: str) -> list[RetrievalResult]:
    # Semantic retrieval remains available for environments with enough memory and a warmed model cache.
    log_memory("before_semantic_retrieval", k=k)
    if not INDEX_PATH.exists():
        raise FileNotFoundError("Missing FAISS index. Run scripts/build_index.py first.")
    if not META_PATH.exists():
        raise FileNotFoundError("Missing chunk_meta.jsonl. Run scripts/embed_corpus.py first.")
    if not CHUNKS_PATH.exists():
        raise FileNotFoundError("Missing chunks.jsonl. Run scripts/preprocess.py first.")

    index = _cached_index(str(INDEX_PATH))
    meta = _cached_jsonl(str(META_PATH))
    chunk_lookup = _cached_chunk_lookup(str(CHUNKS_PATH))
    embedder = _cached_embedder(model_name)
    import numpy as np

    qv = embedder.embed_query(query).astype(np.float32).reshape(1, -1)

    # Search normalized embeddings with inner product, then attach metadata and chunk text.
    scores, idxs = index.search(qv, k)
    scores = scores[0]
    idxs = idxs[0]

    results: list[RetrievalResult] = []
    for rank, (score, i) in enumerate(zip(scores, idxs), start=1):
        if i == -1:
            continue
        m = meta[int(i)]
        chunk_id = m.get("chunk_id")
        full = chunk_lookup.get(chunk_id, {})
        results.append(
            RetrievalResult(
                rank=rank,
                score=float(score),
                chunk_id=chunk_id,
                title=m.get("title"),
                source=m.get("source"),
                path=m.get("path"),
                text=full.get("text", ""),
            )
        )
    log_memory("after_semantic_retrieval", k=k, results=len(results))
    return results


def retrieve_topk(query: str, k: int = 5, model_name: str = DEFAULT_EMBEDDING_MODEL) -> list[RetrievalResult]:
    effective_k = _bounded_k(k)
    backend = _retrieval_backend()
    log_memory("before_retrieve_topk", backend=backend, requested_k=k, effective_k=effective_k)

    try:
        if backend not in SEMANTIC_BACKENDS:
            results = _lexical_retrieve_topk(query, effective_k)
        else:
            results = _semantic_retrieve_topk(query, effective_k, model_name)
        log_memory("after_retrieve_topk", backend=backend, results=len(results))
        return results
    except Exception as exc:
        # If semantic retrieval is unavailable, keep chat usable with the local corpus instead of failing the request.
        log_memory("retrieve_topk_failed", backend=backend, error_type=exc.__class__.__name__)
        if backend in SEMANTIC_BACKENDS:
            try:
                results = _lexical_retrieve_topk(query, effective_k)
                log_memory("after_retrieve_topk_fallback", backend="lexical", results=len(results))
                return results
            except Exception as fallback_exc:
                log_memory("retrieve_topk_fallback_failed", error_type=fallback_exc.__class__.__name__)

        if _fallback_mode() in {"keyword", "llm_only"}:
            return []
        raise
