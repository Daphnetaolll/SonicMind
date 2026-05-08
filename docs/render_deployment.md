# Render Deployment Guide

This guide prepares SonicMind for a Render deployment with:

- Render Postgres
- Render Web Service for the FastAPI backend
- Render Static Site for the Vite React frontend

No real secrets belong in this repo. Add real values only in the Render dashboard.

## Readiness Checklist

Required files found:

- `requirements.txt`
- `requirements-production.txt`
- `runtime.txt`
- `.python-version`
- `backend/main.py`
- `frontend/package.json`
- `scripts/init_db.py`
- `src/`
- `data/index/faiss.index`
- `data/processed/chunks.jsonl`
- `data/processed/chunk_meta.jsonl`

Required runtime data is tracked by Git:

```bash
git ls-files data/index/faiss.index
git ls-files data/processed/chunks.jsonl
git ls-files data/processed/chunk_meta.jsonl
```

Each command returned the expected path.

`.gitignore` ignores generated/cached files but explicitly keeps the runtime FAISS index:

```gitignore
data/index/*
!data/index/faiss.index
data/processed/embeddings.npy
```

`chunks.jsonl` and `chunk_meta.jsonl` are not ignored.

## Two SonicMind Runtime Modes

SonicMind has two explicit backend runtime profiles. Use the lightweight profile
for the current 2 GB Render service, and reserve semantic FAISS mode for local
testing or a future larger backend instance.

### A. Render 2 GB production lightweight mode

Backend Build Command:

```bash
pip install -r requirements-production.txt
```

Backend Start Command:

```bash
python -m uvicorn backend.main:app --host 0.0.0.0 --port $PORT --workers 1
```

Backend environment variables:

```text
APP_ENV=production
SONICMIND_MODE=production_light
SONICMIND_RETRIEVAL_BACKEND=lexical
ENABLE_LOCAL_EMBEDDING_MODEL=false
ENABLE_RERANKER=false
RAG_LOAD_ON_STARTUP=false
RAG_TOP_K=3
RAG_CANDIDATE_K=12
MAX_CONTEXT_CHARS=6000
MAX_SOURCE_CHARS=2000
RAG_FALLBACK_MODE=keyword
WEB_CONCURRENCY=1
MALLOC_ARENA_MAX=2
OMP_NUM_THREADS=1
OPENBLAS_NUM_THREADS=1
MKL_NUM_THREADS=1
NUMEXPR_NUM_THREADS=1
TOKENIZERS_PARALLELISM=false
PYTHONUNBUFFERED=1
```

This mode installs no FAISS, torch, transformers, or sentence-transformers
packages. The active knowledge-base readiness check requires only:

- `data/processed/chunks.jsonl`
- `data/processed/chunk_meta.jsonl`

### B. Local semantic mode

Install:

```bash
pip install -r requirements.txt
```

Run:

```bash
cp .env.local.semantic.example .env.local.semantic
scripts/run_backend_semantic.sh
```

This mode uses FAISS plus the local `BAAI/bge-m3` sentence-transformer path.
It requires:

- `data/index/faiss.index`
- `data/processed/chunks.jsonl`
- `data/processed/chunk_meta.jsonl`

### C. Local lightweight mode

Install:

```bash
pip install -r requirements-production.txt
```

Run:

```bash
cp .env.local.light.example .env.local.light
scripts/run_backend_light.sh
```

This gives production-like behavior locally without heavy semantic packages.

### Memory probes

Run the lightweight probe before deploying to the 2 GB service:

```bash
python scripts/memory_probe.py --mode lexical
```

Run the semantic probe only where FAISS files and semantic dependencies are
available:

```bash
python scripts/memory_probe.py --mode faiss
```

### D. Future high-memory Render semantic mode

Do not enable this on the 2 GB backend unless memory probes pass. For a future
4 GB or 8 GB backend instance:

```text
SONICMIND_MODE=semantic_production
SONICMIND_RETRIEVAL_BACKEND=faiss
ENABLE_LOCAL_EMBEDDING_MODEL=true
ENABLE_RERANKER=true
```

For local-only testing, `SONICMIND_MODE=local_semantic` uses the same FAISS
defaults without implying a production deployment.

Use `requirements.txt` for the build if the larger service should run semantic
retrieval. The FAISS index must be built with the same embedding model used for
query embeddings; changing embedding providers requires rebuilding
`data/index/faiss.index`.

