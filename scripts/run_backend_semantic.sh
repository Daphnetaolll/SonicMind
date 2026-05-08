#!/usr/bin/env bash
set -euo pipefail

# Run the backend in high-memory semantic mode for local testing or future larger instances.
cd "$(dirname "$0")/.."

if [[ -f ".env.local.semantic" ]]; then
  set -a
  source ".env.local.semantic"
  set +a
elif [[ -f ".env" ]]; then
  set -a
  source ".env"
  set +a
fi

export APP_ENV="${APP_ENV:-development}"
export SONICMIND_MODE="${SONICMIND_MODE:-local_semantic}"
export SONICMIND_RETRIEVAL_BACKEND="${SONICMIND_RETRIEVAL_BACKEND:-faiss}"
export ENABLE_LOCAL_EMBEDDING_MODEL="${ENABLE_LOCAL_EMBEDDING_MODEL:-true}"
export ENABLE_RERANKER="${ENABLE_RERANKER:-true}"
export RAG_LOAD_ON_STARTUP="${RAG_LOAD_ON_STARTUP:-false}"
export RAG_FALLBACK_MODE="${RAG_FALLBACK_MODE:-error}"
export RAG_TOP_K="${RAG_TOP_K:-5}"
export RAG_CANDIDATE_K="${RAG_CANDIDATE_K:-25}"
export MAX_CONTEXT_CHARS="${MAX_CONTEXT_CHARS:-12000}"
export MAX_SOURCE_CHARS="${MAX_SOURCE_CHARS:-4000}"
export WEB_CONCURRENCY="${WEB_CONCURRENCY:-1}"
export MALLOC_ARENA_MAX="${MALLOC_ARENA_MAX:-2}"
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"
export OPENBLAS_NUM_THREADS="${OPENBLAS_NUM_THREADS:-1}"
export MKL_NUM_THREADS="${MKL_NUM_THREADS:-1}"
export NUMEXPR_NUM_THREADS="${NUMEXPR_NUM_THREADS:-1}"
export TOKENIZERS_PARALLELISM="${TOKENIZERS_PARALLELISM:-false}"
export PYTHONUNBUFFERED="${PYTHONUNBUFFERED:-1}"

exec python -m uvicorn backend.main:app --host 0.0.0.0 --port "${PORT:-8000}" --workers 1
