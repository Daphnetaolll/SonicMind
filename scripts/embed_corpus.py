import sys
from pathlib import Path

# Allow this script to run from the project root without installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import json

import numpy as np

from src.embeddings import DEFAULT_EMBEDDING_MODEL, EmbeddingConfig, TextEmbedder

CHUNKS_PATH = Path("data/processed/chunks.jsonl")
OUT_EMB = Path("data/processed/embeddings.npy")
OUT_META = Path("data/processed/chunk_meta.jsonl")


def load_chunks(path: Path) -> list[dict]:
    # Load processed chunk records produced by scripts/preprocess.py.
    items = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            items.append(json.loads(line))
    return items


def main():
    # Embed chunks in a stable order so FAISS rows and metadata rows stay aligned.
    if not CHUNKS_PATH.exists():
        raise FileNotFoundError(f"Missing {CHUNKS_PATH}. Run scripts/preprocess.py first.")

    chunks = load_chunks(CHUNKS_PATH)

    chunks = sorted(chunks, key=lambda x: x.get("chunk_id", ""))

    texts = [c["text"] for c in chunks]
    # Keep only lightweight metadata next to embeddings; full text stays in chunks.jsonl.
    meta = [
        {
            "chunk_id": c.get("chunk_id"),
            "title": c.get("title"),
            "source": c.get("source"),
            "path": c.get("path"),
            "text_preview": (c.get("text") or "")[:120],
        }
        for c in chunks
    ]

    cfg = EmbeddingConfig(
        model_name=DEFAULT_EMBEDDING_MODEL,
        normalize=True,
        batch_size=32,
    )
    embedder = TextEmbedder(cfg)
    vecs = embedder.embed_texts(texts)

    # Store vector data separately from metadata so runtime retrieval can load each format efficiently.
    OUT_EMB.parent.mkdir(parents=True, exist_ok=True)
    np.save(OUT_EMB, vecs)

    with OUT_META.open("w", encoding="utf-8") as f:
        for m in meta:
            f.write(json.dumps(m, ensure_ascii=False) + "\n")

    print(f"Saved embeddings: {OUT_EMB} shape={vecs.shape}")
    print(f"Saved metadata: {OUT_META} rows={len(meta)}")


if __name__ == "__main__":
    main()
