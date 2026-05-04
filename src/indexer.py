from __future__ import annotations

from pathlib import Path

import numpy as np
import faiss


def build_faiss_index(embeddings: np.ndarray, use_ip: bool = True) -> faiss.Index:
    """
    Build a FAISS index from embeddings.
    - use_ip=True: IndexFlatIP (inner product). If embeddings are normalized, IP ~= cosine similarity.
    - use_ip=False: IndexFlatL2 (euclidean distance).
    """
    if embeddings.dtype != np.float32:
        embeddings = embeddings.astype(np.float32)

    if embeddings.ndim != 2:
        raise ValueError(f"Embeddings must be 2D array, got shape={embeddings.shape}")

    # Use a flat index for the MVP so retrieval is exact and easy to reason about.
    dim = embeddings.shape[1]
    index = faiss.IndexFlatIP(dim) if use_ip else faiss.IndexFlatL2(dim)
    index.add(embeddings)
    return index


def save_faiss_index(index: faiss.Index, path: Path) -> None:
    # Ensure the generated index directory exists before writing the binary FAISS artifact.
    path.parent.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(path))


def load_faiss_index(path: Path) -> faiss.Index:
    # Fail fast with a setup hint when the knowledge-base index has not been built.
    if not path.exists():
        raise FileNotFoundError(f"FAISS index not found: {path}")
    return faiss.read_index(str(path))


def maybe_normalize(embeddings: np.ndarray) -> np.ndarray:
    """
    Normalize embeddings in-place (L2 norm = 1). Useful if you want IP ~= cosine.
    Only needed if you did NOT normalize during embedding.
    """
    if embeddings.dtype != np.float32:
        embeddings = embeddings.astype(np.float32)
    faiss.normalize_L2(embeddings)
    return embeddings
