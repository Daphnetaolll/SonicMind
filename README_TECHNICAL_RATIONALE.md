# README Technical Rationale

Last updated: 2026-04-28

## Purpose of this document

This document explains the technical reasoning behind the current public-beta architecture of `rag-agent-web-public-mvp`.

It is intentionally separate from the main `README.md`. The main README is for setup, deployment, and usage. This file is for design rationale, architecture tradeoffs, debugging history, and lessons learned while building the project from a local RAG demo into a public-facing music discovery assistant.

The project did not start as a polished product. It evolved through many practical problems:

- local environment standardization
- deployment readiness
- secrets handling
- PostgreSQL setup
- login and quota rules
- English UI and prompt conversion
- local RAG quality
- hybrid RAG routing
- trusted web search
- Spotify mismatch issues
- dynamic music recommendation quality
- public beta deployment preparation
- artist/entity understanding bugs such as `who is John Summit`

The main theme of the project became:

```text
Do not let the model, Spotify, or random web search invent the music answer.
Collect evidence first, structure it, rank it, and only then generate text and Spotify cards from the same source-grounded plan.
```

## High-level product goal

The project is a public-beta music RAG web app. The target behavior is:

1. A user asks a music question.
2. The system understands whether the user is asking about a genre, artist, label, track, album, playlist, comparison, profile, or recommendation.
3. The system retrieves evidence from the local knowledge base first.
4. If local evidence is not enough, it searches trusted music sources.
5. If trusted sources are still not enough, it uses broader web search through a formal search API.
6. The answer includes sources and uncertainty when needed.
7. If Spotify display is useful, Spotify cards show playable results that correspond to the same entities discussed in the answer.
8. Public users must log in, get limited free usage, and cannot freely upload documents or consume unlimited API calls.

This forced the project to solve both product problems and infrastructure problems. It is not just a chatbot. It is a controlled public beta with retrieval, accounts, quotas, music-specific source routing, and Spotify display.

## Current stack

The current MVP stack is:

```text
Frontend and app shell:
Streamlit

Backend language:
Python

RAG:
FAISS
sentence-transformers
BAAI/bge-m3 embedding model direction

LLM:
OpenAI-compatible chat completions through LLM_API_KEY or OPENAI_API_KEY

Database:
PostgreSQL

Search:
Tavily as the default formal web search provider
Brave as optional fallback

Music metadata and source grounding:
MusicBrainz
Discogs
Resident Advisor
Beatport
Traxsource
Billboard
Official Charts
DJ Mag
Mixmag
Every Noise at Once
Ishkur's Guide
Rate Your Music
AllMusic

Music display:
Spotify Web API
Spotify embeds
```

## Frontend rationale

The frontend is currently built with Streamlit, not JavaScript, React, Vite, or Next.js.

This was a deliberate MVP decision.

The project is heavily Python-centered. The core work is not static page rendering. The core work is:

- building a local knowledge base
- embedding documents
- retrieving from FAISS
- calling LLM APIs
- routing between local, trusted-site, and web evidence
- parsing music entities
- validating Spotify results
- tracking account quota in PostgreSQL

Streamlit lets the project expose these Python workflows as a web app without creating a separate API server and JavaScript frontend first.

### Why Streamlit is good for this beta

Streamlit is a good beta frontend because:

- It has very low setup overhead.
- It lets the app be deployed quickly from GitHub.
- It can render forms, login panels, sidebars, buttons, captions, expanders, warnings, and embedded Spotify iframes with minimal code.
- It keeps RAG debugging close to the UI.
- It avoids maintaining a separate frontend build pipeline.
- It lets one developer move quickly while the product direction is still changing.

This mattered because the app changed direction many times. We moved from:

```text
local RAG demo
```

to:

```text
public beta app with auth, quota, hybrid RAG, trusted sources, Spotify display, and deployment docs
```

If the project had started with React and FastAPI immediately, every change would have required frontend/backend contract changes. Streamlit gave us speed while the architecture was still being discovered.

### Frontend tradeoffs

Streamlit is not the ideal final frontend if this becomes a polished consumer product.

Tradeoffs:

