# README Technical Rationale

Last updated: 2026-05-09

## 1. Project Overview

SonicMind is a deployed music knowledge and discovery assistant. The current public version runs as a React frontend on Render and a FastAPI backend on Render, with PostgreSQL persistence, backend-enforced usage quota, Stripe billing, hybrid RAG, trusted-source retrieval, optional web search, and optional Spotify display cards.

The project began as a local Python/Streamlit RAG experiment. It has since moved toward a production-style architecture:

```text
React frontend
-> FastAPI backend
-> PostgreSQL account/quota/billing state
-> RAG and music reasoning services
-> trusted music sources / web search / Spotify / Stripe
```

The deployed services are:

- Frontend: `https://sonicmind.onrender.com`
- Backend API: `https://sonicmind-api.onrender.com`
- Health endpoint: `https://sonicmind-api.onrender.com/api/health`

## 2. Original Problem

The original problem was not simply "build a chatbot." Music questions often require genre knowledge, current context, artist and label disambiguation, source trust, and playable follow-up recommendations. A plain LLM answer can sound plausible while being outdated or wrong, and a direct Spotify search can return playable tracks that are not actually good recommendations.

The deeper problem became:

```text
How can a public-facing music assistant answer accurately, show useful playback cards, control API cost, and remain deployable on a modest cloud instance?
```

That problem forced the project to include retrieval, evidence checks, music-specific entity logic, account quota, subscription billing, deployment constraints, and operational debugging.

## 3. Product Goal

The product goal is to let a user ask music questions such as:

- `What is drum and bass?`
- `Who is Lilly Palmer?`
- `Recommend recent popular dance music.`
- `What are John Summit's popular albums?`
- `What is the difference between house and techno?`

The intended user journey is:

1. The user registers or logs in.
2. The backend checks account quota and plan.
3. The system classifies the question intent.
4. Retrieval gathers local, trusted, or web evidence.
5. The answer generator synthesizes a source-grounded response.
6. Spotify cards appear only when useful candidates can be resolved.
7. Successful answers deduct quota.
8. Creator and Pro users get higher limits and additional features.

## 4. System Architecture

The system is organized around separation of responsibilities.

```text
frontend/
  React routes, forms, account state, pricing page, chat UI, Spotify card rendering

backend/
  FastAPI routes, request/response schemas, auth dependency, billing routes, service wrappers

src/
  RAG pipeline, retrievers, music understanding, repositories, quota, auth, Spotify integration

data/
  Raw music documents, processed chunks, metadata, optional FAISS index

scripts/
  Database initialization, seed users, memory probes, backend mode launch scripts

tests/
  API, billing, runtime mode, retriever, Spotify, and music intent coverage
```

This split exists because UI, quota, billing, retrieval, and generation have different failure modes. Keeping them separate makes bugs easier to isolate.

## 5. Frontend Design Rationale

The current frontend is Vite + React. This replaced the early Streamlit-first UI as the main deployed experience.

React was chosen for the deployed app because it provides:

- proper route-based pages for `/`, `/login`, `/register`, `/pricing`, and `/chat`
- a cleaner product shell with top navigation and plan badges
- component boundaries for chat, messages, sources, Spotify cards, favorites, and history
- TanStack Query for request lifecycle and cache invalidation
- Zustand for persisted auth and conversation state
- a static Render deployment separate from backend secrets

The frontend intentionally does not enforce quota or billing truth. It displays the account state returned by `/api/me`, while the backend remains authoritative.

Tradeoff: React introduces a frontend build pipeline and API-contract management. The benefit is a more realistic deployed product interface and a cleaner path to future UX work.

## 6. Backend Design Rationale

The backend is FastAPI because the project needs an API boundary between browser-safe UI code and secret-bearing server code.

FastAPI owns:

- auth token verification
- account lookup
- quota checks
- billing routes
- raw Stripe webhook body handling
- chat request validation
- CORS
- health diagnostics
- account-status response shaping

The backend wraps existing Python services instead of rewriting every RAG component. This preserves the earlier RAG work while giving the React frontend a stable API.

Secrets stay backend-only:

- database URLs
- LLM keys
- Stripe secret and webhook keys
- Spotify client secret
- Tavily and Discogs keys
- backend signing secret

## 7. RAG Pipeline Evolution

The first RAG path was local:

```text
local documents
-> embeddings
-> FAISS vector search
-> LLM answer
```

This worked for general genre explanations but did not cover current or artist-specific questions well. The pipeline evolved into a hybrid design:

```text
local knowledge base
-> trusted music sources
-> general web search
-> answer with certainty and citations
```

The generator now treats evidence sufficiency seriously. When evidence is weak, the answer should be labeled as partial or uncertain rather than pretending to be definitive.

