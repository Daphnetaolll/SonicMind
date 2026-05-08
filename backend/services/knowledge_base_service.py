from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Protocol

from src.settings import (
    CHUNKS_PATH,
    INDEX_PATH,
    META_PATH,
    get_retrieval_backend,
    heavy_dependencies_available,
    lexical_artifacts_available,
    semantic_artifacts_available,
    semantic_retrieval_ready as settings_semantic_retrieval_ready,
)

ROOT_DIR = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT_DIR / "data" / "raw"


class UploadedTextFile(Protocol):
    """Minimal file-upload shape needed by the service, independent of Streamlit."""

    name: str

    def getbuffer(self) -> bytes:
        ...


def save_uploaded_files(uploaded_files: list[UploadedTextFile]) -> list[Path]:
    """
    Store admin-uploaded source docs outside UI code so a future FastAPI upload
    endpoint can reuse the same extension checks and target directory.
    """
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    saved_paths: list[Path] = []

    for uploaded in uploaded_files:
        suffix = Path(uploaded.name).suffix.lower()
        if suffix not in {".txt", ".md"}:
            raise ValueError(f"Unsupported file type: {uploaded.name}. Only .txt and .md are allowed.")

        target = RAW_DIR / Path(uploaded.name).name
        target.write_bytes(uploaded.getbuffer())
        saved_paths.append(target)

    return saved_paths


def rebuild_knowledge_base() -> None:
    """
    Reuse the existing corpus build scripts instead of duplicating indexing logic.
    The command list stays here because rebuilding the FAISS index is backend work,
    not presentation logic.
    """
    commands = [
        [sys.executable, "scripts/preprocess.py"],
        [sys.executable, "scripts/embed_corpus.py"],
        [sys.executable, "scripts/build_index.py"],
    ]

    for cmd in commands:
        result = subprocess.run(
            cmd,
            cwd=ROOT_DIR,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Command failed: {' '.join(cmd)}\n"
                f"stdout:\n{result.stdout}\n"
                f"stderr:\n{result.stderr}"
            )

    # The running app may have cached the old FAISS index and metadata; clear it after a successful rebuild.
    from src.retriever import clear_retrieval_cache

    clear_retrieval_cache()


def knowledge_base_ready() -> bool:
    """Return whether the active retrieval backend has the generated artifacts it needs."""
    backend = get_retrieval_backend()
    if backend == "faiss":
        return semantic_artifacts_available()
    return lexical_artifacts_available()


def semantic_retrieval_ready() -> bool:
    """Return whether FAISS mode has both files and optional heavy packages available."""
    return settings_semantic_retrieval_ready()


def knowledge_base_diagnostics() -> dict[str, object]:
    # Health diagnostics describe readiness without importing semantic libraries or exposing secrets.
    dependencies = heavy_dependencies_available()
    return {
        "knowledge_base_ready": knowledge_base_ready(),
        "semantic_retrieval_ready": semantic_retrieval_ready(),
        "heavy_dependencies_available": {
            "faiss": dependencies["faiss"],
            "sentence_transformers": dependencies["sentence_transformers"],
            "torch": dependencies["torch"],
            "transformers": dependencies["transformers"],
        },
    }


def count_local_source_docs() -> int:
    """Count local source documents that can feed the knowledge-base rebuild."""
    if not RAW_DIR.exists():
        return 0
    return len(list(RAW_DIR.glob("*.txt"))) + len(list(RAW_DIR.glob("*.md")))