- Less control over visual design than React or Next.js.
- Less control over routing, animations, and advanced component layout.
- Frontend and backend are more tightly coupled.
- Complex multi-page user flows can become awkward.
- Subscription checkout and rich Spotify playback UX would be cleaner in a dedicated frontend.
- Streamlit session state is practical for beta but not as flexible as a custom client-side state model.

The long-term migration path is:

```text
Current beta:
Streamlit app
-> Python services
-> PostgreSQL
-> RAG/search/Spotify APIs

Future production:
Next.js or React frontend
-> FastAPI backend
-> PostgreSQL
-> RAG/search/music services
```

The current service boundaries are designed so that this migration is possible. The business logic is not supposed to live in `app.py`. `app.py` should render the UI. The deeper decisions should live under `src/`.

## Backend rationale

Python is the backend language because the project is retrieval and reasoning heavy.

The backend needs to handle:

- embeddings
- FAISS indexing and retrieval
- LLM prompt construction
- web search parsing
- source routing
- music entity extraction
- Spotify API calls
- PostgreSQL account and quota logic

Python is the practical choice for this work because the ecosystem around RAG, embeddings, transformers, and data parsing is strongest there.

## Service structure rationale

The project is organized into modules instead of putting everything in `app.py`.

Important modules include:

- `src/rag_pipeline.py`
- `src/retrievers/`
- `src/services/router_service.py`
- `src/services/evidence_service.py`
- `src/generator.py`
- `src/music/query_understanding.py`
- `src/music/entity_extractor.py`
- `src/music/entity_type_detector.py`
- `src/music/music_recommendation_planner.py`
- `src/music/music_router.py`
- `src/integrations/spotify_client.py`
- `src/services/auth_service.py`
- `src/services/quota_service.py`
- `src/services/question_service.py`
- `src/services/subscription_service.py`

This split became necessary because the project accumulated many different responsibilities.

The UI should not decide:

- whether to call local RAG or web search
- whether evidence is sufficient
- whether an entity is an artist or label
- whether Spotify should be called
- whether a question should deduct quota

Those decisions belong in service and pipeline layers.

The reason is maintainability. If UI and logic are mixed together, every bug becomes harder to isolate. With the current split, we can debug one stage at a time:

```text
query understanding
-> evidence routing
-> entity extraction
-> recommendation planning
-> answer generation
-> Spotify display
-> quota logging
```

## Database rationale

The project uses PostgreSQL instead of JSON files or SQLite because the app is intended to be public and account-based.

The product rules are:

- users must log in
- each account gets 5 free successful questions
- failed questions should not deduct usage
- subscription usage should be tracked separately
- the app should show remaining quota
- users can log in from multiple devices
- uploads should not be open to everyone

That requires persistent server-side state.

PostgreSQL gives the project:

- durable user accounts
- auditable question logs
- usage ledger records
- subscription state
- admin roles
- future migration path to real billing

The database schema includes:

- `users`
- `subscriptions`
- `question_logs`
- `usage_ledger`
- `admin_roles`
- `billing_events`

### Tradeoff

PostgreSQL makes deployment more complex because the public beta needs a cloud database such as Neon or Railway PostgreSQL. But that complexity is worth it because quota and account usage cannot be trusted to browser state or local files.

## Authentication and quota rationale

The app is designed for a public beta, not an open anonymous chatbot.

The reason is cost control. Every public question may trigger:

- LLM API usage
- Tavily API usage
- Spotify API usage
- database writes
- retrieval and embedding computation

The project therefore uses account-based limits:

```text
free trial: 5 successful questions per account
failed answer: no deduction
subscription: scaffolded monthly quota
```

This is not only a billing decision. It is a product safety decision. Public upload and unlimited anonymous use would make the beta easy to abuse.

## Environment and secrets rationale

The project uses `.env` locally and platform-managed secrets in deployment.

Secrets include:

- `LLM_API_KEY`
- `OPENAI_API_KEY`
- `DATABASE_URL`
- `TAVILY_API_KEY`
- `SPOTIFY_CLIENT_ID`
- `SPOTIFY_CLIENT_SECRET`
- optional `DISCOGS_USER_TOKEN`

These must not be committed to GitHub.

The `.env.example` file exists to document required variables without exposing real values.

One lesson from the build process was that seeing keys or certificate paths in terminal output can feel confusing. The important rule is:

