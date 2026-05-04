from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from src.embeddings import DEFAULT_EMBEDDING_MODEL, EmbeddingConfig, TextEmbedder
from src.indexer import load_faiss_index

INDEX_PATH = Path("data/index/faiss.index")
META_PATH = Path("data/processed/chunk_meta.jsonl")
CHUNKS_PATH = Path("data/processed/chunks.jsonl")


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


def retrieve_topk(query: str, k: int = 5, model_name: str = DEFAULT_EMBEDDING_MODEL) -> list[RetrievalResult]:
    # Validate all generated corpus artifacts before loading the FAISS index.
    if not INDEX_PATH.exists():
        raise FileNotFoundError("Missing FAISS index. Run scripts/build_index.py first.")
    if not META_PATH.exists():
        raise FileNotFoundError("Missing chunk_meta.jsonl. Run scripts/embed_corpus.py first.")
    if not CHUNKS_PATH.exists():
        raise FileNotFoundError("Missing chunks.jsonl. Run scripts/preprocess.py first.")

    index = load_faiss_index(INDEX_PATH)

    meta = load_jsonl(META_PATH)
    chunk_lookup = build_chunk_lookup(CHUNKS_PATH)

    embedder = TextEmbedder(EmbeddingConfig(model_name=model_name, normalize=True))
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
    return results
