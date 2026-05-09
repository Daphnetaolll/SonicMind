# SonicMind Code Documentation

Last updated: 2026-05-09

DOCX version: [`docs/SonicMind_Code_Documentation.docx`](SonicMind_Code_Documentation.docx)

## 1. Purpose

This document is a reader-friendly guide to the SonicMind codebase. It explains the main folders, runtime modes, API boundaries, data flow, billing flow, retrieval flow, and testing strategy so another engineer can navigate the project without reverse-engineering every file first.

Current deployed URLs:

- Frontend: `https://sonicmind.onrender.com`
- Backend API: `https://sonicmind-api.onrender.com`
- Health endpoint: `https://sonicmind-api.onrender.com/api/health`

## 2. High-Level Code Map

| Area | Path | Responsibility |
| --- | --- | --- |
| React app | `frontend/src/` | Browser UI, routing, forms, chat rendering, pricing actions, Spotify cards |
| API client | `frontend/src/api/client.js` | Shared Axios client and API helper functions |
| Auth state | `frontend/src/store/authStore.js` | Persisted bearer token, user, chat turns, latest response, UI settings |
| FastAPI app | `backend/main.py` | Routes, auth dependency, CORS, health, account status, billing, chat |
| API schemas | `backend/schemas.py` | Pydantic request/response models for browser-safe API contracts |
| Billing service | `backend/services/billing_service.py` | Stripe Checkout, Portal, direct plan changes, webhook processing |
| Chat service | `backend/services/chat_service.py` | Quota check, question logging, answer generation, usage charging |
| Runtime settings | `src/settings.py` | Production/lightweight vs semantic/FAISS mode resolution |
| RAG pipeline | `src/rag_pipeline.py` | Query routing, evidence gathering, answer synthesis, Spotify planning |
| Retrieval | `src/retriever.py`, `src/retrievers/` | Lexical, FAISS, trusted-source, and web retrieval helpers |
| Music logic | `src/music/` | Intent classification, entity extraction, recommendation planning |
| Database schema | `src/db/schema.py` | PostgreSQL tables, indexes, and repeatable schema setup |
| Repositories | `src/repositories/` | Database access functions by domain |
| Quota service | `src/services/quota_service.py` | Backend-enforced usage limits and subscription-backed plan state |
| Spotify | `src/integrations/spotify_client.py` | Spotify token/search/card resolution |
| Tests | `tests/` | Pytest coverage for API, billing, runtime modes, retrieval, music logic |
| Production smoke | `frontend/tests/e2e/production-smoke.spec.js` | Playwright test for deployed register/login/chat journey |

## 3. Request Flow: Chat

```text
React ChatPage
-> frontend API client POST /api/chat
-> FastAPI auth dependency
-> chat_service.answer_user_question
-> quota_service.get_quota_status
-> question_repository creates question log
-> rag_pipeline answers the question
-> Spotify resolution runs if useful and configured
-> successful answer records usage
-> response returns answer, sources, Spotify cards, plan usage
```

Important behavior:

- Quota is checked before answering.
- Usage is deducted only after a successful text answer.
- Spotify failures should not break a text answer.
- The response includes updated plan/quota fields so the frontend can refresh counters.

## 4. Request Flow: Account Status

`GET /api/me` returns:

```text
{
  user: { id, email, display_name, plan, subscription_status },
  usage: { current_plan, current_plan_name, remaining_questions, features, ... }
}
```

The displayed user plan is derived from quota/source-of-truth state rather than trusting a stale `users.plan` row. This matters because Stripe subscription reconciliation can discover a paid plan during the quota check.

## 5. Request Flow: Billing

SonicMind separates three billing jobs:

| Job | Endpoint | Reason |
| --- | --- | --- |
| Start a first-time paid subscription | `POST /api/billing/checkout-session` | Stripe Checkout owns first purchase and payment collection |
| Manage billing | `POST /api/billing/portal-session` | Stripe Portal owns payment methods, invoices, cancellation, and downgrades |
| Upgrade Creator to Pro | `POST /api/billing/subscription-plan` | The app can safely replace one existing subscription item price |
| Reconcile provider state | `POST /api/billing/webhook` | Stripe webhook is the source of truth for paid access |

Direct Creator to Pro upgrade:

```text
PricingPage Pro button
-> POST /api/billing/subscription-plan { plan_code: "pro" }
-> billing_service.change_subscription_plan
-> load current provider subscription from PostgreSQL
-> retrieve Stripe subscription
-> identify existing subscription item id
-> Stripe Subscription.modify(items=[{ id, price: STRIPE_PRO_PRICE_ID }])
-> sync updated subscription into local database
-> return account status
```

The code intentionally replaces the existing subscription item. It does not create a new Checkout session for an already-subscribed user, because that could create duplicate subscriptions or confusing invoices.

## 6. Runtime Modes

Production lightweight mode:

```text
SONICMIND_MODE=production_light
SONICMIND_RETRIEVAL_BACKEND=lexical
ENABLE_LOCAL_EMBEDDING_MODEL=false
ENABLE_RERANKER=false
RAG_LOAD_ON_STARTUP=false
```

This mode avoids importing or installing heavy semantic packages in production. It is the deployed default for the 2 GB Render backend.

Local semantic mode:

```text
SONICMIND_MODE=local_semantic
SONICMIND_RETRIEVAL_BACKEND=faiss
ENABLE_LOCAL_EMBEDDING_MODEL=true
ENABLE_RERANKER=true
```