```text
.env can contain real local secrets.
.env.example must contain placeholders only.
GitHub must not receive .env.
Cloud hosting must receive secrets through its secret manager.
```

## SSL certificate debugging rationale

During local API testing, Python produced this error:

```text
SSL: CERTIFICATE_VERIFY_FAILED
certificate verify failed: unable to get local issuer certificate
```

This was not an OpenAI API problem. It was a local Python/macOS certificate trust problem.

The debug process was:

1. Test a direct HTTPS request to `https://api.openai.com`.
2. Confirm that the failure happened before the LLM request logic.
3. Set `SSL_CERT_FILE` to the virtualenv `certifi` bundle.
4. Retest HTTPS.
5. Confirm that certificate verification no longer blocked the request.

Then another response appeared:

```text
HTTP Error 421: Misdirected Request
```

That was different from SSL failure. It meant the certificate problem was fixed enough to reach the server, but the simple test URL was not a valid chat completion call. The correct next step was to test `/v1/chat/completions` with a real API key through the app's LLM path.

The main lesson:

```text
SSL errors are environment-level failures.
HTTP errors are application/API-level responses.
Debug them separately.
```

## RAG architecture rationale

The original app used a simple local RAG flow:

```text
local knowledge base
-> vector search
-> LLM answer
```

That was not enough for this project.

Music questions often require information that is:

- current
- source-dependent
- ambiguous
- spread across multiple music databases
- not available in a small local knowledge base

Examples:

```text
What are the best garage house labels?
What are the hottest house tracks right now?
Who is John Summit?
What is the difference between Afterlife and Anjunadeep?
```

The architecture was upgraded to hybrid RAG:

```text
local knowledge base
-> trusted music sources
-> general web search
-> answer with citations and certainty
```

## Evidence sufficiency rationale

The app should not call the open web for every question. It should first ask:

```text
Do we already have enough evidence?
```

That led to the evidence sufficiency check.

The pipeline labels evidence as:

- `SUFFICIENT`
- `PARTIAL`
- `INSUFFICIENT`

If local evidence is sufficient, the app can answer from local evidence only.

If local evidence is partial or insufficient, the app goes to trusted music sources.

If trusted sources are still insufficient, the app goes to broader web search.

This design reduces cost and keeps source quality higher.

### Tradeoff

This routing is more complex than always searching the web. But always searching the web creates new problems:

- more API cost
- more latency
- noisier evidence
- less predictable answers
- more chances for hallucinated or low-quality source use

Hybrid routing is more work, but it is the correct foundation for a public music research assistant.

## Evidence schema rationale

All evidence is converted into a shared schema.

The source can be:

- local knowledge base
- trusted site
- web search result

But downstream code sees a consistent evidence object with:

- source type
- source name
- URL
- title
- snippet
- full text
- retrieval score
- trust level
- metadata

This matters because the answer generator should not need separate logic for each source. It should receive evidence and reason over it.

The evidence schema also makes citations possible.

## Prompt and answer rationale

The generator asks the LLM to return structured JSON:

```json
{
  "answer": "string",
  "certainty": "CONFIDENT|PARTIAL|UNCERTAIN",
  "uncertainty_note": "string",
  "citations": [1, 2]
}
```

This was introduced because unstructured answers caused UI problems. If the model returned normal prose, the app could not reliably show citations or certainty.

The structured output lets the app display:

- answer text
- certainty label
- uncertainty note
- source citations

### Tradeoff

Strict JSON output can fail if the LLM ignores instructions. The code therefore includes fallback parsing. If citations cannot be verified, the app marks the answer as less certain instead of pretending everything is fine.

## English conversion rationale

The project originally had Chinese-focused data and UI text. It was later changed to English because the public beta target is broader and because trusted music sources are mostly English-language sources.

The conversion included:

- page titles
- buttons
- captions
- errors
- prompts
- fallback messages
- knowledge base documents

The design decision was to keep the product language consistent. A mixed Chinese-English UI makes public testing harder and can confuse the LLM prompt behavior.

## Embedding model rationale

The embedding direction moved toward `BAAI/bge-m3`.

The reason is that music questions may include:

- artist names
- genre names
- label names
- multilingual terms
- short descriptions
- long explanatory text

