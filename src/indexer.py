from __future__ import annotations

from pathlib import Path
from typing import Any


def build_faiss_index(embeddings: Any, use_ip: bool = True) -> Any:
    """
    Build a FAISS index from embeddings.
    - use_ip=True: IndexFlatIP (inner product). If embeddings are normalized, IP ~= cosine similarity.
    - use_ip=False: IndexFlatL2 (euclidean distance).
    """
    # FAISS and numpy are build/query-time dependencies, so import them only for FAISS operations.
    import faiss
    import numpy as np

    if embeddings.dtype != np.float32:
        embeddings = embeddings.astype(np.float32)

    if embeddings.ndim != 2:
        raise ValueError(f"Embeddings must be 2D array, got shape={embeddings.shape}")

    # Use a flat index for the MVP so retrieval is exact and easy to reason about.
    dim = embeddings.shape[1]
    index = faiss.IndexFlatIP(dim) if use_ip else faiss.IndexFlatL2(dim)
    index.add(embeddings)
    return index


def save_faiss_index(index: Any, path: Path) -> None:
    # Ensure the generated index directory exists before writing the binary FAISS artifact.
    import faiss

    path.parent.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(path))


def load_faiss_index(path: Path) -> Any:
    # Fail fast with a setup hint when the knowledge-base index has not been built.
    import faiss

    if not path.exists():
        raise FileNotFoundError(f"FAISS index not found: {path}")
    return faiss.read_index(str(path))


def maybe_normalize(embeddings: Any) -> Any:
    """
    Normalize embeddings in-place (L2 norm = 1). Useful if you want IP ~= cosine.
    Only needed if you did NOT normalize during embedding.
    """
    # Keep optional FAISS normalization out of plain API imports.
    import faiss
    import numpy as np

    if embeddings.dtype != np.float32:
        embeddings = embeddings.astype(np.float32)
    faiss.normalize_L2(embeddings)
    return embeddings
