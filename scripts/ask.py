import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse
from textwrap import shorten

from src.rag_pipeline import answer_question


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("query", type=str, help="Question or query")
    parser.add_argument("--topk", type=int, default=3, help="How many retrieved chunks to pass to the LLM")
    parser.add_argument(
        "--show-context",
        action="store_true",
        help="Print retrieved chunks before the final answer",
    )
    args = parser.parse_args()

    pipeline_result = answer_question(args.query, topk=args.topk)

    print("\n" + "=" * 80)
    print("Q:", pipeline_result.query)
    print("=" * 80)

    if args.show_context:
        print("\n[Retrieved Context]")
        print(
            f"Candidates searched: {pipeline_result.candidate_k} | "
            f"Evidence used: {len(pipeline_result.used_evidence)}"
        )
        if pipeline_result.query_rewritten:
            print(f"Retrieval query: {pipeline_result.retrieval_query}")
        print(f"Route: {' -> '.join(pipeline_result.route_steps)}")
        print(f"Certainty: {pipeline_result.certainty}")
        for idx, item in enumerate(pipeline_result.used_evidence, start=1):
            print(
                f"\n#{idx}  score={item.retrieval_score:.4f}  "
                f"type={item.source_type}  title={item.title}"
            )
            print(f"   source={item.source_name}  url={item.url or 'n/a'}")
            print("   text:", shorten(item.full_text.replace("\n", " "), width=240, placeholder=" ..."))

    print("\n[Answer]")
    print(pipeline_result.answer)
    print("\nask complete.")


if __name__ == "__main__":
    main()