This mode keeps the FAISS and `BAAI/bge-m3` path available for local quality testing or future larger infrastructure.

## 7. Data Model Summary

Core tables created by `scripts/init_db.py`:

| Table | Purpose |
| --- | --- |
| `users` | Accounts, plan snapshot, billing period snapshot, extra credit snapshot |
| `subscriptions` | Local subscription records, Stripe provider ids, plan code, period window |
| `billing_events` | Idempotent Stripe webhook event log |
| `question_logs` | Started/succeeded/failed question records |
| `usage_ledger` | Free/subscription/extra-credit usage events |
| `credit_transactions` | Future extra-pack credits and usage |
| `chat_messages` | Saved chat history for paid plans |
| `favorite_tracks` | Saved Spotify favorites for paid plans |
| `admin_roles` | Admin role records |

Database access is kept in `src/repositories/` so service code does not need inline SQL for every operation.

## 8. Retrieval and Music Reasoning

The music pipeline is designed around evidence-first answers.

Key ideas:

- Local knowledge is attempted first.
- Trusted music sources are preferred before broad web search.
- Evidence is normalized into common objects.
- Query understanding decides whether the user is asking for a genre explanation, artist profile, recommendation, comparison, or follow-up.
- Spotify cards are generated from resolved candidates, not broad query text.

This prevents the app from answering about one artist or track while showing unrelated Spotify cards.

## 9. Frontend State and UI Notes

Important frontend files:

- `App.jsx`: top-level shell, routes, topbar plan/user display.
- `PricingPage.jsx`: plan cards, checkout, portal, and direct Pro upgrade.
- `ChatPage.jsx`: chat state, account status, source/favorites/history panels.
- `api/client.js`: backend API calls and bearer token injection.
- `authStore.js`: persisted token/user and current conversation state.

React Query owns server state. Zustand owns persisted client session state. When account status changes after billing, the pricing page updates both the React Query cache and the stored user.

## 10. Environment Variables

Backend-only examples:

```text
DATABASE_URL=...
BACKEND_SECRET_KEY=...
LLM_API_KEY=...
OPENAI_API_KEY=...
STRIPE_SECRET_KEY=...
STRIPE_WEBHOOK_SECRET=...
STRIPE_CREATOR_PRICE_ID=price_...
STRIPE_PRO_PRICE_ID=price_...
SPOTIFY_CLIENT_ID=...
SPOTIFY_CLIENT_SECRET=...
TAVILY_API_KEY=...
DISCOGS_USER_TOKEN=...
```

Frontend-only example:

```text
VITE_API_BASE_URL=https://sonicmind-api.onrender.com
```

Never move backend secrets into `VITE_*` variables. Vite exposes those values to the browser bundle.

## 11. Tests and Verification

Common commands:

```bash
.venv/bin/python -m pytest
cd frontend && npm run build
.venv/bin/python scripts/memory_probe.py --mode lexical
```

Production smoke test:

```bash
cd frontend
FRONTEND_URL=https://sonicmind.onrender.com \
BACKEND_URL=https://sonicmind-api.onrender.com \
EXPECTED_RETRIEVAL_BACKEND=lexical \
npm run test:prod
```

Important test groups:

- `tests/test_api.py`: health, chat API, account status behavior.
- `tests/test_billing_api.py`: checkout, portal, subscription-plan, webhook routes.
- `tests/test_billing_service.py`: Stripe sync and plan-change service behavior.
- `tests/test_runtime_modes.py`: lightweight import behavior and semantic mode configuration.
- `tests/test_music_intent.py`: music query understanding and routing.
- `tests/test_spotify_artist_albums.py`: Spotify artist/album fallback behavior.

## 12. Code Review Notes

Recent review findings and documentation updates:

- README and technical rationale previously described the project as Streamlit-first; the current deployed app is React + FastAPI.
- `render.yaml` previously referenced the older `sonicmind-frontend.onrender.com` placeholder; current docs now use `https://sonicmind.onrender.com`.
- Stripe billing docs now include direct Creator to Pro upgrades and the production webhook URL.
- Production documentation now states that Stripe billing is implemented for Creator/Pro subscriptions, while extra packs remain planned.
- Runtime-mode documentation now reflects the actual lightweight production deployment.

Remaining engineering risks:

- Production lexical retrieval is stable but less accurate than semantic FAISS for some artist/current-context questions.
- Direct billing upgrades can fail if Stripe requires additional payment authentication.
- Extra-pack purchases are not implemented.
- A future larger launch should harden auth/session management beyond the current prototype token.

## 13. How To Read The Code

Recommended order for a new engineer:

1. Read [README.md](../README.md) for setup and deployed URLs.
2. Read [README_TECHNICAL_RATIONALE.md](../README_TECHNICAL_RATIONALE.md) for design reasoning.
3. Read `backend/main.py` to understand API boundaries.
4. Read `backend/schemas.py` to understand response contracts.
5. Read `backend/services/chat_service.py` and `src/rag_pipeline.py` for chat behavior.
6. Read `src/services/quota_service.py` for usage enforcement.
7. Read `backend/services/billing_service.py` for Stripe behavior.
8. Read `frontend/src/pages/PricingPage.jsx` and `frontend/src/pages/ChatPage.jsx` for user workflows.
9. Run the tests before changing behavior.