## 8. Hybrid RAG and Source Routing

SonicMind does not search the whole web first. It tries to use the lowest-cost, most controlled source that can answer the question.

Retrieval order:

1. Local knowledge base.
2. Trusted music sources.
3. Formal web search through a configured provider.

This reduces cost and lowers the chance of low-quality source noise. It also helps keep answers explainable because evidence can be normalized into one schema before synthesis.

Trusted-source routing is especially important for music because different sources have different strengths:

- MusicBrainz for artist, release, and recording metadata.
- Discogs for labels, releases, underground electronic music, and physical releases.
- Resident Advisor, DJ Mag, Mixmag, Beatport, Traxsource, Billboard, and Official Charts for scene and chart context.
- Every Noise at Once and Ishkur's Guide for genre relationship and electronic music explanations.
- AllMusic and Rate Your Music for artist/album descriptions and community context.

## 9. Query Understanding and Music Entity Logic

The project moved from label-first logic to intent-first logic. A question is first classified into an intent such as:

- genre explanation
- artist profile
- track recommendation
- artist recommendation
- album recommendation
- label recommendation
- comparison
- playlist discovery
- general music knowledge

Entity extraction then tries to identify artists, labels, tracks, genres, and follow-up references. This matters because Spotify display should be driven by resolved entities, not broad keyword strings.

Example:

```text
Who is John Summit?
```

should become an artist-profile question, not a generic EDM prompt. If the user then asks for popular albums or songs, the app should carry forward the artist entity.

## 10. Spotify Integration Rationale

One major design lesson was:

```text
RAG decides relevance. Spotify displays playable results.
```

Spotify Search is useful for:

- track URLs
- album art
- artist names
- Spotify IDs
- playback embeds
- weak popularity signals

Spotify Search is not reliable as the primary recommendation engine. Broad searches such as `popular dance music recently` or `house tracks` can return old, generic, or mismatched results.

The corrected architecture is:

```text
trusted evidence / recommendation planner
-> candidate artist-track-album entities
-> Spotify exact or near-exact resolution
-> frontend cards
```

When current/trending evidence is unavailable, the app should show fewer or no Spotify cards rather than confidently showing old songs as "recent."

## 11. Authentication, Quota, and Subscription Design

SonicMind is public-testable, so it needs account and cost control.

The backend stores:

- users
- subscriptions
- billing events
- question logs
- usage ledger rows
- extra credit transactions
- saved chat messages
- favorite tracks

Plans:

| Plan | Limit | Purpose |
| --- | --- | --- |
| Free | 5 questions/day | public trial |
| Student / Creator | 200 questions/month | student and creator usage |
| Pro | 1000 questions/month | heavier portfolio or research usage |

Quota is deducted only after a successful text answer. Failed backend, RAG, or LLM responses do not charge the user.

Billing design:

- Checkout starts first-time Creator/Pro subscriptions.
- Stripe webhooks reconcile real paid access.
- Stripe Customer Portal handles payment methods, invoices, cancellation, and downgrades.
- Direct Creator to Pro upgrades replace the existing subscription item price.

This separation prevents the browser from granting itself access and avoids duplicate subscriptions during upgrades.

## 12. Environment and Deployment Rationale

Deployment introduced a major constraint: the Render backend can hit a 2 GB memory limit if it cold-loads local semantic dependencies such as torch, sentence-transformers, and FAISS.

The solution was to create explicit runtime modes.

Production lightweight mode:

```text
SONICMIND_MODE=production_light
SONICMIND_RETRIEVAL_BACKEND=lexical
ENABLE_LOCAL_EMBEDDING_MODEL=false
ENABLE_RERANKER=false
RAG_LOAD_ON_STARTUP=false
```

Local semantic mode:

```text
SONICMIND_MODE=local_semantic
SONICMIND_RETRIEVAL_BACKEND=faiss
ENABLE_LOCAL_EMBEDDING_MODEL=true
ENABLE_RERANKER=true
```

This lets production stay cheap and stable while preserving a higher-quality semantic path for local testing or future larger deployments.

Render production uses:

```bash
pip install -r requirements-production.txt
python scripts/init_db.py
python -m uvicorn backend.main:app --host 0.0.0.0 --port $PORT --workers 1
```

The frontend uses:

```bash
npm install
npm run build
```

with `VITE_API_BASE_URL=https://sonicmind-api.onrender.com`.

## 13. Major Bugs and Debugging Process

### SSL Certificate Verification Failure

Local Python failed with `CERTIFICATE_VERIFY_FAILED` when calling an external LLM endpoint. This was not an API-key problem. The fix was to point Python/OpenSSL to the `certifi` certificate bundle through `SSL_CERT_FILE`.

