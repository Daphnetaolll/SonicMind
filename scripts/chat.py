import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse

from src.rag_pipeline import answer_question


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--topk", type=int, default=3, help="How many chunks to pass to the LLM")
    parser.add_argument(
        "--max-history-turns",
        type=int,
        default=3,
        help="How many recent conversation turns to remember",
    )
    parser.add_argument(
        "--show-context",
        action="store_true",
        help="Print used documents for each turn",
    )
    args = parser.parse_args()

    history = []

    print("Multi-turn RAG chat started. Type 'exit' or 'quit' to stop.")
    while True:
        query = input("\nYou: ").strip()
        if not query:
            continue
        if query.lower() in {"exit", "quit"}:
            print("Chat ended.")
            break

        result = answer_question(
            query,
            chat_history=history,
            topk=args.topk,
            max_history_turns=args.max_history_turns,
        )
        history = result.updated_chat_history

        print(f"\nAssistant: {result.answer}")
        if args.show_context:
            print("\n[Used Context]")
            if result.query_rewritten:
                print(f"Retrieval query: {result.retrieval_query}")
            print(f"Route: {' -> '.join(result.route_steps)}")
            print(f"Certainty: {result.certainty}")
            for idx, item in enumerate(result.used_evidence, start=1):
                print(
                    f"#{idx} score={item.retrieval_score:.4f} "
                    f"type={item.source_type} title={item.title}"
                )


if __name__ == "__main__":
    main()
