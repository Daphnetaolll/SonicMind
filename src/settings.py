from __future__ import annotations

import importlib.util
import os
import warnings
from dataclasses import dataclass
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
CHUNKS_PATH = ROOT_DIR / "data" / "processed" / "chunks.jsonl"
META_PATH = ROOT_DIR / "data" / "processed" / "chunk_meta.jsonl"
INDEX_PATH = ROOT_DIR / "data" / "index" / "faiss.index"

VALID_APP_ENVS = {"production", "development", "test"}
VALID_MODES = {"production_light", "local_semantic", "semantic_production", "auto"}
VALID_BACKENDS = {"lexical", "faiss", "semantic", "auto"}
VALID_FALLBACK_MODES = {"keyword", "llm_only", "error"}


@dataclass(frozen=True)
class RuntimeSettings:
    # RuntimeSettings is the single source of truth for retrieval and memory-sensitive defaults.
    app_env: str
    sonicmind_mode: str
    retrieval_backend: str
    fallback_mode: str
    local_embedding_enabled: bool
    reranker_enabled: bool
    rag_load_on_startup: bool
    rag_top_k: int
    rag_candidate_k: int
    max_context_chars: int
    max_source_chars: int


def _warn(message: str) -> None:
    # Warnings are visible during startup and tests without exposing any environment values.
    warnings.warn(f"SonicMind runtime config: {message}", RuntimeWarning, stacklevel=3)