`bge-m3` is a stronger multilingual and general-purpose retrieval model than many smaller default embedding models. It is a practical choice for a music knowledge base that may contain both English and non-English terms.

### Tradeoff

A stronger embedding model can increase memory usage and build time. For a small beta knowledge base, that is acceptable. For larger deployment, the embedding pipeline may need caching, offline build jobs, or a vector database.

## Trusted music source rationale

Open web search is too noisy by default. The app therefore uses a trusted music source policy.

Different sources have different jobs:

- MusicBrainz: artist, recording, album, and release metadata
- Discogs: releases, labels, vinyl, underground electronic metadata
- Resident Advisor: electronic music scenes, artists, labels, editorial context
- Beatport: current electronic music charts and releases
- Traxsource: house, garage, soulful, and underground dance charts
- Billboard: mainstream and dance/electronic chart context
- Official Charts: UK chart context
- DJ Mag: electronic music editorial and scene context
- Mixmag: club culture, tracks, mixes, and current editorial context
- Every Noise at Once: genre relationship map
- Ishkur's Guide: electronic music genre explanations
- Rate Your Music: community genre, album, and list context
- AllMusic: artist, album, and explanatory text

The goal is not to treat every source as equally authoritative. The goal is to use each source for what it is good at.

## Spotify design rationale

One of the most important lessons was:

```text
Spotify should not decide recommendations.
Spotify should display validated candidates.
```

Spotify Search is useful for:

- finding an artist profile
- finding a track by title and artist
- getting album art
- getting Spotify URLs
- getting embed URLs
- getting popularity as a weak signal

Spotify Search is not reliable for:

- deciding the best labels
- deciding the most representative tracks
- deciding what is currently hottest
- deciding music history or genre importance

The early mistake was using Spotify like a recommendation engine:

```text
search Spotify for "acid techno tracks"
search Spotify for "best uk garage"
search Spotify for "house music"
```

That produced playable but often semantically weak results.

The corrected design is:

```text
trusted evidence chooses candidate
Spotify validates exact title + artist
Spotify displays playable card
```

## MusicRecommendationPlan rationale

The `MusicRecommendationPlan` became the key architecture fix.

Before the planner, the app had two separate paths:

```text
Answer path:
RAG evidence -> LLM answer

Spotify path:
genre/entity fallback -> Spotify search
```

This caused mismatches. The answer could discuss one thing while Spotify displayed another.

The planner fixes this by creating one shared candidate list:

```text
user question
-> query understanding
-> evidence routing
-> music recommendation plan
-> answer synthesis
-> Spotify validation
```

Both the answer and Spotify cards use the same candidates.

For trending questions, this is especially important. If the user asks:

```text
What are the hottest house tracks right now?
```

the app should not display classic house tracks just because dynamic search failed.

The current rule is:

```text
For trending or recent track questions, do not fallback to curated classics.
Show source-grounded dynamic matches, or show fewer/no Spotify cards.
```

This is a better user experience than showing confident but wrong Spotify matches.

## Curated recommendations rationale

The project briefly used `curated_recommendations.json` to stabilize known genres such as:

- acid techno
- UK garage
- house music
- melodic techno
- drum and bass

This was useful for MVP quality because it gave known-good examples.

But it also revealed a product limitation:

```text
Curated JSON is accurate only for genres that already exist in the file.
```

The user correctly identified that we cannot manually curate every genre.

The design therefore shifted:

```text
Primary path:
dynamic evidence-driven discovery

Fallback path:
generated cache or curated examples when appropriate

Spotify:
display only
```

Curated data should not be the main long-term recommendation method. It should be a fallback or evaluation baseline.

## Major bug 1: SSL certificate failure

### Symptom

Local HTTPS requests failed with:

```text
SSL: CERTIFICATE_VERIFY_FAILED
certificate verify failed: unable to get local issuer certificate
```

### Initial confusion

It looked like an OpenAI or LLM problem because the app failed when calling an external API.

But the failure happened before the LLM request could complete. It was a local Python certificate issue.

### Debug process

1. Test a simple Python HTTPS request to `https://api.openai.com`.
2. Confirm the failure was in `urllib` SSL verification.
3. Set `SSL_CERT_FILE` to the `certifi` certificate bundle inside the virtual environment.
4. Retry the request.
5. Observe that the error changed from SSL failure to an HTTP-level response.

