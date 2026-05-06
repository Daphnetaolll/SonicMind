# SonicMind QA Debug Report

Date: 2026-05-04

## Summary

Phase 4 focused on portfolio polish and a QA/debug pass for the React + FastAPI migration. I kept the current product direction, did not rewrite the app, did not delete Streamlit, did not add Redux/Docker/mobile tooling, and did not put secrets in frontend code.

Main result: frontend build and backend tests pass. Full answer generation could not be verified locally because this workspace has no `.env`, no exported `LLM_API_KEY`/`OPENAI_API_KEY`, and no backend Spotify credentials. The app now fails cleanly in that configuration instead of exposing raw backend failures.

## Project Structure Checked

- `frontend/`: Vite + React app with Router, axios, TanStack Query, zustand, React Bootstrap.
- `backend/`: FastAPI app plus reusable backend service wrappers.
- `src/`: existing RAG, FAISS retrieval, music intent, Spotify, auth, quota, and database services.
- `data/`: local raw/processed docs plus FAISS index.
- `scripts/`: database and knowledge-base utility scripts.
- `tests/`: API and music-intent pytest coverage.
- `app.py`: legacy Streamlit app still present and importable.

## Environment / Startup

Findings:

- `.env.example` exists.
- `.env` is missing locally.
- No relevant secrets are exported in the shell.
- Local Postgres database `postgresql:///rag_agent_web` exists and schema initialization succeeded.
- Backend runs when `DATABASE_URL=postgresql:///rag_agent_web` is supplied.
- Frontend runs on Vite at `http://127.0.0.1:5173/`.

Commands used:

```bash
git status --short
find . -maxdepth 3 -type f ...
test -f .env && printf 'present\n' || printf 'missing\n'
env | rg '^(DATABASE_URL|LLM_API_KEY|OPENAI_API_KEY|SPOTIFY_CLIENT_ID|SPOTIFY_CLIENT_SECRET|BACKEND_SECRET_KEY)='
DATABASE_URL=postgresql:///rag_agent_web .venv/bin/python scripts/init_db.py
DATABASE_URL=postgresql:///rag_agent_web .venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
npm run dev
curl -s http://127.0.0.1:8000/api/health
```

Health result:

```json
{"status":"ok","service":"sonicmind-api","knowledge_base_ready":true}
```

## Technical Checks

Commands run:

```bash
.venv/bin/python -m pytest -q
npm run build
.venv/bin/python -m compileall app.py backend src scripts tests
.venv/bin/python scripts/quick_similarity_test.py
npm run
.venv/bin/python -c "from backend.main import app; import app as streamlit_app; print(app.title); print('streamlit import ok')"
```

Results:

- Backend tests: `7 passed, 3 warnings in 2.23s`
- Frontend build: passed
- Compile check: passed
- Streamlit import: passed
- FastAPI import: passed
- Retrieval utility: passed
- Frontend lint/test scripts: none available; `npm run` lists only `dev`, `build`, and `preview`.

Final sanity commands after the last backend changes:

```bash
lsof -iTCP:8000 -sTCP:LISTEN -n -P
lsof -iTCP:5173 -sTCP:LISTEN -n -P
kill 8843
DATABASE_URL=postgresql:///rag_agent_web .venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
curl -s http://127.0.0.1:8000/api/health
.venv/bin/python -m pytest -q
npm run build
.venv/bin/python -m compileall app.py backend src scripts tests
.venv/bin/python scripts/quick_similarity_test.py
rg -n -g '!frontend/node_modules/**' -g '!frontend/dist/**' "(OPENAI|SPOTIFY|SECRET|PASSWORD|TOKEN|DATABASE_URL|sk-)" frontend README.md docs .env.example backend src tests
```

Final local servers:

- FastAPI: `http://127.0.0.1:8000`
- React/Vite: `http://127.0.0.1:5173`

Known warning:

- Hugging Face cache writes under `/Users/miss.daphne/.cache/huggingface/...` are permission-blocked. Retrieval still works after the initial warning. I added in-process retrieval caching so repeated queries do not repeatedly reload the model or hit Hugging Face checks.

## Auth Flow Testing

Tested through browser and API using only the provided local test account. The report intentionally does not store the test password.

Results:

- Register exact provided account: account already existed locally; API returned clean `400 {"detail":"Email already exists."}`.
- Invalid login: browser showed `Invalid email or password.`
- Valid login: browser reached `/chat`.
- Refresh while logged in: stayed on `/chat`; token persisted through zustand storage.
- Protected `/chat` after logout: redirected to `/login`.
- Chat page error state: visible when LLM config is missing.

