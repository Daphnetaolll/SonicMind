import json
import sys
from pathlib import Path

# Allow this diagnostic script to import src modules without installing the project package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from src.embeddings import DEFAULT_EMBEDDING_MODEL, EmbeddingConfig, TextEmbedder

EMB_PATH = Path("data/processed/embeddings.npy")
META_PATH = Path("data/processed/chunk_meta.jsonl")


# Load chunk metadata beside the embedding matrix so scores can be inspected by title and preview.
def load_meta(path: Path):
    meta = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                meta.append(json.loads(line))
    return meta


# Compare a few known music questions against the stored embeddings to spot retrieval drift.
def main():
    if not EMB_PATH.exists() or not META_PATH.exists():
        raise FileNotFoundError("Missing embeddings/meta. Run scripts/embed_corpus.py first.")

    vecs = np.load(EMB_PATH)
    meta = load_meta(META_PATH)
    assert len(meta) == vecs.shape[0], "Meta and embeddings count mismatch!"

    cfg = EmbeddingConfig(model_name=DEFAULT_EMBEDDING_MODEL, normalize=True)
    embedder = TextEmbedder(cfg)

    queries = [
        "What defines electronic music?",
        "What are the main traits of techno?",
        "What is house music?",
    ]

    topk = 5

    for q in queries:
        qv = embedder.embed_query(q)
        sims = vecs @ qv
        idx = np.argsort(-sims)[:topk]

        print("\n" + "=" * 80)
        print("Q:", q)
        print("-" * 80)
        for rank, i in enumerate(idx, start=1):
            m = meta[i]
            print(f"{rank:>2}. score={float(sims[i]):.4f}  chunk_id={m['chunk_id']}  title={m.get('title')}")
            print("    preview:", m.get("text_preview", ""))
    print("\nquick similarity test done.")


if __name__ == "__main__":
    main()