### Resolution

Set:

```text
SSL_CERT_FILE=/path/to/.venv/lib/python3.x/site-packages/certifi/cacert.pem
```

### Lesson

Environment-level TLS failures and application-level API failures are different. Fix certificate trust first, then test the actual LLM endpoint.

## Major bug 2: API keys and `.env` confusion

### Symptom

There was confusion about where real API keys should live and whether `.env` is safe.

### Root cause

`.env` is local-only if it is ignored by Git, but it is not encrypted. It is simply a local file.

### Decision

Use:

```text
.env
```

for real local values, and:

```text
.env.example
```

for placeholders.

Never commit `.env`.

For deployment, use the hosting platform's secrets manager.

### Lesson

`.env` is private only if it stays off GitHub and off screenshots. It is not a magic encrypted vault.

## Major bug 3: Git push target confusion

### Symptom

Pushing failed with:

```text
refusing to update checked out branch
branch is currently checked out
```

### Root cause

Git was trying to push into a local non-bare repository path instead of a proper GitHub remote repository.

### Debug process

1. Read the push error.
2. Notice the remote target was a local filesystem path.
3. Identify that GitHub Desktop was linked locally but the remote GitHub repository workflow was not fully set up yet.

### Resolution

Use a real GitHub remote repository for push/pull, not another checked-out local repo path.

### Lesson

GitHub Desktop linking a folder is not the same as pushing to a GitHub-hosted remote.

## Major bug 4: missing deployment files

### Symptom

The app could run locally, but deployment would not reliably rebuild the environment.

### Root cause

The project initially lacked the deployment basics:

- `requirements.txt`
- runtime documentation
- environment variable documentation
- clear startup command

### Resolution

Add:

- `requirements.txt`
- `.env.example`
- `runtime.txt`
- README setup steps
- standard startup command:

```bash
python3 -m streamlit run app.py
```

### Lesson

Local success does not mean deployability. A cloud platform must be able to recreate the environment from files in the repo plus platform secrets.

## Major bug 5: local knowledge base not available in deployment

### Symptom

The app needed `data/index/faiss.index` at runtime, but deployment would fail if the index was ignored by Git.

### Root cause

`.gitignore` ignored `data/index/`.

That is reasonable for large generated indexes, but the public beta uses a small FAISS index that must exist in the cloud.

### Decision

Allow `data/index/faiss.index` to be tracked for beta deployment while keeping unnecessary generated files ignored.

### Tradeoff

Tracking a FAISS index is not ideal for large production systems. But for a small public beta, it avoids cloud startup rebuild complexity.

Future production should build indexes in a pipeline or use a hosted vector database.

## Major bug 6: local-only RAG could not answer broad music questions

### Symptom

The app could answer only from local documents. If the question required current or external music context, it failed or answered too narrowly.

Example:

```text
What are the best garage house labels?
```

### Root cause

The knowledge base was too small and static.

### Resolution

Build hybrid RAG:

```text
local knowledge base
-> trusted music sources
-> web search
```

Add evidence sufficiency checks:

- `SUFFICIENT`
- `PARTIAL`
- `INSUFFICIENT`

### Lesson

RAG quality depends not only on embeddings. It also depends on when to seek more evidence.

## Major bug 7: answer said "cannot answer" even when music entities existed

### Symptom

The app sometimes produced answers like:

```text
The evidence does not specify the best garage house labels.
I cannot provide a definitive answer.
```

Even though the system had extracted useful music entities from trusted evidence.

### Root cause

The LLM prompt treated raw evidence as the only source of truth and did not sufficiently use structured music findings.

### Resolution

Inject structured music findings into the generator prompt and add a structured fallback answer when the LLM produces an unhelpful refusal despite having ranked entities.

### Tradeoff

This improves usefulness, but it must be handled carefully. Structured fallback should not invent facts. It should only use entities actually extracted from evidence or trusted data.

## Major bug 8: Spotify showed no tracks for genre explanation

### Symptom

Questions like:

```text
What is UK garage?
What is acid techno?
```

could produce a good text answer, but Spotify showed no useful matches or no new matches.

### Root cause

The answer path and Spotify path were separate. The answer could explain the genre, while Spotify had no structured candidate tracks to display.