Bugs fixed:

- Login/register could return raw 500 when `DATABASE_URL` was missing. They now return clean `503` messages.
- Chat/source/Spotify details were lost on refresh because only chat turns persisted. The latest response metadata now persists with the conversation state.

## 30-Question QA Table

Because no LLM key is configured locally, `/api/chat` reached retrieval and then returned a clean LLM configuration error for non-empty inputs. The retrieval/intent columns show the local RAG routing and Spotify intent behavior that could still be evaluated.

| # | Category | Question | API Result | Answer? | Intent | Genre Hint | Top Retrieved Titles | Spotify Intent? |
|---|---|---|---|---|---|---|---|---|
| 1 | Basic genre | What is house music? | 500 LLM config | No | genre_explanation | house music | House Music, House Music | Yes |
| 2 | Basic genre | What is techno? | 500 LLM config | No | genre_explanation | techno | Techno, Techno | Yes |
| 3 | Basic genre | What is electronic music? | 500 LLM config | No | genre_explanation | electronic music | Electronic Music, Electronic Music | Yes |
| 4 | Basic genre | What is the difference between house and techno? | 500 LLM config | No | entity_comparison | techno | Techno, Techno | Yes |
| 5 | Artist / label / scene | Who are important artists in Chicago house? | 500 LLM config | No | artist_profile | house | House Music, House Music | Yes |
| 6 | Artist / label / scene | What labels are associated with techno? | 500 LLM config | No | label_profile | techno | Techno, Techno | Yes |
| 7 | Artist / label / scene | What is Detroit techno? | 500 LLM config | No | genre_explanation | detroit techno | Techno, Techno | Yes |
| 8 | Artist / label / scene | What is the relationship between house music and club culture? | 500 LLM config | No | genre_explanation | house music | House Music, House Music | Yes |
| 9 | Recommendation | Recommend me energetic techno tracks for a late-night set. | 500 LLM config | No | track_recommendation | techno | House Music, Techno | Yes |
| 10 | Recommendation | Recommend deep house songs for studying. | 500 LLM config | No | track_recommendation | deep house | House Music, House Music | Yes |
| 11 | Recommendation | I want something dark, minimal, and hypnotic. | 500 LLM config | No | track_recommendation | minimal techno | House Music, Techno | Yes |
| 12 | Recommendation | I want emotional electronic music with strong vocals. | 500 LLM config | No | track_recommendation | electronic music | House Music, Techno | Yes |
| 13 | Recommendation | Recommend music similar to classic house but modern. | 500 LLM config | No | track_recommendation | house | House Music, House Music | Yes |
| 14 | Ambiguous | Give me something fast and underground. | 500 LLM config | No | track_recommendation | minimal techno | House Music, House Music | Yes |
| 15 | Ambiguous | I want something for dancing but not too aggressive. | 500 LLM config | No | track_recommendation | house | Techno, House Music | Yes |
| 16 | Ambiguous | What should I listen to if I like warm basslines? | 500 LLM config | No | track_recommendation | deep house | House Music, House Music | Yes |
| 17 | Ambiguous | What is good music for a sunset DJ set? | 500 LLM config | No | track_recommendation | house | House Music, Techno | Yes |
| 18 | Edge | `<empty input>` | 422 validation | No | general_music_knowledge | - | n/a | No |
| 19 | Edge | Very long house/techno/electronic music question | 500 LLM config | No | label_recommendation | house | House Music, House Music | Yes |
| 20 | Edge | What is the capital of Canada? | 500 LLM config | No | general_music_knowledge | - | House Music, Techno | No |
| 21 | Edge | 什么是浩室音乐？ | 500 LLM config | No | genre_explanation | house | House Music, House Music | Yes |
| 22 | Edge | 推荐一些 deep house 学习时候听的歌 | 500 LLM config | No | track_recommendation | deep house | House Music, House Music | Yes |
| 23 | Edge | What is tehcno music? | 500 LLM config | No | genre_explanation | techno | Techno, Techno | Yes |
| 24 | Edge | What BPM was every techno song released in 1988? | 500 LLM config | No | general_music_knowledge | techno | Techno, Techno | No |
| 25 | Additional | Explain acid house. | 500 LLM config | No | genre_explanation | acid house | House Music, House Music | Yes |
| 26 | Additional | Compare deep house and progressive house. | 500 LLM config | No | entity_comparison | deep house | Techno, House Music | Yes |
| 27 | Additional | Recommend a playlist for a warmup set. | 500 LLM config | No | playlist_discovery | - | House Music, House Music | Yes |
| 28 | Additional | Tell me about Frankie Knuckles. | 500 LLM config | No | entity_profile | - | House Music, House Music | Yes |
| 29 | Additional | What makes techno sound mechanical? | 500 LLM config | No | general_music_knowledge | techno | Techno, Techno | No |
| 30 | Additional | Give me hypnotic music with machine-like percussion. | 500 LLM config | No | track_recommendation | minimal techno | House Music, Techno | Yes |