`render.yaml` documents the intended settings, but existing manually-created
Render services do not automatically adopt every Blueprint change. Check the
Render dashboard and set Build Command, Start Command, and environment variables
there as the source of truth.

## Backend Service

Create a Render Web Service from the repository root.

Recommended settings:

- Runtime: `Python`
- Build Command: `pip install -r requirements-production.txt`
- Pre-Deploy Command: `python scripts/init_db.py`
- Start Command: `python -m uvicorn backend.main:app --host 0.0.0.0 --port $PORT --workers 1`

Environment variables:

```text
DATABASE_URL=<Render Postgres internal database URL>
BACKEND_SECRET_KEY=<long random value>
LLM_API_KEY=<your backend-only LLM key>
OPENAI_API_KEY=<optional backend-only OpenAI key>
BACKEND_CORS_ORIGINS=https://<your-render-static-site>.onrender.com
WEB_SEARCH_PROVIDER=tavily
APP_ENV=production
SONICMIND_MODE=production_light
SONICMIND_RETRIEVAL_BACKEND=lexical
SONICMIND_MEMORY_LOGS=true
RAG_TOP_K=3
RAG_CANDIDATE_K=12
MAX_CONTEXT_CHARS=6000
MAX_SOURCE_CHARS=2000
ENABLE_RERANKER=false
ENABLE_LOCAL_EMBEDDING_MODEL=false
RAG_LOAD_ON_STARTUP=false
RAG_FALLBACK_MODE=keyword
WEB_CONCURRENCY=1
MALLOC_ARENA_MAX=2
OMP_NUM_THREADS=1
OPENBLAS_NUM_THREADS=1
MKL_NUM_THREADS=1
NUMEXPR_NUM_THREADS=1
TOKENIZERS_PARALLELISM=false
PYTHONUNBUFFERED=1
TAVILY_API_KEY=<optional backend-only Tavily key>
SPOTIFY_CLIENT_ID=<optional backend-only Spotify client id>
SPOTIFY_CLIENT_SECRET=<optional backend-only Spotify client secret>
DISCOGS_USER_TOKEN=<optional backend-only Discogs token>
```

Do not add these values to React `VITE_*` variables.

Health check:

```bash
curl https://<your-backend>.onrender.com/api/health
```

Expected shape:

```json
{
  "status": "ok",
  "service": "sonicmind-api",
  "app_env": "production",
  "sonicmind_mode": "production_light",
  "retrieval_backend": "lexical",
  "knowledge_base_ready": true,
  "semantic_retrieval_ready": false,
  "local_embedding_enabled": false,
  "reranker_enabled": false,
  "rag_load_on_startup": false,
  "fallback_mode": "keyword",
  "heavy_dependencies_available": {
    "faiss": false,
    "sentence_transformers": false,
    "torch": false,
    "transformers": false
  }
}
```

If `knowledge_base_ready` is `false`, confirm these files are present in the deployed repo:

- `data/processed/chunks.jsonl`
- `data/processed/chunk_meta.jsonl`

In semantic mode, also confirm:

- `data/index/faiss.index`

## Database Initialization

`scripts/init_db.py` is safe to run during deployment because the schema uses:

- `CREATE TABLE IF NOT EXISTS`
- `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`
- `CREATE INDEX IF NOT EXISTS`
- repeatable constraint replacement for known local check constraints

The script no longer prints the raw `DATABASE_URL`, because Render logs should never expose database credentials.

## Frontend Static Site

Create a Render Static Site with root directory `frontend`.

Recommended settings:

- Build Command: `npm install && npm run build`
- Publish Directory: `dist`
- Rewrite rule: `/*` to `/index.html`

Environment variable:

```text
VITE_API_BASE_URL=https://<your-backend>.onrender.com
```

Only `VITE_API_BASE_URL` is needed in the frontend. Do not add API keys, database URLs, JWT secrets, Spotify secrets, Tavily keys, or Discogs tokens to the frontend.

## CORS

The backend reads `BACKEND_CORS_ORIGINS` as a comma-separated list:

```text
BACKEND_CORS_ORIGINS=https://frontend-url.onrender.com
```

For multiple frontend origins:

```text
BACKEND_CORS_ORIGINS=https://frontend-url.onrender.com,https://preview-url.onrender.com
```

For the current SonicMind Render deployment, the frontend origin is:

```text
BACKEND_CORS_ORIGINS=https://sonicmind.onrender.com
```