### First fix

Add curated representative tracks for known genres.

This helped for:

- acid techno
- UK garage
- house music
- melodic techno
- drum and bass

### New problem

Curated data worked only for genres already in JSON.

The user correctly pointed out:

```text
I cannot manually add every genre in the world.
```

### Long-term fix

Move from curated-first to dynamic evidence-driven recommendation planning.

## Major bug 9: Spotify recommendations were inaccurate

### Symptom

Spotify cards were playable but not accurate.

The app might search:

```text
acid techno tracks
best uk garage
house music
```

and Spotify would return results that matched the keywords but not the intended recommendation.

### Root cause

Spotify Search was being used as a recommendation engine.

### Debug process

1. Compare the answer text with Spotify card titles.
2. Inspect Spotify search queries.
3. Notice broad keyword searches were used.
4. Test exact title + artist matching.
5. Confirm exact matching produced more reliable cards.

### Resolution

Replace broad Spotify keyword search with exact candidate validation:

```text
candidate title + candidate artist
-> Spotify search
-> validate title overlap
-> validate artist overlap
-> build card only if validation passes
```

### Lesson

Spotify should not decide what is good. Spotify should only confirm and display what the evidence layer already selected.

## Major bug 10: dynamic generated cache became polluted

### Symptom

The generated recommendation cache contained bad candidates such as:

```text
Various - This Is The Best Of Drum & Bass Classics
Drum and Bass Classics. Started by ...
3 x CD (Mixed), 2011 - Pure Dubstep
Rate Your Music. In 2010, trap music experienced...
```

### Root cause

The dynamic extractor was too permissive. It saw text that looked like `Artist - Title`, but the text was actually:

- compilation title
- forum thread title
- list title
- chart page title
- album metadata
- "Various Artists" release

### Debug process

1. Inspect `data/music/generated_recommendations.json`.
2. Compare cached candidates with source URLs.
3. Notice Discogs and Rate Your Music page titles were being parsed as tracks.
4. Test parser output with fake `SearchHit` objects.
5. Add filters and rerun extraction tests.

### Resolution

Add filters for:

- `Various`
- `Various Artists`
- compilation metadata
- CD/LP/box set metadata
- forum threads
- list pages
- "Best Of" titles
- generic "Top 100" pages
- chart titles that are not track rows

Delete polluted generated cache.

### Lesson

Generated cache is useful only if extraction is high precision. Bad cache makes wrong results repeat.

## Major bug 11: "What is drum and bass?" produced correct answer but wrong Spotify

### Symptom

The text answer for:

```text
What is drum and bass?
```

was good, but Spotify Matches were wrong.

### Root cause

The system used polluted generated candidates for Spotify display:

```text
Various - This Is The Best Of Drum & Bass Classics
Jairinho over 23 years ago...
Essential Drum n Bass - Box Set 3 x CD
```

The answer was correct because RAG evidence explained the genre. Spotify was wrong because the candidate source list was polluted.

### Debug process

1. Run `understand_query("what is drum and bass")`.
2. Confirm it was correctly classified as `genre_explanation`.
3. Inspect generated recommendation cache.
4. Find the bad DnB candidate list.
5. Test candidate extraction with fake Discogs hits.
6. Confirm bad candidates passed.
7. Add stricter filters.
8. Add a curated fallback for DnB as a temporary quality baseline.
9. Delete polluted generated cache.
10. Re-run Spotify validation.

### Resolution

The DnB query now uses better candidates:

- Goldie - Inner City Life
- LTJ Bukem - Atlantis (I Need You)
- Roni Size - Brown Paper Bag
- Origin Unknown - Valley of the Shadows
- DJ Zinc - Super Sharp Shooter

### Lesson

Good text answer and good Spotify cards are two separate problems unless they share the same candidate plan.

## Major bug 12: "hottest house tracks right now" fell back to classics

### Symptom

The user wanted current or trending house music:

```text
What are the hottest house tracks right now?
```

But Spotify displayed classic house tracks like:

```text
Marshall Jefferson - Move Your Body
Mr. Fingers - Can You Feel It
Frankie Knuckles - Your Love
```

Those are historically important, but not an answer to "right now."

### Root cause

Dynamic extraction found weak or invalid current candidates. When Spotify validation failed, the code fell back to curated classics.

