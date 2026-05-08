from __future__ import annotations

from src.retriever import retrieve_topk


def test_retrieve_topk_defaults_to_lexical_without_loading_embedder(monkeypatch) -> None:
    # Production chat should not cold-load a large embedding model unless semantic retrieval is explicitly enabled.
    monkeypatch.setenv("SONICMIND_MODE", "production_light")
    monkeypatch.delenv("SONICMIND_RETRIEVAL_BACKEND", raising=False)
    monkeypatch.setenv("ENABLE_LOCAL_EMBEDDING_MODEL", "false")

    def fail_if_called(*args, **kwargs):
        raise AssertionError("semantic embedder should not load for default lexical retrieval")

    monkeypatch.setattr("src.retriever._cached_embedder", fail_if_called)

    results = retrieve_topk("What is drum and bass?", k=3)

    assert len(results) == 3
    assert any("drum and bass" in result.text.lower() for result in results)
