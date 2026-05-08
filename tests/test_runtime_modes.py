from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from src.settings import resolve_runtime_settings, semantic_retrieval_ready


ROOT_DIR = Path(__file__).resolve().parents[1]
HEAVY_MODULES = ("torch", "transformers", "sentence_transformers", "faiss")


def _mode_env(**overrides: str) -> dict[str, str]:
    # Tests set every mode switch explicitly so local .env files cannot change expectations.
    env = os.environ.copy()
    env.update(
        {
            "APP_ENV": "test",
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
            "PYTHONPATH": str(ROOT_DIR),
        }
    )
    env.update(overrides)
    return env


def test_lightweight_backend_import_does_not_import_heavy_modules() -> None:
    # App import must stay cheap even when semantic dependencies happen to be installed locally.
    code = """
import json
import sys
import backend.main as main

payload = {
    "heavy_modules": {name: name in sys.modules for name in ("torch", "transformers", "sentence_transformers", "faiss")},
    "health": main.health().model_dump(),
}
print("JSON_RESULT=" + json.dumps(payload, sort_keys=True))
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT_DIR,
        env=_mode_env(),
        capture_output=True,
        text=True,
        check=True,
    )

    payload_line = next(line for line in result.stdout.splitlines() if line.startswith("JSON_RESULT="))
    payload = json.loads(payload_line.removeprefix("JSON_RESULT="))

    assert payload["heavy_modules"] == {name: False for name in HEAVY_MODULES}
    assert payload["health"]["retrieval_backend"] == "lexical"
    assert payload["health"]["local_embedding_enabled"] is False
    assert payload["health"]["reranker_enabled"] is False


def test_lightweight_retrieval_path_returns_local_results(monkeypatch) -> None:
    # Lexical mode should answer local retrieval queries without loading embeddings or FAISS.
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("SONICMIND_MODE", "production_light")
    monkeypatch.setenv("SONICMIND_RETRIEVAL_BACKEND", "lexical")
    monkeypatch.setenv("ENABLE_LOCAL_EMBEDDING_MODEL", "false")
    monkeypatch.setenv("ENABLE_RERANKER", "false")
    monkeypatch.setenv("RAG_CANDIDATE_K", "12")

    from src.retriever import clear_retrieval_cache, retrieve_topk

    clear_retrieval_cache()
    results = retrieve_topk("What is drum and bass?", k=3)

    assert len(results) == 3
    assert any("drum and bass" in result.text.lower() for result in results)


def test_semantic_mode_config_resolves_to_faiss(monkeypatch) -> None:
    # Semantic mode remains a first-class configuration even when tests do not load the model.
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("SONICMIND_MODE", "local_semantic")
    monkeypatch.setenv("SONICMIND_RETRIEVAL_BACKEND", "faiss")
    monkeypatch.setenv("ENABLE_LOCAL_EMBEDDING_MODEL", "true")
    monkeypatch.setenv("ENABLE_RERANKER", "true")
    monkeypatch.setenv("RAG_FALLBACK_MODE", "error")

    settings = resolve_runtime_settings()

    assert settings.sonicmind_mode == "local_semantic"
    assert settings.retrieval_backend == "faiss"
    assert settings.local_embedding_enabled is True
    assert settings.reranker_enabled is True
    assert settings.fallback_mode == "error"


def test_auto_backend_respects_local_embedding_kill_switch(monkeypatch) -> None:
    # Auto mode should not choose FAISS when the local embedding model is explicitly disabled.
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("SONICMIND_MODE", "auto")
    monkeypatch.setenv("SONICMIND_RETRIEVAL_BACKEND", "auto")
    monkeypatch.setenv("ENABLE_LOCAL_EMBEDDING_MODEL", "false")

    settings = resolve_runtime_settings()

    assert settings.retrieval_backend == "lexical"
    assert settings.local_embedding_enabled is False


def test_semantic_retrieval_smoke_when_explicitly_enabled(monkeypatch) -> None:
    # Loading BAAI/bge-m3 is intentionally opt-in so regular CI does not surprise-download a large model.
    if os.getenv("RUN_SEMANTIC_SMOKE", "").lower() not in {"1", "true", "yes"}:
        pytest.skip("Set RUN_SEMANTIC_SMOKE=true to load the local semantic model.")

    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("SONICMIND_MODE", "local_semantic")
    monkeypatch.setenv("SONICMIND_RETRIEVAL_BACKEND", "faiss")
    monkeypatch.setenv("ENABLE_LOCAL_EMBEDDING_MODEL", "true")
    monkeypatch.setenv("ENABLE_RERANKER", "true")
    monkeypatch.setenv("RAG_FALLBACK_MODE", "error")

    if not semantic_retrieval_ready():
        pytest.skip("Semantic files or dependencies are unavailable.")

    from src.retriever import clear_retrieval_cache, retrieve_topk

    clear_retrieval_cache()
    results = retrieve_topk("What is drum and bass?", k=3)

    assert results
