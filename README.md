# SonicMind

SonicMind is a music knowledge RAG web app built for portfolio / DALI Lab application review. The current app uses a React frontend, a FastAPI backend, and the original Python RAG pipeline with FAISS retrieval, embedding-based search, account/quota storage, and optional Spotify embeds.

The legacy Streamlit app is still available in [app.py](app.py) while the migration continues.

## Project structure

```text
frontend/             Vite + React app
backend/              FastAPI app and backend-facing service wrappers
src/                  Existing RAG, retrieval, auth, quota, Spotify, and music logic
data/                 Raw docs, processed chunks, embeddings, and FAISS index
scripts/              Database and knowledge-base utility scripts
tests/                Pytest coverage for API and music intent helpers
docs/                 Deployment notes, dev logs, and QA reports
```

## Requirements

Answering real questions requires:

- a valid `LLM_API_KEY` or `OPENAI_API_KEY`
- a valid PostgreSQL `DATABASE_URL`
- a ready knowledge base index under `data/index/faiss.index`
- optional Spotify credentials for playable recommendation embeds

## Local setup

1. Create and activate a virtual environment.

```bash
python3 -m venv .venv
source .venv/bin/activate
```

2. Install dependencies.

```bash
python3 -m pip install -r requirements.txt
```

3. Fill in local environment variables in `.env`.

- Required: `LLM_API_KEY` or `OPENAI_API_KEY`
- Required: `DATABASE_URL`
- Required for deployed auth tokens: `BACKEND_SECRET_KEY`
- Optional: `LLM_MODEL`, `LLM_BASE_URL`, `LLM_TIMEOUT`, `LLM_TEMPERATURE`
- Optional hybrid retrieval: `WEB_SEARCH_PROVIDER`, `TAVILY_API_KEY`, `TAVILY_SEARCH_DEPTH`, `TAVILY_TOPIC`, `TAVILY_INCLUDE_RAW_CONTENT`, `TAVILY_CHUNKS_PER_SOURCE`, `BRAVE_SEARCH_API_KEY`, `WEB_SEARCH_COUNTRY`, `WEB_SEARCH_LANG`, `WEB_SEARCH_SAFESEARCH`, `WEB_FETCH_RESULT_PAGES`, `EXTERNAL_FETCH_TIMEOUT`
- Optional metadata APIs: `MUSIC_METADATA_USER_AGENT`, `DISCOGS_USER_TOKEN`
- Optional Spotify: `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET`
- Optional dev seeds: `SONICMIND_ENABLE_DEV_SEEDS`, `SONICMIND_DEV_SEED_PASSWORD`
- Recommended on this machine: `SSL_CERT_FILE` pointing to your virtualenv's `certifi` bundle

For this machine, the local PostgreSQL database is set up to use:

```bash
DATABASE_URL=postgresql:///rag_agent_web
```

If Python reports SSL certificate verification failures when calling the LLM API, set:

```bash
SSL_CERT_FILE=/Users/miss.daphne/Documents/GitHub/rag-agent-web-public-mvp/.venv/lib/python3.13/site-packages/certifi/cacert.pem
```

4. Export the variables from `.env` into your shell.

```bash
set -a
source .env
set +a
```

5. Initialize the PostgreSQL schema.

```bash
python3 scripts/init_db.py
```

6. Start the legacy Streamlit app only if you need to compare behavior.

```bash
python3 -m streamlit run app.py
```

## FastAPI backend

Phase 2 adds a FastAPI backend that wraps the existing Python RAG, auth, quota, and Spotify services. Secrets stay in backend environment variables and are never exposed to the React frontend.

Run the API locally from the project root:

```bash
source .venv/bin/activate
python3 -m uvicorn backend.main:app --reload --port 8000
```

Available endpoints:

- `GET /api/health`
- `GET /api/pricing`
- `GET /api/me`
- `POST /api/login`
- `POST /api/register`
- `POST /api/chat`
- `GET /api/history`
- `DELETE /api/history`
- `GET /api/favorites`
- `POST /api/favorites`
- `DELETE /api/favorites/{favorite_id}`

Local React development is allowed through CORS for `http://localhost:5173` and `http://127.0.0.1:5173` by default. Override this with:

```bash
BACKEND_CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

FastAPI auth uses a backend-only signing secret:

```bash
BACKEND_SECRET_KEY=replace_with_a_long_random_backend_secret
```

Do not put `LLM_API_KEY`, `OPENAI_API_KEY`, `SPOTIFY_CLIENT_SECRET`, `DATABASE_URL`, or `BACKEND_SECRET_KEY` in React `VITE_*` variables.

Create a local test account by opening the React app and using `/register`, or call the API with clearly fake credentials:

```bash
curl -X POST http://127.0.0.1:8000/api/register \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"examplepass123","confirm_password":"examplepass123"}'
```

Run backend tests from the project root:

```bash
.venv/bin/python -m pytest
```

## Pricing and usage model

SonicMind now has a backend-enforced plan system. Stripe/payment is not integrated yet; upgrade and extra-pack buttons are placeholders.

| Plan | Price | Limit | Answer Tokens | RAG Top-K | Spotify Limit | Saved History | Favorites |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Free | $0/month | 5 questions/day, reset at UTC midnight | 400 | 3 | 5 | No | No |
| Student / Creator | $4.99/month | 200 questions/month | 800 | 5 | 10 | Yes | Yes |
| Pro | $8.99/month | 1000 questions/month | 1200 | 8 | 15 | Yes | Yes |

Extra packs are planned but not purchasable yet:

- `$2.99` for 50 extra questions
- `$4.99` for 100 extra questions
- Extra credits are used after plan quota and expire after 12 months

Usage deduction rules:

- A question costs 1 unit only after the backend successfully returns a text answer.
- Failed RAG/LLM/backend answers do not deduct usage.
- If the text answer succeeds but Spotify fails, usage is still deducted and the frontend shows a clean Spotify fallback.
- Refreshing the page, loading saved history, and viewing favorites do not deduct usage.
- Frontend counters are display-only; quota is enforced on the backend.

The full design is documented in [docs/PRICING_AND_USAGE_PLAN.md](docs/PRICING_AND_USAGE_PLAN.md).

## Seed local plan test users

Seed users are local/dev-only and are disabled unless you opt in:

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

## React frontend

Phase 3 adds a Vite + React frontend in `frontend/`. The frontend talks to FastAPI through one public browser variable:

```bash
VITE_API_BASE_URL=http://127.0.0.1:8000
```

Only use `VITE_*` variables for values that are safe in the browser. Keep `LLM_API_KEY`, `OPENAI_API_KEY`, `SPOTIFY_CLIENT_SECRET`, `DATABASE_URL`, and `BACKEND_SECRET_KEY` in the backend `.env`.

Install and run the frontend:

```bash
cd frontend
npm install
npm run dev
```

Build the frontend:

```bash
cd frontend
npm run build
```

The React app includes `/`, `/login`, `/register`, `/pricing`, and `/chat`. It uses React Router for pages, axios for API calls, TanStack Query for request state, zustand for auth/conversation state, and React Bootstrap for layout controls.

For local development, run FastAPI on `http://127.0.0.1:8000` and React on `http://127.0.0.1:5173`.

## Knowledge base status

This repo currently includes:

- raw source files in `data/raw/`
- processed chunk files in `data/processed/`

This repo currently includes `data/index/faiss.index`. If it is missing or stale, rebuild it with the commands below.

## Build the knowledge base

Run these commands from the project root:

```bash
python3 scripts/preprocess.py
python3 scripts/embed_corpus.py
python3 scripts/build_index.py
```

After that, start the app again with:

```bash
python3 -m uvicorn backend.main:app --reload --port 8000
```

