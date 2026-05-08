from __future__ import annotations

import os
import sys
import argparse
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.services.memory_logging import rss_mb


def report(stage: str, **fields: object) -> None:
    # Print the same safe stage names that production logs emit, without any secrets.
    details = " ".join(f"{key}={value}" for key, value in fields.items())
    suffix = f" {details}" if details else ""
    print(f"[MEMORY] stage={stage} rss_mb={rss_mb():.1f}{suffix}", flush=True)


def _configure_mode(mode: str) -> None:
    # The probe mode intentionally overrides ambient .env values so memory comparisons are repeatable.
    if mode == "faiss":
        os.environ.update(
            {
                "APP_ENV": "development",
                "SONICMIND_MODE": "local_semantic",
                "SONICMIND_RETRIEVAL_BACKEND": "faiss",
                "ENABLE_LOCAL_EMBEDDING_MODEL": "true",
                "ENABLE_RERANKER": "true",
                "RAG_LOAD_ON_STARTUP": "false",
                "RAG_FALLBACK_MODE": "error",
                "RAG_TOP_K": "5",
                "RAG_CANDIDATE_K": "25",
                "MAX_CONTEXT_CHARS": "12000",
                "MAX_SOURCE_CHARS": "4000",
            }
        )
        return

    if mode == "auto":
        os.environ.setdefault("APP_ENV", "development")
        os.environ["SONICMIND_MODE"] = "auto"
        os.environ["SONICMIND_RETRIEVAL_BACKEND"] = "auto"
        return

    os.environ.update(
        {
            "APP_ENV": "development",
            "SONICMIND_MODE": "production_light",
            "SONICMIND_RETRIEVAL_BACKEND": "lexical",
            "ENABLE_LOCAL_EMBEDDING_MODEL": "false",
            "ENABLE_RERANKER": "false",
            "RAG_LOAD_ON_STARTUP": "false",
            "RAG_FALLBACK_MODE": "keyword",
            "RAG_TOP_K": "3",
            "RAG_CANDIDATE_K": "12",
            "MAX_CONTEXT_CHARS": "6000",
            "MAX_SOURCE_CHARS": "2000",
        }
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Measure SonicMind backend memory in a selected retrieval mode.")
    parser.add_argument("--mode", choices=("lexical", "faiss", "auto"), default="lexical")
    parser.add_argument("--route", action="store_true", help="Also exercise the full evidence router.")
    args = parser.parse_args()

    _configure_mode(args.mode)

    report("probe_process_start")

    import backend.main as backend_main
    from src.settings import resolve_runtime_settings, semantic_retrieval_ready

    report("probe_after_backend_app_import", app=backend_main.app.title)
    settings = resolve_runtime_settings()
    print(
        "[MODE] "
        f"sonicmind_mode={settings.sonicmind_mode} retrieval_backend={settings.retrieval_backend} "
        f"local_embedding={settings.local_embedding_enabled} reranker={settings.reranker_enabled}",
        flush=True,
    )

    from backend.services.knowledge_base_service import knowledge_base_ready

    report("probe_before_knowledge_base_ready")
    ready = knowledge_base_ready()
    report("probe_after_knowledge_base_ready", knowledge_base_ready=ready)

    from src.retriever import retrieve_topk

    if settings.retrieval_backend == "faiss" and not semantic_retrieval_ready():
        report("probe_semantic_unavailable", semantic_retrieval_ready=False)
        print("Semantic probe skipped: FAISS files or semantic dependencies are unavailable.", flush=True)
        return 0

    report(
        "probe_before_retrieval",
        backend=settings.retrieval_backend,
    )
    results = retrieve_topk("What is drum and bass?", k=settings.rag_candidate_k)
    report("probe_after_retrieval", results=len(results))

    if args.route or os.getenv("MEMORY_PROBE_ROUTE", "false").strip().lower() in {"1", "true", "yes"}:
        from src.services.router_service import route_evidence

        report("probe_before_route_evidence")
        routed = route_evidence(
            "What is drum and bass?",
            topk=settings.rag_top_k,
            candidate_k=settings.rag_candidate_k,
            model_name="BAAI/bge-m3",
        )
        report("probe_after_route_evidence", used_evidence=len(routed.used_evidence))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
