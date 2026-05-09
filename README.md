# SonicMind

SonicMind is a deployed music knowledge and discovery assistant. It combines a Vite + React frontend, a FastAPI backend, PostgreSQL-backed accounts and quota, a music RAG pipeline, trusted-source retrieval, optional Spotify display cards, and Stripe subscription billing.

The legacy Streamlit app remains in [app.py](app.py) for comparison, but the primary application is now the React + FastAPI deployment.

## Deployed URLs

- Frontend: [https://sonicmind.onrender.com](https://sonicmind.onrender.com)
- Backend API: [https://sonicmind-api.onrender.com](https://sonicmind-api.onrender.com)
- Backend health: [https://sonicmind-api.onrender.com/api/health](https://sonicmind-api.onrender.com/api/health)

Production runs in lightweight retrieval mode by default so the backend can remain stable on a 2 GB Render web service.

## Project Structure

```text
frontend/             Vite + React app, routes, components, API client, Playwright smoke test
backend/              FastAPI app, API schemas, backend-facing service wrappers
src/                  RAG, retrieval, auth, quota, Spotify, music routing, repositories
data/                 Raw docs, processed chunks, metadata, and optional FAISS index
scripts/              Database, knowledge-base, runtime, seed, and memory-probe scripts
tests/                Pytest coverage for API, billing, runtime modes, retrieval, and music logic
docs/                 Deployment notes, billing docs, dev logs, QA reports, code documentation
```

## Current Architecture

```text
React frontend
  -> FastAPI backend
    -> PostgreSQL auth, quota, subscriptions, history, favorites
    -> RAG pipeline and music intent routing
    -> trusted music source search and optional Tavily/Brave web search
    -> optional Spotify Web API cards
    -> Stripe Checkout, Customer Portal, webhooks, and Creator -> Pro upgrades
```

The frontend only receives browser-safe values. Secrets such as database URLs, LLM keys, Stripe keys, Spotify secrets, Tavily keys, Discogs tokens, and backend signing secrets stay on the backend.

## Runtime Modes

SonicMind has two explicit retrieval/runtime profiles.

### Production Lightweight Mode

Use this mode for the current Render deployment.

```text
APP_ENV=production
SONICMIND_MODE=production_light
SONICMIND_RETRIEVAL_BACKEND=lexical
ENABLE_LOCAL_EMBEDDING_MODEL=false
ENABLE_RERANKER=false
RAG_LOAD_ON_STARTUP=false
```

This mode installs [requirements-production.txt](requirements-production.txt), excludes FAISS/torch/transformers/sentence-transformers, and uses lightweight lexical retrieval over the processed JSONL knowledge base. It is the safest option for Render's 2 GB backend.

### Local Semantic Mode

Use this mode for local high-quality semantic retrieval or a future 4 GB/8 GB backend.

```text
APP_ENV=development
SONICMIND_MODE=local_semantic
SONICMIND_RETRIEVAL_BACKEND=faiss
ENABLE_LOCAL_EMBEDDING_MODEL=true
ENABLE_RERANKER=true
```

This mode installs [requirements.txt](requirements.txt), can load FAISS and `BAAI/bge-m3`, and requires matching files under `data/index/` and `data/processed/`.

## Requirements

Core local development requires:

- Python 3.12
- Node.js/npm for the frontend
- PostgreSQL through `DATABASE_URL`
- At least one backend-only LLM key: `LLM_API_KEY` or `OPENAI_API_KEY`
- `BACKEND_SECRET_KEY` for deployed auth tokens

Optional integrations:

- `TAVILY_API_KEY` or `BRAVE_SEARCH_API_KEY` for web retrieval
- `SPOTIFY_CLIENT_ID` and `SPOTIFY_CLIENT_SECRET` for Spotify cards
- `DISCOGS_USER_TOKEN` for richer metadata lookup
- Stripe backend env vars for live billing

## Local Setup

Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install dependencies.

For production-like lightweight local testing:

```bash
python3 -m pip install -r requirements-production.txt
```

For full semantic local mode:

```bash
python3 -m pip install -r requirements.txt
```

Create a private `.env` from [.env.example](.env.example), then initialize the database:

```bash
set -a
source .env
set +a
python3 scripts/init_db.py
```

Run the lightweight backend:

```bash
scripts/run_backend_light.sh
```

Run the semantic backend:

```bash
scripts/run_backend_semantic.sh
```

Run the React frontend:

```bash
cd frontend
npm install
npm run dev
```

Local default URLs:

- Frontend: `http://127.0.0.1:5173`
- Backend: `http://127.0.0.1:8000`

## FastAPI Endpoints

Public and auth endpoints:

- `GET /api/health`
- `GET /api/pricing`
- `POST /api/login`
- `POST /api/register`
- `GET /api/me`

Chat and account features:

- `POST /api/chat`
- `GET /api/history`
- `DELETE /api/history`
- `GET /api/favorites`
- `POST /api/favorites`
- `DELETE /api/favorites/{favorite_id}`

Billing:

- `POST /api/billing/checkout-session`
- `POST /api/billing/portal-session`
- `POST /api/billing/subscription-plan`
- `POST /api/billing/webhook`

The billing webhook is authenticated by Stripe signature verification, not by SonicMind bearer tokens.

## Frontend App

The React app includes:

- `/` landing page
- `/register`
- `/login`
- `/pricing`
- `/chat`

Frontend stack:

- Vite
- React
- React Router
- Axios
- TanStack Query
- Zustand
- React Bootstrap
- Playwright production smoke test

The frontend talks to the backend through:

```bash
VITE_API_BASE_URL=https://sonicmind-api.onrender.com
```

Do not put backend secrets in `VITE_*` variables.

## Pricing and Usage Model

SonicMind enforces quota on the backend. Frontend counters are display-only.

| Plan | Price | Limit | Answer Tokens | RAG Top-K | Spotify Limit | Saved History | Favorites |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Free | $0/month | 5 questions/day, reset at UTC midnight | 400 | 3 | 5 | No | No |
| Student / Creator | $4.99/month | 200 questions/month | 800 | 5 | 10 | Yes | Yes |
| Pro | $8.99/month | 1000 questions/month | 1200 | 8 | 15 | Yes | Yes |

Usage rules:

- Successful text answers cost 1 question.
- Failed backend/RAG/LLM responses do not deduct usage.
- If text answer generation succeeds but Spotify cards fail, usage is still deducted.
- Saved history, favorites, page refreshes, and account-status fetches do not deduct usage.
- Creator/Pro production access requires a current Stripe-backed subscription row.

Extra packs are displayed as planned products but are not purchasable yet.

## Stripe Billing

SonicMind currently supports:

- Stripe Checkout for first-time Creator/Pro subscription purchase.
- Stripe Customer Portal for payment methods, invoices, cancellation, and broad subscription management.
- Stripe webhooks as the source of truth for paid access.
- Direct in-app Creator -> Pro upgrades by replacing the existing Stripe subscription item price.

Required backend-only Stripe variables:

```text
STRIPE_SECRET_KEY=replace_me
STRIPE_WEBHOOK_SECRET=replace_me
STRIPE_CREATOR_PRICE_ID=price_...
STRIPE_PRO_PRICE_ID=price_...
FRONTEND_BASE_URL=https://sonicmind.onrender.com
SONICMIND_ENABLE_DEMO_BILLING_ROLLOVER=false
```

Stripe price ids must start with `price_`; product ids that start with `prod_` are not valid for checkout or plan changes.

Full billing documentation lives in [docs/STRIPE_BILLING.md](docs/STRIPE_BILLING.md).

## Knowledge Base and Retrieval

The repository includes:

- raw source files in `data/raw/`
- processed chunks in `data/processed/chunks.jsonl`
- processed metadata in `data/processed/chunk_meta.jsonl`
- a FAISS index in `data/index/faiss.index` for semantic mode

Rebuild the knowledge base:

```bash
python3 scripts/preprocess.py
python3 scripts/embed_corpus.py
python3 scripts/build_index.py
```

Hybrid retrieval order:

1. Local knowledge base.
2. Trusted music sources.
3. General web search through a configured provider.

Answer certainty is labeled as confident, partial, or uncertain so incomplete evidence is visible to users.

## Spotify Integration

Spotify is a display and listening layer, not the source of recommendation truth.

The intended flow is:

```text
RAG/trusted evidence decides entities
  -> recommendation planner ranks tracks/artists/albums
  -> Spotify resolves playable metadata/cards
```

If Spotify credentials are missing or Spotify rate-limits the backend, text answers still work and Spotify cards degrade gracefully.

## Seed Local Plan Test Users

Seed users are local/dev-only and disabled unless explicitly enabled:

```bash
set -a
source .env
set +a
SONICMIND_ENABLE_DEV_SEEDS=true python3 scripts/seed_plan_test_users.py
```

Default seed accounts:

- `freetest@example.com` on Free
- `creatortest@example.com` on Student / Creator
- `protest@example.com` on Pro

Default local seed password:

```text
Test123456!
```

Use `SONICMIND_DEV_SEED_PASSWORD` to override it.

## Testing and Verification

Backend tests:

```bash
.venv/bin/python -m pytest
```

Frontend build:

```bash
cd frontend
npm run build
```

Memory probe:

```bash
.venv/bin/python scripts/memory_probe.py --mode lexical
.venv/bin/python scripts/memory_probe.py --mode faiss
```

Production smoke test:

```bash
cd frontend
FRONTEND_URL=https://sonicmind.onrender.com \
BACKEND_URL=https://sonicmind-api.onrender.com \
EXPECTED_RETRIEVAL_BACKEND=lexical \
npm run test:prod
```

The smoke test covers health, registration, login, chat, console errors, failed network requests, and response shapes.

## Deployment

Render deployment docs:

- [docs/render_deployment.md](docs/render_deployment.md)
- [docs/public_beta_deployment.md](docs/public_beta_deployment.md)

Current production backend settings:

```bash
pip install -r requirements-production.txt
python scripts/init_db.py
python -m uvicorn backend.main:app --host 0.0.0.0 --port $PORT --workers 1
```

Current production frontend settings:

```bash
npm install
npm run build
```

Publish directory:

```text
dist
```

## Project Documentation

- [README Technical Rationale](README_TECHNICAL_RATIONALE.md)
- [Code Documentation](docs/CODE_DOCUMENTATION.md)
- [Code Documentation DOCX](docs/SonicMind_Code_Documentation.docx)
- [Stripe Billing](docs/STRIPE_BILLING.md)
- [Render Deployment](docs/render_deployment.md)
- [Pricing and Usage Plan](docs/PRICING_AND_USAGE_PLAN.md)
- [Music Recommendation Flow](docs/music_recommendation_flow.md)
- [QA Debug Report](docs/QA_DEBUG_REPORT.md)
- [Autonomous QA Polish Report](docs/AUTONOMOUS_QA_POLISH_REPORT.md)

## Development Log

I keep a daily development log to document design decisions, implementation progress, debugging process, and next steps.

- [2026-04-27](docs/devlog/2026-04-27.md)
- [2026-05-04](docs/devlog/2026-05-04.md)
- [2026-05-05](docs/devlog/2026-05-05.md)
- [2026-05-06](docs/devlog/2026-05-06.md)
- [2026-05-09](docs/devlog/2026-05-09.md)

## Migration Status

- Phase 1: Streamlit UI logic was separated from reusable backend services.
- Phase 2: FastAPI endpoints were added for health, auth, and chat.
- Phase 3: Vite + React frontend was added with login, register, pricing, and chat pages.
- Phase 4: Production deployment was moved to Render with separate frontend/backend services.
- Phase 5: Runtime modes were split into production lightweight and local semantic retrieval.
- Phase 6: Stripe billing was added for Creator/Pro subscriptions, including direct Creator -> Pro upgrade support.

## Known Limitations

- Production lexical retrieval is stable on 2 GB but less semantically rich than local FAISS mode.
- High-quality semantic retrieval on Render likely needs a 4 GB or 8 GB backend instance or hosted vector search.
- External recommendation quality depends on configured Tavily/Brave, Spotify, and Discogs credentials.
- Stripe extra-pack purchases are not implemented yet.
- Direct plan changes currently support Creator -> Pro upgrades; downgrades remain in Stripe Customer Portal.
- If Stripe requires extra payment authentication during an upgrade, the user may need to complete billing action through Stripe.
- The auth token is a lightweight backend-signed token suitable for this prototype stage; production hardening should use a stronger session/JWT strategy and a long non-default `BACKEND_SECRET_KEY`.

## Safety Notes

- `.env` is intentionally ignored by Git.
- `.env.example` and `.env.production.example` contain placeholders only.
- Do not commit API keys, database URLs, Stripe secrets, Spotify secrets, Tavily keys, Discogs tokens, or backend signing secrets.
- If the app starts but cannot answer questions, first check backend health, LLM key configuration, database connection, and retrieval mode.