## Hybrid retrieval flow

The app answers questions in this order:

- local knowledge base
- trusted music sources
- general web search through a formal search API

If evidence is still incomplete, the answer includes a lower certainty label and an uncertainty note.

Trusted music sources:

- MusicBrainz: song, artist, album, and release metadata through the official MusicBrainz API
- Discogs: release versions, labels, vinyl, and underground electronic music through the official Discogs API
- Every Noise at Once: music genre relationship map through API-backed site search
- Ishkur's Guide: electronic music genre explanations through API-backed site search
- Rate Your Music: album, genre, and community evaluation context through API-backed site search
- AllMusic: artist and album explanatory text through API-backed site search
- Spotify Web API: BPM, audio features, similar songs, and listening links when configured

General web search defaults to Tavily. Set `WEB_SEARCH_PROVIDER=tavily` and `TAVILY_API_KEY` to enable external search. Brave remains available as a fallback by setting `WEB_SEARCH_PROVIDER=brave` and `BRAVE_SEARCH_API_KEY`.

## Database schema

The MVP database uses PostgreSQL via `DATABASE_URL`. The initialization script creates these core tables:

- `users`
- `subscriptions`
- `question_logs`
- `usage_ledger`
- `credit_transactions`
- `chat_messages`
- `favorite_tracks`
- `admin_roles`
- `billing_events`

## Development Log

I keep a daily development log to document design decisions, implementation progress, debugging process, and next steps.

- [2026-04-27](docs/devlog/2026-04-27.md)
- [2026-05-04](docs/devlog/2026-05-04.md)
- [2026-05-05](docs/devlog/2026-05-05.md)
- [2026-05-06](docs/devlog/2026-05-06.md)

## Public Beta Deployment

Deployment notes are documented in [docs/public_beta_deployment.md](docs/public_beta_deployment.md).

## Migration status

- Phase 1: Streamlit UI logic was separated from reusable backend services.
- Phase 2: FastAPI endpoints were added for health, auth, and chat.
- Phase 3: Vite + React frontend was added with login, register, and chat pages.
- Phase 4: Portfolio polish and QA pass documented in [docs/QA_DEBUG_REPORT.md](docs/QA_DEBUG_REPORT.md).
- Autonomous QA polish sprint: 80-question test pass, Spotify rate-limit diagnosis, and UI cleanup are documented in [docs/AUTONOMOUS_QA_POLISH_REPORT.md](docs/AUTONOMOUS_QA_POLISH_REPORT.md).

## Known limitations

- Real chat requires a valid LLM key and Postgres database configuration.
- Spotify embeds require backend-only `SPOTIFY_CLIENT_ID` and `SPOTIFY_CLIENT_SECRET`.
- Spotify can temporarily return HTTP 429 after heavy QA runs. SonicMind now caches Spotify tokens/searches and backs off cleanly, but cards may stay hidden until the provider limit clears.
- Stripe/payment is not integrated yet; upgrade and extra-pack buttons intentionally show Coming Soon.
- Creator/Pro billing periods use local rolling 30-day windows until a payment provider supplies real renewal dates.
- Extra-credit expiration is implemented for active balance display, but full FIFO credit consumption should be tightened when Stripe is added.
- The current auth token is a lightweight HMAC token suitable for this migration stage; production auth should use a stronger session/JWT strategy and a non-default `BACKEND_SECRET_KEY`.
- Saved chat history exists for Creator/Pro, but the UI is still intentionally simple.
- External web search quality depends on configured Tavily or Brave credentials.

## Notes

- `.env` is intentionally ignored by Git.
- `scripts/init_db.py` only creates tables and indexes. It does not create the PostgreSQL database itself.
- If Spotify credentials are missing, the app will still run; Spotify features will degrade gracefully.
- If the app starts but cannot answer questions, first check the API key and whether `data/index/faiss.index` exists.
