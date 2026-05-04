# Public Beta Deployment Guide

This guide describes the fastest safe path to publish the app for early public testing.

## Recommended beta stack

- App hosting: Streamlit Community Cloud
- Database: Neon PostgreSQL or Railway PostgreSQL
- Repository: GitHub
- Secrets: platform-managed secrets, not `.env`

## What must be deployed

- `app.py`
- `requirements.txt`
- `runtime.txt`
- `data/index/faiss.index`
- `data/processed/chunk_meta.jsonl`
- `data/processed/chunks.jsonl`
- `data/raw/`
- `src/`
- `scripts/init_db.py`

`data/processed/embeddings.npy` is not required at runtime and remains ignored.

## Required cloud secrets

Set these in the hosting platform. Do not commit them to GitHub.

```text
DATABASE_URL=postgresql://...
LLM_API_KEY=...
LLM_MODEL=gpt-4o-mini
LLM_BASE_URL=https://api.openai.com/v1
WEB_SEARCH_PROVIDER=tavily
TAVILY_API_KEY=...
SPOTIFY_CLIENT_ID=...
SPOTIFY_CLIENT_SECRET=...
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
MUSIC_METADATA_USER_AGENT=rag-agent-web-public-mvp/0.1 (your-contact@example.com)
DISCOGS_USER_TOKEN=
```

## Deployment steps

1. Push the latest repo to GitHub.
2. Create a cloud PostgreSQL database.
3. Copy the cloud `DATABASE_URL`.
4. Initialize the schema from local terminal:

```bash
source .venv/bin/activate
export DATABASE_URL="your_cloud_database_url"
python3 scripts/init_db.py
```

5. Open Streamlit Community Cloud.
6. Create a new app from the GitHub repository.
7. Select branch `main`.
8. Set entrypoint file to `app.py`.
9. Set Python version to `3.11` if the platform asks.
10. Paste the cloud secrets.
11. Deploy.

## Public beta safeguards

- Keep uploads admin-only.
- Keep account login enabled.
- Keep free usage at 5 questions per account.
- Do not enable real payments until Stripe or another payment gateway is integrated.
- Add a feedback form link before sharing the app broadly.

## Smoke test after deployment

Ask:

```text
What is drum and bass?
What are the hottest house tracks right now?
Who is John Summit?
What are the best garage house labels?
Tell me about Afterlife.
```

Check:

- The app loads without dependency errors.
- Account registration and login work.
- Free quota decreases only after successful answers.
- Answer text and Spotify cards refer to the same music candidates.
- Sources and uncertainty notes display correctly.

## Known beta limitation

Artist profile questions such as `Who is John Summit?` still need profile subject extraction and entity-type resolution. This should be fixed before inviting a larger test group.
