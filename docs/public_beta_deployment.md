# Public Beta Deployment Guide

This guide describes the current safe public-beta deployment for SonicMind.

## Current Beta Stack

- Frontend hosting: Render Static Site
- Backend hosting: Render Python Web Service
- Database: Render PostgreSQL or another PostgreSQL database
- Repository: GitHub
- Secrets: Render environment variables, not `.env`

Current deployed URLs:

- Frontend: `https://sonicmind.onrender.com`
- Backend API: `https://sonicmind-api.onrender.com`
- Health endpoint: `https://sonicmind-api.onrender.com/api/health`

The older Streamlit entrypoint in `app.py` remains available for comparison, but it is not the primary deployed beta app.

## What Must Be Deployed

Backend:

- `backend/`
- `src/`
- `scripts/init_db.py`
- `requirements-production.txt`
- `runtime.txt`
- `data/processed/chunks.jsonl`
- `data/processed/chunk_meta.jsonl`

Frontend:

- `frontend/`
- `frontend/package.json`
- `frontend/package-lock.json`
- `frontend/src/`

Semantic local mode additionally uses:

- `data/index/faiss.index`
- full `requirements.txt`

Production lightweight mode does not require FAISS, torch, transformers, or sentence-transformers.

## Required Cloud Secrets

Set these in the backend service. Do not commit them to GitHub.

```text
DATABASE_URL=postgresql://...
BACKEND_SECRET_KEY=...
LLM_API_KEY=...
OPENAI_API_KEY=...
WEB_SEARCH_PROVIDER=tavily
TAVILY_API_KEY=...
SPOTIFY_CLIENT_ID=...
SPOTIFY_CLIENT_SECRET=...
STRIPE_SECRET_KEY=...
STRIPE_WEBHOOK_SECRET=...
STRIPE_CREATOR_PRICE_ID=price_...
STRIPE_PRO_PRICE_ID=price_...
FRONTEND_BASE_URL=https://sonicmind.onrender.com
BACKEND_CORS_ORIGINS=https://sonicmind.onrender.com
```

Optional:

```text
LLM_TIMEOUT=60
LLM_TEMPERATURE=0.2
TAVILY_SEARCH_DEPTH=basic
TAVILY_TOPIC=general
TAVILY_INCLUDE_RAW_CONTENT=false
WEB_FETCH_RESULT_PAGES=false
EXTERNAL_FETCH_TIMEOUT=12
MUSIC_METADATA_USER_AGENT=sonicmind/0.1 (your-contact@example.com)
DISCOGS_USER_TOKEN=
```

Frontend Static Site should only need:

```text
VITE_API_BASE_URL=https://sonicmind-api.onrender.com
```

## Production Runtime Mode

Keep the backend in lightweight mode on the 2 GB Render service:

```text
APP_ENV=production
SONICMIND_MODE=production_light
SONICMIND_RETRIEVAL_BACKEND=lexical
ENABLE_LOCAL_EMBEDDING_MODEL=false
ENABLE_RERANKER=false
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
```

## Deployment Steps

1. Push the latest repo to GitHub.
2. Create or connect a PostgreSQL database.
3. Configure the backend Render Web Service:

```bash
pip install -r requirements-production.txt
python scripts/init_db.py
python -m uvicorn backend.main:app --host 0.0.0.0 --port $PORT --workers 1
```

4. Configure the frontend Render Static Site:

```bash
npm install
npm run build
```

Publish directory:

```text
dist
```

5. Add backend environment variables in Render.
6. Add `VITE_API_BASE_URL` in the frontend service.
7. Configure Stripe webhook endpoint:

```text
https://sonicmind-api.onrender.com/api/billing/webhook
```

8. Redeploy backend and frontend.

## Public Beta Safeguards

- Keep account login enabled.
- Keep backend quota enforcement enabled.
- Keep the free plan limited to 5 questions per day.
- Keep production semantic retrieval disabled on the 2 GB service.
- Keep Stripe secrets backend-only.
- Keep real `.env` files out of Git.
- Use disposable accounts for QA.

## Smoke Test After Deployment

Run the automated production smoke test:

```bash
cd frontend
FRONTEND_URL=https://sonicmind.onrender.com \
BACKEND_URL=https://sonicmind-api.onrender.com \
EXPECTED_RETRIEVAL_BACKEND=lexical \
npm run test:prod
```

Manual prompts to verify:

```text
What is drum and bass?
Who is John Summit?
Recommend recent popular dance music.
Tell me about Afterlife.
```

Check:

- The app loads without dependency errors.
- Registration and login work.
- Free quota decreases only after successful answers.
- `/api/health` reports `retrieval_backend=lexical` and `knowledge_base_ready=true`.
- Answer text and Spotify cards refer to the same music candidates when cards are shown.
- Sources and uncertainty notes display cleanly.
- Pricing shows Free, Creator, and Pro.
- Existing Creator users can upgrade to Pro through the Pro card.

## Known Beta Limitations

- Production lightweight retrieval is stable but less semantically rich than local FAISS mode.
- Current/recent music questions depend on external search quality and source extraction.
- Spotify cards require backend Spotify credentials and can be affected by rate limits.
- Extra-pack purchases are planned but not implemented.
- Billing-specific browser automation should be expanded with Stripe test-mode flows.