That fallback made sense for:

```text
What is house music?
```

but not for:

```text
What is hot right now?
```

### Debug process

1. Run a real Tavily query for current house tracks.
2. Inspect Beatport and Traxsource search hits.
3. Notice snippets contained useful rows like:

```text
1. Non Stop · Castion · Clarisse Records
2. All Night Long · Volkoder · Diynamic
```

4. Notice the parser was instead extracting bad page titles like:

```text
January 2026 Chart by - Beatport
The Best DJ Mixes Of The Year 2026 So Far - February
```

5. Add source-specific parser support for middle-dot rows.
6. Disable curated fallback for trending/recent track questions.
7. Re-run end-to-end Tavily plus Spotify test.

### Resolution

For trending questions, the app now builds dynamic candidates from current sources such as Beatport and Traxsource and only displays Spotify cards that validate against those candidates.

If dynamic candidates fail, the app should show fewer or no cards, not old classics.

### Lesson

Fallbacks must be context-aware. A fallback that is useful for a genre explanation can be wrong for a current-trends question.

## Major bug 13: Answer and Spotify did not correspond

### Symptom

The app could generate a good answer but show Spotify cards that did not correspond to the answer.

### Root cause

There were two separate paths:

```text
Answer path:
RAG evidence -> LLM answer

Spotify path:
genre/entity fallback -> Spotify search
```

These paths could disagree.

### Resolution

Introduce `MusicRecommendationPlan`.

The shared plan contains:

- question type
- genre hint
- time window
- candidate tracks
- source queries
- confidence
- uncertainty note

The generator receives the same candidate tracks that Spotify will use.

### Lesson

Alignment is architectural, not cosmetic. The UI cannot fix mismatch after the answer and cards were generated from different data.

## Major bug 14: "who is John Summit" understanding failure

### Symptom

The answer could be correct, but the Understanding panel and Spotify were wrong.

For:

```text
who is John Summit
```

the system produced:

```text
intent = general_music_knowledge
primary_entity_type = unknown
needs_spotify = false
spotify_display_target = none
```

For:

```text
tell me about John Summit
```

the system could misclassify `John Summit` as a genre hint.

### Root cause

The system lacked profile-subject extraction.

It understood:

```text
What is drum and bass?
What are the best melodic techno labels?
What are the hottest house tracks right now?
```

better than:

```text
Who is X?
Tell me about X.
```

The query understanding layer only recognized known entities from the local music map. If `John Summit` was not in the known map, it did not become an entity candidate.

### Debug process

1. Run `understand_query("who is John Summit")`.
2. Confirm `needs_spotify` was false.
3. Run `understand_query("tell me about John Summit")`.
4. Confirm it was incorrectly treated as `genre_explanation`.
5. Inspect the conditional order in `query_understanding.py`.
6. Identify that `who is X` was not handled.
7. Identify that `tell me about X` was too eagerly treated as genre.
8. Trace downstream behavior into `music_router.py`.
9. Confirm Spotify was never called because `needs_spotify` was false.

### Planned root fix

Add a profile-subject extraction layer.

It should recognize:

```text
who is X
who are X
tell me about X
introduce X
X 是谁
介绍 X
```

and output:

```text
intent = entity_profile
primary_entity_type = ambiguous
entities = [X]
needs_resolution = true
needs_spotify = true
spotify_display_target = artist_top_tracks or optional_representative_tracks
```

Then resolve type using evidence:

- `DJ`, `producer`, `artist` -> artist
- `record label`, `imprint` -> label
- `genre`, `style`, `sound` -> genre
- `single`, `track`, `song` -> track
- `album`, `LP`, `release` -> album

If the resolved type is artist, Spotify should show:

- artist card
- top tracks

### Lesson

Entity questions need subject extraction before genre detection. Otherwise proper names get mistaken for genres, or ignored entirely.

## Major bug 15: trusted-source search quality varies by site

### Symptom

Some web results are clean. Others are not.

Clean examples:

```text
Track · Artist · Label
Artist - Track
```

Noisy examples:

```text
Top 100 House of March 2026 Various Artists
Best New Tech House January 2026 Chart by ...
RYM Ultimate Boxset
Discogs forum thread
Compilation CD listing
```