### Git Push Rejected To Checked-Out Branch

A push failed because the remote was accidentally a non-bare local repository with the target branch checked out. The fix was to use a real GitHub remote workflow rather than force-pushing into a checked-out local repo.

### API Keys And `.env`

The project clarified that `.env` is not encrypted. It is safe only if it stays local and ignored by Git. `.env.example` and `.env.production.example` must contain placeholders only.

### Unstructured LLM Output

The answer layer expected structured output with certainty and citations, but models can return prose. The system now validates and falls back rather than assuming every answer is machine-parseable.

### Genre Answers Without Spotify Matches

Text answers could explain genres while Spotify showed no cards. The root issue was a mismatch between answer generation and Spotify entity planning. Representative entity extraction and recommendation planning now bridge this gap.

### Spotify Matches Not Corresponding To The Answer

Spotify broad keyword search returned playable but irrelevant results. The architectural fix was to let RAG/trusted evidence select candidates and let Spotify only resolve display metadata.

### Curated Recommendations Were Too Narrow

Curated JSON improved known genres but did not scale to arbitrary or current questions. The longer-term direction is evidence-driven extraction and hosted or live search-backed recommendation planning.

### Query Understanding Failure For Artist Profiles

Questions like `Who is John Summit?` need artist-profile routing. Failures here led to weak answers and missing Spotify cards. The fix is stronger intent classification, entity type detection, and follow-up memory.

### Render Memory OOM

Production chat crashed because the backend could load heavy local semantic dependencies. The fix was explicit lightweight production mode, production dependency splitting, lazy semantic imports, and memory probes.

### Stripe Plan Display And Sync Bugs

Stripe webhooks could return `processed=true` even when local subscription sync did not actually grant access. The fix was to fail critical events that cannot sync and to let subscription metadata provide a safe plan-code fallback. `/api/me` now derives displayed plan from quota/source-of-truth state.

### Creator To Pro Upgrade Blocked

After canceling Creator at period end, the user was still active until the period ended, so the UI sent all paid actions to Billing Portal. The fix was a direct Creator to Pro endpoint and a pricing-page `Upgrade to Pro` action that replaces the existing Stripe subscription item.

## 14. Tradeoffs

Production lightweight retrieval trades some answer quality for stability. This is acceptable for the current 2 GB deployment, but artist/current-music questions benefit from stronger trusted-source search or hosted vector retrieval.

Semantic FAISS mode offers better local retrieval but can exceed cheap production memory limits. It remains available as an explicit mode rather than hidden in production.

Stripe billing is more complex than local demo plans, but it is necessary for real paid access. The tradeoff is that subscription state must be reconciled through webhooks and local database rows.

Spotify display improves product value but can fail because of credentials, rate limits, catalog mismatches, or broad search ambiguity. The app must degrade gracefully.

React + FastAPI is more work than Streamlit, but it creates a more realistic deployed product and separates browser code from backend secrets.

## 15. Current Limitations

- Production lexical retrieval is less accurate than local semantic FAISS for some artist/entity questions.
- The local knowledge base is small.
- High-quality current recommendations depend on external search credentials and source extraction.
- Spotify cards may be absent when credentials are missing, rate limits occur, or candidates cannot be resolved confidently.
- Extra-pack purchases are planned but not yet implemented.
- Direct billing plan changes currently support Creator to Pro; downgrades remain in Stripe Customer Portal.
- Production auth uses a lightweight backend-signed token and should be hardened for a larger public launch.
- Semantic production mode likely needs hosted vector search or a larger Render instance.

## 16. Future Improvements

Recommended next steps:

- Add hosted vector search or API embeddings so production can regain semantic quality without local torch memory usage.
- Add stronger current-music retrieval using chart/source aggregation.
- Add a billing status/admin diagnostic endpoint that exposes non-secret subscription sync state.
- Add extra-pack purchase support and FIFO credit consumption.
- Improve follow-up entity memory for artist, album, and track questions.
- Add richer production smoke tests for billing state and Spotify cards.
- Add observability for retrieval source mix, answer certainty, and Spotify resolution failures.
- Harden auth/session strategy before a larger launch.

## 17. Conclusion

SonicMind's architecture reflects the practical reality of turning a local RAG demo into a deployed product prototype. The project now separates UI, API routes, retrieval, music reasoning, quota, billing, and provider integrations. It also documents the tradeoff between cheap production stability and richer local semantic retrieval.

The most important design principle remains:

```text
Evidence and music reasoning decide the answer.
Spotify displays validated playable results.
Billing and quota are enforced by the backend.
Production mode must match the memory budget.
```

That principle keeps the project understandable, safer to deploy, and easier to improve.
