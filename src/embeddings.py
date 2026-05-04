from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sentence_transformers import SentenceTransformer

DEFAULT_EMBEDDING_MODEL = "BAAI/bge-m3"


# EmbeddingConfig keeps corpus and query embedding settings in one reusable shape.
@dataclass
class EmbeddingConfig:
    model_name: str = DEFAULT_EMBEDDING_MODEL
    device: str | None = None
    normalize: bool = True
    batch_size: int = 32


class TextEmbedder:
    def __init__(self, cfg: EmbeddingConfig = EmbeddingConfig()):
        # Load the sentence-transformers model once per embedder instance.
        self.cfg = cfg
        self.model = SentenceTransformer(cfg.model_name, device=cfg.device)

    def embed_texts(self, texts: list[str]) -> np.ndarray:
        # Normalize embeddings so FAISS inner product behaves like cosine similarity.
        vecs = self.model.encode(
            texts,
            batch_size=self.cfg.batch_size,
            show_progress_bar=True,
            convert_to_numpy=True,
            normalize_embeddings=self.cfg.normalize,
        )
        return vecs.astype(np.float32)

    def embed_query(self, query: str) -> np.ndarray:
        return self.embed_texts([query])[0]
