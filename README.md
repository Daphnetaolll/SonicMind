# rag-agent-web-public-mvp

This project is a Streamlit-based hybrid-RAG demo. The app can start without any extra build step, but answering questions requires:

- a valid `LLM_API_KEY` or `OPENAI_API_KEY`
- a valid PostgreSQL `DATABASE_URL`
- a ready knowledge base index under `data/index/faiss.index`

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
- Optional: `LLM_MODEL`, `LLM_BASE_URL`, `LLM_TIMEOUT`, `LLM_TEMPERATURE`
- Optional hybrid retrieval: `WEB_SEARCH_PROVIDER`, `TAVILY_API_KEY`, `TAVILY_SEARCH_DEPTH`, `TAVILY_TOPIC`, `TAVILY_INCLUDE_RAW_CONTENT`, `TAVILY_CHUNKS_PER_SOURCE`, `BRAVE_SEARCH_API_KEY`, `WEB_SEARCH_COUNTRY`, `WEB_SEARCH_LANG`, `WEB_SEARCH_SAFESEARCH`, `WEB_FETCH_RESULT_PAGES`, `EXTERNAL_FETCH_TIMEOUT`
- Optional metadata APIs: `MUSIC_METADATA_USER_AGENT`, `DISCOGS_USER_TOKEN`
- Optional Spotify: `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET`
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

6. Start the app.

```bash
python3 -m streamlit run app.py
```

## Knowledge base status

This repo currently includes:

- raw source files in `data/raw/`
- processed chunk files in `data/processed/`

This repo currently does **not** include `data/index/faiss.index`, so question answering will not work until you prepare the index.

## Build the knowledge base

Run these commands from the project root:

```bash
python3 scripts/preprocess.py
python3 scripts/embed_corpus.py
python3 scripts/build_index.py
```

After that, start the app again with:

```bash
python3 -m streamlit run app.py
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
- `admin_roles`
- `billing_events`

## Development Log

I keep a daily development log to document design decisions, implementation progress, debugging process, and next steps.

- [2026-04-27](docs/devlog/2026-04-27.md)

## Public Beta Deployment

Deployment notes are documented in [docs/public_beta_deployment.md](docs/public_beta_deployment.md).

## Notes

- `.env` is intentionally ignored by Git.
- `scripts/init_db.py` only creates tables and indexes. It does not create the PostgreSQL database itself.
- If Spotify credentials are missing, the app will still run; Spotify features will degrade gracefully.
- If the app starts but cannot answer questions, first check the API key and whether `data/index/faiss.index` exists.
