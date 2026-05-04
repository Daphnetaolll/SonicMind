import sys
from pathlib import Path

# Allow this command-line query tool to import src modules without installing the project package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse
from textwrap import shorten

from src.retriever import retrieve_topk


# Run a top-k retrieval check and print compact previews for local debugging.
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("query", type=str, help="Question or query")
    parser.add_argument("--topk", type=int, default=5)
    args = parser.parse_args()

    results = retrieve_topk(args.query, k=args.topk)

    print("\n" + "=" * 80)
    print("Q:", args.query)
    print("=" * 80)

    for r in results:
        print(f"\n#{r.rank}  score={r.score:.4f}  chunk_id={r.chunk_id}")
        print(f"   title={r.title}  source={r.source}")
        print("   text:", shorten(r.text.replace("\n", " "), width=240, placeholder=" ..."))

    print("\nquery complete.")


if __name__ == "__main__":
    main()
