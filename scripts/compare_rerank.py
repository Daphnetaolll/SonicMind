import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse
from textwrap import shorten

from src.memory import normalize_chat_history, rewrite_query_with_history
from src.reranker import rerank_documents
from src.retriever import retrieve_topk


def _print_docs(label: str, docs):
    print(f"\n[{label}]")
    for doc in docs:
        print(f"#{doc.rank} score={doc.score:.4f} chunk_id={doc.chunk_id} title={doc.title}")
        print("   text:", shorten(doc.text.replace("\n", " "), width=220, placeholder=" ..."))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("query", type=str, help="Question to test reranking")
    parser.add_argument("--topk", type=int, default=3, help="Final number of chunks to compare")
    parser.add_argument("--candidate-k", type=int, default=10, help="Initial retrieval depth before reranking")
    args = parser.parse_args()

    history = normalize_chat_history([])
    retrieval_query, rewritten = rewrite_query_with_history(args.query, history)
    retrieved = retrieve_topk(retrieval_query, k=args.candidate_k)
    reranked = rerank_documents(retrieval_query, retrieved)

    print("\n" + "=" * 80)
    print("Q:", args.query)
    if rewritten:
        print("Retrieval query:", retrieval_query)
    print("=" * 80)

    _print_docs("Before Rerank (Top-K)", retrieved[: args.topk])
    _print_docs("After Rerank (Top-K)", reranked[: args.topk])


if __name__ == "__main__":
    main()