## Spotify Evaluation

Expected behavior reviewed:

- Non-music prompts should not show Spotify intent.
- Mood prompts should map to useful music search terms.
- Spotify should display only backend-supplied cards; frontend never builds queries with secrets.
- If Spotify fails or is not configured, text answer flow should still work and frontend should show a clean fallback.

Improvements made:

- Added mood-to-genre routing for prompts such as dark/minimal/hypnotic, warm basslines, sunset DJ set, and dancing but not aggressive.
- Added Chinese house/electronic genre hints.
- Added a common `tehcno` typo route to techno.
- Prevented generic definition questions like “What is the capital of Canada?” from becoming Spotify/music prompts.
- Added `spotify_error` to API responses and frontend display.
- Improved Spotify card layout with source labels and clearer empty/error states.

Remaining Spotify limitation:

- Real Spotify cards were not verified because no `SPOTIFY_CLIENT_ID` / `SPOTIFY_CLIENT_SECRET` are configured locally.

## Frontend UX Review

Improvements made:

- Added example prompt buttons in the chat empty state.
- Added pending user message display while chat is loading.
- Improved error parsing for FastAPI/Pydantic errors.
- Persisted latest response details across refresh.
- Improved source display with snippet first and expandable full retrieved text.
- Improved Spotify empty/error messaging and card metadata.
- Added responsive refinements for long messages, source overflow, and mobile composer layout.

Browser checks:

- `/login` loads.
- `/register` loads.
- `/chat` is protected.
- Login, invalid login, duplicate register, refresh, logout, and post-logout route guard were tested.

## Backend/API Review

Improvements made:

- Clean 503 handling for auth storage/config failures.
- `spotify_error` included in chat response schema.
- Retrieval cache added for FAISS index, JSONL metadata, chunk lookup, and SentenceTransformer instance.
- Retrieval cache is cleared after successful knowledge-base rebuild.
- Added tests for health, chat serialization, clean login storage failure, music mood intent, non-music Spotify hiding, typo handling, and Spotify embed URL formatting.

## Bugs Found And Fixed

| Bug | Fix |
|---|---|
| Missing `DATABASE_URL` caused raw auth 500s. | Login/register now return sanitized 503 errors. |
| Latest sources/Spotify/certainty disappeared on refresh. | Persisted `latestResponse` in zustand. |
| Mood recommendation prompts did not trigger Spotify intent. | Added mood-to-genre intent mapping. |
| Non-music “What is ...” prompts could trigger Spotify. | Tightened genre extraction to known music terms/style words. |
| `tehcno` typo was not treated as techno. | Added typo handling. |
| Repeated retrieval could hit Hugging Face model checks/rate limits. | Added in-process retrieval caching. |
| Source cards showed long full text immediately. | Added snippet-first layout with expandable full text. |
| Spotify failures were invisible to React. | Added `spotify_error` response and frontend display. |

## Remaining Risks

- Real answer quality cannot be confirmed until `LLM_API_KEY` or `OPENAI_API_KEY` is configured.
- Real Spotify embed quality cannot be confirmed until Spotify backend credentials are configured.
- `/api/chat` still returns 500 when LLM configuration is missing; message is clean, but production should configure the key.
- Retrieval for non-music questions can still return low-scoring local chunks; answer synthesis should handle insufficiency once LLM is configured.
- Chat history is client-side only; `/api/history` is still a future phase.
- `backend/package-lock.json` is an unrelated untracked file already present in the workspace. I left it untouched.
- Hugging Face cache permissions still warn on first model load.

## Recommended Next Improvements

1. Add a real `.env` locally with `DATABASE_URL`, `BACKEND_SECRET_KEY`, and an LLM key, then rerun the 30-question chat table for actual answer quality.
2. Configure Spotify credentials and verify cards for house, techno, mood, and non-music prompts.
3. Add a lightweight `/api/history` endpoint backed by `question_logs`.
4. Add frontend unit tests for auth store and chat request states if you want more polish before deployment.
5. Consider fixing the local Hugging Face cache ownership or setting a project-local `HF_HOME`.