def _env_value(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    stripped = value.strip()
    return stripped if stripped else None


def _normalized_choice(name: str, default: str, valid: set[str]) -> str:
    value = (_env_value(name) or default).lower()
    if value not in valid:
        _warn(f"invalid {name}={value!r}; using {default!r}.")
        return default
    return value


def _env_bool(name: str, default: bool) -> bool:
    value = _env_value(name)
    if value is None:
        return default
    lowered = value.lower()
    if lowered in {"1", "true", "yes", "on"}:
        return True
    if lowered in {"0", "false", "no", "off"}:
        return False
    _warn(f"invalid boolean for {name}; using {default}.")
    return default


def _env_int(name: str, default: int, *, minimum: int = 1) -> int:
    value = _env_value(name)
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError:
        _warn(f"invalid integer for {name}; using {default}.")
        return default
    if parsed < minimum:
        _warn(f"{name} must be >= {minimum}; using {default}.")
        return default
    return parsed


def _module_available(module_name: str) -> bool:
    # importlib metadata checks availability without importing heavy ML modules into the process.
    try:
        return importlib.util.find_spec(module_name) is not None
    except (ImportError, ValueError):
        return False


def heavy_dependencies_available() -> dict[str, bool]:
    # Health reports dependency availability without loading torch, transformers, FAISS, or models.
    return {
        "faiss": _module_available("faiss"),
        "sentence_transformers": _module_available("sentence_transformers"),
        "torch": _module_available("torch"),
        "transformers": _module_available("transformers"),
    }


def semantic_artifacts_available() -> bool:
    # Semantic retrieval needs all generated corpus artifacts plus the FAISS index.
    return CHUNKS_PATH.exists() and META_PATH.exists() and INDEX_PATH.exists()


def lexical_artifacts_available() -> bool:
    # Lexical retrieval only needs the processed text and metadata JSONL files.
    return CHUNKS_PATH.exists() and META_PATH.exists()


def semantic_dependencies_available() -> bool:
    dependencies = heavy_dependencies_available()
    return all(dependencies[name] for name in ("faiss", "sentence_transformers", "torch", "transformers"))


def _mode_defaults(mode: str, app_env: str) -> dict[str, int | bool | str]:
    if mode in {"local_semantic", "semantic_production"}:
        return {
            "retrieval_backend": "faiss",
            "fallback_mode": "error",
            "local_embedding_enabled": True,
            "reranker_enabled": True,
            "rag_load_on_startup": False,
            "rag_top_k": 5,
            "rag_candidate_k": 25,
            "max_context_chars": 12000,
            "max_source_chars": 4000,
        }

    if mode == "auto" and app_env != "production" and semantic_artifacts_available() and semantic_dependencies_available():
        return {
            "retrieval_backend": "faiss",
            "fallback_mode": "error",
            "local_embedding_enabled": True,
            "reranker_enabled": True,
            "rag_load_on_startup": False,
            "rag_top_k": 5,
            "rag_candidate_k": 25,
            "max_context_chars": 12000,
            "max_source_chars": 4000,
        }

    return {
        "retrieval_backend": "lexical",
        "fallback_mode": "keyword",
        "local_embedding_enabled": False,
        "reranker_enabled": False,
        "rag_load_on_startup": False,
        "rag_top_k": 3,
        "rag_candidate_k": 12,
        "max_context_chars": 6000,
        "max_source_chars": 2000,
    }


def resolve_runtime_settings() -> RuntimeSettings:
    # Explicit environment variables always override mode defaults; missing values stay production-safe.
    app_env = _normalized_choice("APP_ENV", "development", VALID_APP_ENVS)
    mode = _normalized_choice("SONICMIND_MODE", "production_light", VALID_MODES)
    defaults = _mode_defaults(mode, app_env)

    backend = _normalized_choice(
        "SONICMIND_RETRIEVAL_BACKEND",
        str(defaults["retrieval_backend"]),
        VALID_BACKENDS,
    )
    if backend == "semantic":
        backend = "faiss"

    fallback_mode = _normalized_choice("RAG_FALLBACK_MODE", str(defaults["fallback_mode"]), VALID_FALLBACK_MODES)
    local_embedding_enabled = _env_bool(
        "ENABLE_LOCAL_EMBEDDING_MODEL",
        bool(defaults["local_embedding_enabled"]),
    )
    reranker_enabled = _env_bool("ENABLE_RERANKER", bool(defaults["reranker_enabled"]))
    rag_load_on_startup = _env_bool("RAG_LOAD_ON_STARTUP", bool(defaults["rag_load_on_startup"]))

    if backend == "auto":
        can_use_semantic = (
            app_env != "production"
            and local_embedding_enabled
            and semantic_artifacts_available()
            and semantic_dependencies_available()
        )
        backend = "faiss" if can_use_semantic else "lexical"

    return RuntimeSettings(
        app_env=app_env,
        sonicmind_mode=mode,
        retrieval_backend=backend,
        fallback_mode=fallback_mode,
        local_embedding_enabled=local_embedding_enabled,
        reranker_enabled=reranker_enabled,
        rag_load_on_startup=rag_load_on_startup,
        rag_top_k=_env_int("RAG_TOP_K", int(defaults["rag_top_k"])),
        rag_candidate_k=_env_int("RAG_CANDIDATE_K", int(defaults["rag_candidate_k"])),
        max_context_chars=_env_int("MAX_CONTEXT_CHARS", int(defaults["max_context_chars"]), minimum=400),
        max_source_chars=_env_int("MAX_SOURCE_CHARS", int(defaults["max_source_chars"]), minimum=400),
    )


def get_retrieval_backend() -> str:
    return resolve_runtime_settings().retrieval_backend


def get_fallback_mode() -> str:
    return resolve_runtime_settings().fallback_mode


def is_local_embedding_enabled() -> bool:
    return resolve_runtime_settings().local_embedding_enabled


def is_reranker_enabled() -> bool:
    return resolve_runtime_settings().reranker_enabled


def is_production_light_mode() -> bool:
    return resolve_runtime_settings().sonicmind_mode == "production_light"


def is_local_semantic_mode() -> bool:
    return resolve_runtime_settings().sonicmind_mode in {"local_semantic", "semantic_production"}


def semantic_retrieval_ready() -> bool:
    # Readiness combines config, files, and dependency availability without importing heavy modules.
    settings = resolve_runtime_settings()
    return settings.local_embedding_enabled and semantic_artifacts_available() and semantic_dependencies_available()


def mode_log_fields() -> dict[str, str | bool | int]:
    settings = resolve_runtime_settings()
    return {
        "sonicmind_mode": settings.sonicmind_mode,
        "retrieval_backend": settings.retrieval_backend,
        "local_embedding": settings.local_embedding_enabled,
        "reranker": settings.reranker_enabled,
        "fallback": settings.fallback_mode,
        "top_k": settings.rag_top_k,
        "candidate_k": settings.rag_candidate_k,
    }


def log_runtime_mode() -> None:
    # Mode logs intentionally include only non-secret runtime labels and limits.
    fields = " ".join(f"{key}={value}" for key, value in mode_log_fields().items())
    print(f"[MODE] {fields}", flush=True)