If registration or login shows Axios `Network Error`, verify the API service env var
uses the frontend origin only. Do not include paths such as `/register`, and restart
or redeploy the API after saving the env var.

## Production Retrieval Mode

The deployed API defaults to lightweight lexical retrieval for the small included
knowledge base. This avoids cold-loading large sentence-transformer models on
memory-constrained Render instances during user chat requests.

The backend Render service should install `requirements-production.txt`, not the
full local `requirements.txt`. Production lexical chat does not need Streamlit,
FAISS, torch, transformers, or sentence-transformers at runtime.

Keep these defaults for a 2 GB Render web service:

```text
SONICMIND_RETRIEVAL_BACKEND=lexical
ENABLE_LOCAL_EMBEDDING_MODEL=false
ENABLE_RERANKER=false
RAG_LOAD_ON_STARTUP=false
RAG_TOP_K=3
RAG_CANDIDATE_K=12
MAX_CONTEXT_CHARS=6000
MAX_SOURCE_CHARS=2000
```

Only set this if the service has enough memory and a warmed model cache:

```text
SONICMIND_RETRIEVAL_BACKEND=faiss
ENABLE_LOCAL_EMBEDDING_MODEL=true
```

Semantic FAISS retrieval uses the same embedding model that built the index.
Switching query embeddings to a different provider requires rebuilding
`data/index/faiss.index` with matching embedding dimensions.

Memory diagnostics are safe to leave on during debugging:

```text
SONICMIND_MEMORY_LOGS=true
```

Render logs will include entries like:

```text
[MEMORY] stage=before_chat_request rss_mb=...
[MEMORY] stage=before_faiss_load rss_mb=...
[MEMORY] stage=before_embedding_model_load rss_mb=...
[MEMORY] stage=before_llm_call rss_mb=...
```

If the instance still OOMs, paste only the memory log lines and Render OOM event
around one `/api/chat` request. Do not paste secret env vars.

## Optional Blueprint

This repo includes `render.yaml` with placeholders only. If you use Render Blueprints, update service names and URLs after creation:

- `sonicmind-api`
- `sonicmind-frontend`
- `sonicmind-postgres`

Blueprint secrets use `sync: false` or Render database references. Do not replace them with real secret values in Git.

## Local Verification Results

Commands run locally:

```bash
python -m pytest
.venv/bin/python -m pytest
.venv/bin/python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
curl -s http://127.0.0.1:8000/api/health
cd frontend && npm install
cd frontend && npm run build
```

Results:

- `python -m pytest`: failed locally because the global Miniforge Python does not have `pytest` installed.
- `.venv/bin/python -m pytest`: passed, `21 passed, 1 skipped`.
- `.venv/bin/python scripts/memory_probe.py --mode lexical`: passed, backend import and lexical retrieval held near `54 MB` RSS.
- `.venv/bin/python scripts/memory_probe.py --mode faiss`: entered semantic mode and loaded FAISS/model path, but the local process terminated after `BAAI/bge-m3` model load reached about `959 MB` RSS.
- `python -m uvicorn ...`: global Python does not have `uvicorn` installed.
- `.venv/bin/python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000`: started successfully.
- `/api/health`: returned `knowledge_base_ready: true`.
- `npm install`: completed with peer dependency warnings from optional WASM packages, no vulnerabilities.
- `npm run build`: passed.

On Render, `python -m pytest` and `python -m uvicorn` run in Render's installed Python environment after `pip install -r requirements.txt`, so they should have the required packages.

## Exact Render Commands

Backend:

```bash
pip install -r requirements-production.txt
python scripts/init_db.py
python -m uvicorn backend.main:app --host 0.0.0.0 --port $PORT --workers 1
```

Frontend:

```bash
npm install
npm run build
```

Frontend publish directory:

```text
dist
```

## Remaining Deployment Risks

- The FAISS index and processed JSONL files are tracked now; if they grow beyond Git/provider limits later, move them to object storage and download during build.
- The backend may need at least a Starter-sized instance because `sentence-transformers`, `torch`, and FAISS can be memory-heavy.
- Spotify, Tavily, and Discogs features degrade gracefully when credentials are missing, but recommendation quality improves when those backend-only credentials are configured.
- Payment/Stripe is intentionally not integrated yet.

## References

- Render Blueprint YAML Reference: https://render.com/docs/blueprint-spec
- Render Python Version Docs: https://render.com/docs/python-version
- Render Monorepo Support: https://render.com/docs/monorepo-support