### Root cause

Search APIs return pages, titles, and snippets. They do not guarantee structured music entities.

### Current solution

Use:

- domain whitelist
- source-specific parsing
- noise filters
- Spotify title + artist validation
- no fallback for trending questions

### Future solution

Add deeper source adapters for high-value sources:

- Beatport chart parser
- Traxsource chart parser
- MusicBrainz artist/recording lookup
- Discogs release/label lookup
- Spotify artist resolver

This would reduce dependence on generic search snippets.

## Deployment rationale

The public beta target is:

```text
GitHub
-> Streamlit Community Cloud
-> managed PostgreSQL
-> platform secrets
```

This is not the final production architecture, but it is the fastest safe path to a testable public link.

The deployment guide documents:

- required secrets
- database initialization
- Streamlit entrypoint
- smoke tests
- public beta safeguards

### Why track `faiss.index`

For the beta, the FAISS index is small. Tracking it allows Streamlit Cloud to answer questions immediately without rebuilding embeddings during startup.

Tradeoff:

- Good for beta simplicity.
- Not ideal for large production indexes.

Future production should use:

- build pipeline
- object storage
- vector database
- or startup index download

## Public beta safeguards

The app should not be launched as a fully open anonymous tool yet.

Current safeguards:

- login required
- 5 free successful questions per account
- failed answers do not deduct usage
- admin-only uploads
- local subscription scaffolding
- `.env` ignored by Git
- secrets handled by deployment platform

Still needed:

- real payment integration
- better abuse prevention
- email verification
- password reset
- more robust admin dashboard
- feedback form
- monitoring and logs

## Current tradeoffs

### Streamlit vs React

Streamlit is faster for beta. React is better for final UX.

Current choice:

```text
Streamlit now, React/Next.js later if the product proves useful.
```

### Local FAISS vs vector database

Local FAISS is simple and cheap for a small corpus.

A vector database would be better for:

- larger corpus
- multiple users
- frequent updates
- cloud-native scaling

Current choice:

```text
local FAISS for beta, vector database later if needed.
```

### Curated data vs dynamic discovery

Curated data is accurate but not scalable across all genres.

Dynamic discovery scales better but needs strict parsing and validation.

Current choice:

```text
dynamic discovery as primary direction, curated data as fallback or quality baseline.
```

### Spotify search vs evidence ranking

Spotify search is convenient but not a recommendation source.

Current choice:

```text
trusted evidence ranks, Spotify displays.
```

### One Streamlit process vs separate backend

One process is easy for beta.

Separate backend is better for:

- production API design
- frontend flexibility
- background jobs
- queueing
- better scaling

Current choice:

```text
one Streamlit app for beta, split frontend/backend later.
```

## What changed in the project thinking

The project started with a simple question:

```text
Can this local RAG app become a public webpage?
```

The answer became:

```text
Yes, but only if access control, source quality, cost control, and answer/display alignment are designed carefully.
```

The most important shift was realizing that "answer quality" and "Spotify display quality" are not separate UI details. They are the same data problem.

If the answer and Spotify cards come from different candidate sources, they will eventually disagree.

The project therefore moved toward:

```text
shared structured plan
source-grounded candidates
validated display
explicit uncertainty
```

## Next architectural priorities

The next important fixes are:

1. Add profile-subject extraction for `who is X` and `tell me about X`.
2. Resolve ambiguous entities using evidence plus Spotify/MusicBrainz/Discogs.
3. Improve source-specific parsers for Beatport and Traxsource.
4. Add regression tests for understanding, entity resolution, recommendation planning, and Spotify validation.
5. Add a public feedback form.
6. Add better beta monitoring.
7. Replace subscription scaffolding with real payment integration only after product validation.

## Summary

The current architecture is a public-beta compromise:

- Streamlit for fast UI and deployment
- Python services for RAG and music reasoning
- PostgreSQL for public account and quota state
- hybrid RAG for source quality
- Tavily for formal web search
- trusted music domains for evidence control
- Spotify for display only
- shared recommendation planning to keep answer and Spotify cards aligned

The biggest lesson is:

```text
For music RAG, correctness is not only about generating a good paragraph.
Correctness also means the sources, extracted entities, ranked candidates, and Spotify display all agree.
```
