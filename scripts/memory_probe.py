from __future__ import annotations

import os
import sys
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


def main() -> int:
    # Match the production-safe defaults unless the caller intentionally overrides them.
    os.environ.setdefault("SONICMIND_RETRIEVAL_BACKEND", "lexical")
    os.environ.setdefault("RAG_TOP_K", "3")
    os.environ.setdefault("RAG_CANDIDATE_K", "12")
    os.environ.setdefault("MAX_CONTEXT_CHARS", "6000")
    os.environ.setdefault("ENABLE_RERANKER", "false")
    os.environ.setdefault("ENABLE_LOCAL_EMBEDDING_MODEL", "false")

    report("probe_process_start")

    import backend.main as backend_main

    report("probe_after_backend_app_import", app=backend_main.app.title)

    from backend.services.knowledge_base_service import knowledge_base_ready

    report("probe_before_knowledge_base_ready")
    ready = knowledge_base_ready()
    report("probe_after_knowledge_base_ready", knowledge_base_ready=ready)

    from src.retriever import retrieve_topk

    report(
        "probe_before_retrieval",
        backend=os.getenv("SONICMIND_RETRIEVAL_BACKEND", "lexical"),
    )
    results = retrieve_topk("What is drum and bass?", k=int(os.getenv("RAG_CANDIDATE_K", "12")))
    report("probe_after_retrieval", results=len(results))

    if os.getenv("MEMORY_PROBE_ROUTE", "false").strip().lower() in {"1", "true", "yes"}:
        from src.services.router_service import route_evidence

        report("probe_before_route_evidence")
        routed = route_evidence("What is drum and bass?", topk=3, candidate_k=12, model_name="BAAI/bge-m3")
        report("probe_after_route_evidence", used_evidence=len(routed.used_evidence))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
