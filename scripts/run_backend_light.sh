#!/usr/bin/env bash
set -euo pipefail

# Run the backend in the same lightweight mode expected on the 2 GB Render service.
cd "$(dirname "$0")/.."

if [[ -f ".env.local.light" ]]; then
  set -a
  source ".env.local.light"
  set +a
elif [[ -f ".env" ]]; then
  set -a
  source ".env"
  set +a
fi

export APP_ENV="${APP_ENV:-development}"
export SONICMIND_MODE="${SONICMIND_MODE:-production_light}"
export SONICMIND_RETRIEVAL_BACKEND="${SONICMIND_RETRIEVAL_BACKEND:-lexical}"
export ENABLE_LOCAL_EMBEDDING_MODEL="${ENABLE_LOCAL_EMBEDDING_MODEL:-false}"
export ENABLE_RERANKER="${ENABLE_RERANKER:-false}"
export RAG_LOAD_ON_STARTUP="${RAG_LOAD_ON_STARTUP:-false}"
export RAG_FALLBACK_MODE="${RAG_FALLBACK_MODE:-keyword}"
export RAG_TOP_K="${RAG_TOP_K:-3}"
export RAG_CANDIDATE_K="${RAG_CANDIDATE_K:-12}"
export MAX_CONTEXT_CHARS="${MAX_CONTEXT_CHARS:-6000}"
export MAX_SOURCE_CHARS="${MAX_SOURCE_CHARS:-2000}"
export WEB_CONCURRENCY="${WEB_CONCURRENCY:-1}"
export MALLOC_ARENA_MAX="${MALLOC_ARENA_MAX:-2}"
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"
export OPENBLAS_NUM_THREADS="${OPENBLAS_NUM_THREADS:-1}"
export MKL_NUM_THREADS="${MKL_NUM_THREADS:-1}"
export NUMEXPR_NUM_THREADS="${NUMEXPR_NUM_THREADS:-1}"
export TOKENIZERS_PARALLELISM="${TOKENIZERS_PARALLELISM:-false}"
export PYTHONUNBUFFERED="${PYTHONUNBUFFERED:-1}"

exec python -m uvicorn backend.main:app --host 0.0.0.0 --port "${PORT:-8000}" --workers 1
