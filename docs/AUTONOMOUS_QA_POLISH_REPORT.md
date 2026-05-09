# Autonomous QA Polish Report

Generated: 2026-05-05T17:11:06

## Summary

- Ran an 80-question API QA pass across music knowledge, scenes, recommendations, DJ/playlist prompts, Chinese, mixed-language, and edge cases.
- Initial pass: 32/80 rows had no automated issue flag; 48/80 needed review, mostly because Spotify hit provider rate limiting after many live catalog lookups.
- Spotify-related flags: 46. Language flags: 3.
- Added a public landing page, polished the pricing surface, improved playlist/DJ routing, strengthened Chinese language instructions, added SonicMind product/support answers, and added Spotify request caching/backoff.
- Verified frontend build and backend tests after fixes.

## Commands Run

- `curl -s http://127.0.0.1:8000/api/health`
- `curl -s http://127.0.0.1:8000/api/pricing`
- `80-question API QA script against POST /api/chat as protest@example.com`
- `.venv/bin/python -m py_compile src/rag_pipeline.py src/generator.py src/integrations/spotify_client.py src/music/query_understanding.py src/music/music_recommendation_planner.py src/support_responses.py backend/schemas.py`
- `targeted post-fix retest script for Spotify, Chinese, pricing/login, private-info, and empty input cases`
- `npm run build (frontend)`
- `.venv/bin/python -m pytest -q`
- `browser-use checks for /, /pricing, and /chat`

## Test And Build Results

- Backend health: PASS (`knowledge_base_ready: true`).
- Pricing endpoint: PASS (Free $0, Creator $4.99, Pro $8.99, extra packs present).
- Frontend build: PASS (`npm run build`).
- Backend tests: PASS (`12 passed, 3 warnings`).
- Browser routes: PASS for `/`, `/pricing`, and `/chat`; chat shows Pro plan, remaining usage, extra credits, collapsed panels, favorites, and settings.

## Bugs Found And Fixed

- Spotify catalog calls eventually returned HTTP 429 during the 80-question run. Added Spotify access-token caching, search-result caching, and provider backoff logging. Text answers already degraded safely with `Spotify recommendation temporarily unavailable.`
- Chinese and mixed-language prompts sometimes answered in English. Added explicit language instructions near the synthesis prompt and Chinese structured-answer fallback text.
- Product support prompts like pricing/login were being answered from broader web/Spotify support evidence. Added SonicMind-owned support responses for pricing, login/password, and private-info safety prompts.
- Empty API input returned Pydantic 422 instead of the route’s clean validation message. Changed the schema so the route returns 400 with `Question is required.`
- Playlist/DJ prompts needed clearer routing. Added playlist-style detection for build/set/playlist prompts while preserving explicit song/track recommendation routing.
- Landing page was effectively just a redirect. Added a real public SonicMind landing page for portfolio review.

## Spotify Recommendation Evaluation

- Early questions returned Spotify cards successfully, including plan-sized results for Pro.
- After many live Spotify calls, Spotify returned HTTP 429. This is an external provider limit, not a text-answer failure.
- The backend now reduces repeated token/search calls and backs off after 429 instead of repeatedly hitting Spotify.
- Remaining risk: Spotify cards cannot be fully retested until the provider rate limit clears or mock Spotify tests are added.

## Retest Highlights

- `Recommend me deep house tracks for studying.` -> status 200, spotify cards 0, snippet: For studying, I recommend the following deep house tracks: 'Prism Shift: Best Deep House - Barista Beat: Chillout House Music', 'Aphex Twin - Selected Ambient W
- `Recommend dark minimal techno.` -> status 200, spotify cards 0, snippet: For dark minimal techno, you can explore playlists like 'Dark Minimal Techno' on Spotify, which features a darker dance vibe. Additionally, the compilation 'Dar
- `Build me a peak-time techno set.` -> status 200, spotify cards 0, snippet: To build a peak-time techno set, consider starting with tracks that create a driving energy. Here are some recommended tracks to include: 1. "ACTION" by Rox Dj,
- `Detroit techno 和 Chicago house 有什么区别？` -> status 200, spotify cards 0, snippet: 底特律科技音乐（Detroit techno）和芝加哥浩室音乐（Chicago house）之间的主要区别在于它们的情感表达和音乐特征。底特律科技音乐通常强调未来感和机械化的节奏，具有更合成和驱动的特性，常常使用鼓机模式和逐渐的张力。而芝加哥浩室音乐则更倾向于温暖和灵魂的感觉，常常结合迪斯科和放克的元素，具有更为亲和的
- `Can you explain Detroit techno 的历史？` -> status 200, spotify cards 0, snippet: 底特律电子音乐（Detroit techno）是一种电子舞曲，最早出现在1980年代的底特律。它是通过结合欧洲电子音乐、非裔美国人舞蹈音乐传统、机器节奏和未来主义艺术观念发展而来的。胡安·阿特金斯（Juan Atkins）、德里克·梅（Derrick May）和凯文·索恩德森（Kevin Saunderson）被认为是
- `What is your pricing?` -> status 200, spotify cards 0, snippet: SonicMind currently has three placeholder plans: Free is $0/month with 5 questions per UTC day, Student / Creator is $4.99/month with 200 questions per month, a
- `Can you help me log in?` -> status 200, spotify cards 0, snippet: Use the SonicMind login page to sign in with your local test account. Password reset email is not implemented in this portfolio build yet, so create a new local
- `Tell me unsupported private information about a random DJ's home address.` -> status 200, spotify cards 0, snippet: I can’t help find or reveal a private person’s home address or unsupported personal information. I can still help with public music history, releases, genres, l
- `<empty input>` -> status 400, spotify cards 0, snippet: 

## Question Test Table

| # | Category | Question | Answer quality | Spotify relevance | Issue found | Fix applied | Retest result |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | A | What is house music? | 5 | 4 | None | No issue found. | pass |
| 2 | A | What is techno? | 5 | 4 | None | No issue found. | pass |
| 3 | A | What is Detroit techno? | 5 | 4 | None | No issue found. | pass |
| 4 | A | What is Chicago house? | 5 | 4 | None | No issue found. | pass |
| 5 | A | What is deep house? | 5 | 4 | None | No issue found. | pass |
| 6 | A | What is acid house? | 5 | 4 | None | No issue found. | pass |
| 7 | A | What is minimal techno? | 5 | 4 | None | No issue found. | pass |
| 8 | A | What is ambient electronic music? | 5 | 4 | None | No issue found. | pass |
| 9 | A | What is the difference between house and techno? | 5 | 4 | None | No issue found. | pass |
| 10 | A | What is the difference between trance and techno? | 5 | 4 | None | No issue found. | pass |
| 11 | A | What is garage house? | 5 | 4 | None | No issue found. | pass |
| 12 | A | What is progressive house? | 5 | 4 | None | No issue found. | pass |
| 13 | A | What is jungle music? | 5 | 4 | None | No issue found. | pass |
| 14 | A | What is breakbeat? | 5 | 5 | None | No issue found. | pass |
| 15 | B | Who are important Detroit techno artists? | 5 | 5 | None | No issue found. | pass |
| 16 | B | Who are important Chicago house artists? | 5 | 5 | None | No issue found. | pass |
| 17 | B | What labels are important in techno? | 5 | 5 | None | No issue found. | pass |
| 18 | B | What labels are important in house music? | 5 | 5 | None | No issue found. | pass |
| 19 | B | What is the role of club culture in electronic music? | 5 | 4 | None | No issue found. | pass |
| 20 | B | What is underground dance music? | 5 | 4 | None | No issue found. | pass |
| 21 | B | What is the relationship between electronic music and queer club culture? | 5 | 4 | None | No issue found. | pass |
| 22 | B | What is the relationship between electronic music and Black music history? | 5 | 4 | None | No issue found. | pass |
| 23 | B | How did Detroit shape techno? | 5 | 2 | no Spotify cards for recommendation-like prompt | Added Spotify token/search caching, 429 backoff logging, richer mood/playlist routing, and safer fallback handling. | Text still succeeds; current Spotify provider returned HTTP 429 during retest, so cards remain temporarily unavailable until rate limit clears. |
| 24 | B | How did Chicago clubs shape house music? | 5 | 3 | Spotify fallback shown | Added Spotify token/search caching, 429 backoff logging, richer mood/playlist routing, and safer fallback handling. | Text still succeeds; current Spotify provider returned HTTP 429 during retest, so cards remain temporarily unavailable until rate limit clears. |
| 25 | B | What is the importance of The Warehouse in house music? | 5 | 4 | None | No issue found. | pass |
| 26 | B | What makes Underground Resistance important? | 5 | 5 | None | No issue found. | pass |
| 27 | C | Recommend me deep house tracks for studying. | 5 | 3 | Spotify fallback shown | Added Spotify token/search caching, 429 backoff logging, richer mood/playlist routing, and safer fallback handling. | status 200; spotify_count 0; snippet: For studying, I recommend the following deep house tracks: 'Prism Shift: Best Deep House - |
| 28 | C | Recommend energetic techno for a late-night DJ set. | 5 | 3 | Spotify fallback shown | Added Spotify token/search caching, 429 backoff logging, richer mood/playlist routing, and safer fallback handling. | Text still succeeds; current Spotify provider returned HTTP 429 during retest, so cards remain temporarily unavailable until rate limit clears. |
| 29 | C | Recommend dark minimal techno. | 5 | 2 | no Spotify cards for recommendation-like prompt | Added Spotify token/search caching, 429 backoff logging, richer mood/playlist routing, and safer fallback handling. | status 200; spotify_count 0; snippet: For dark minimal techno, you can explore playlists like 'Dark Minimal Techno' on Spotify,  |
| 30 | C | Recommend emotional electronic music with vocals. | 5 | 3 | Spotify fallback shown | Added Spotify token/search caching, 429 backoff logging, richer mood/playlist routing, and safer fallback handling. | Text still succeeds; current Spotify provider returned HTTP 429 during retest, so cards remain temporarily unavailable until rate limit clears. |
| 31 | C | Recommend music similar to classic house but modern. | 5 | 3 | Spotify fallback shown | Added Spotify token/search caching, 429 backoff logging, richer mood/playlist routing, and safer fallback handling. | Text still succeeds; current Spotify provider returned HTTP 429 during retest, so cards remain temporarily unavailable until rate limit clears. |
| 32 | C | Recommend tracks for a sunset DJ set. | 5 | 3 | Spotify fallback shown | Added Spotify token/search caching, 429 backoff logging, richer mood/playlist routing, and safer fallback handling. | Text still succeeds; current Spotify provider returned HTTP 429 during retest, so cards remain temporarily unavailable until rate limit clears. |
| 33 | C | Recommend warm and groovy house music. | 5 | 3 | Spotify fallback shown | Added Spotify token/search caching, 429 backoff logging, richer mood/playlist routing, and safer fallback handling. | Text still succeeds; current Spotify provider returned HTTP 429 during retest, so cards remain temporarily unavailable until rate limit clears. |
| 34 | C | Recommend experimental electronic music. | 5 | 3 | Spotify fallback shown | Added Spotify token/search caching, 429 backoff logging, richer mood/playlist routing, and safer fallback handling. | Text still succeeds; current Spotify provider returned HTTP 429 during retest, so cards remain temporarily unavailable until rate limit clears. |
| 35 | C | Recommend music for walking alone at night. | 5 | 3 | Spotify fallback shown | Added Spotify token/search caching, 429 backoff logging, richer mood/playlist routing, and safer fallback handling. | Text still succeeds; current Spotify provider returned HTTP 429 during retest, so cards remain temporarily unavailable until rate limit clears. |
| 36 | C | Recommend music for a fashion show. | 5 | 3 | Spotify fallback shown | Added Spotify token/search caching, 429 backoff logging, richer mood/playlist routing, and safer fallback handling. | Text still succeeds; current Spotify provider returned HTTP 429 during retest, so cards remain temporarily unavailable until rate limit clears. |
| 37 | C | Recommend euphoric trance-inspired electronic tracks. | 5 | 3 | Spotify fallback shown | Added Spotify token/search caching, 429 backoff logging, richer mood/playlist routing, and safer fallback handling. | Text still succeeds; current Spotify provider returned HTTP 429 during retest, so cards remain temporarily unavailable until rate limit clears. |
| 38 | C | Recommend calm ambient techno for focus. | 5 | 2 | no Spotify cards for recommendation-like prompt | Added Spotify token/search caching, 429 backoff logging, richer mood/playlist routing, and safer fallback handling. | Text still succeeds; current Spotify provider returned HTTP 429 during retest, so cards remain temporarily unavailable until rate limit clears. |
| 39 | C | Recommend acid house classics. | 5 | 3 | Spotify fallback shown | Added Spotify token/search caching, 429 backoff logging, richer mood/playlist routing, and safer fallback handling. | Text still succeeds; current Spotify provider returned HTTP 429 during retest, so cards remain temporarily unavailable until rate limit clears. |
| 40 | C | Recommend Detroit techno tracks for beginners. | 5 | 3 | Spotify fallback shown | Added Spotify token/search caching, 429 backoff logging, richer mood/playlist routing, and safer fallback handling. | Text still succeeds; current Spotify provider returned HTTP 429 during retest, so cards remain temporarily unavailable until rate limit clears. |
| 41 | D | Build me a warm-up DJ set. | 5 | 3 | Spotify fallback shown | Added Spotify token/search caching, 429 backoff logging, richer mood/playlist routing, and safer fallback handling. | Text still succeeds; current Spotify provider returned HTTP 429 during retest, so cards remain temporarily unavailable until rate limit clears. |
| 42 | D | Build me a peak-time techno set. | 5 | 2 | no Spotify cards for recommendation-like prompt | Added Spotify token/search caching, 429 backoff logging, richer mood/playlist routing, and safer fallback handling. | status 200; spotify_count 0; snippet: To build a peak-time techno set, consider starting with tracks that create a driving energ |
| 43 | D | Build me a closing set for a dark club night. | 5 | 3 | Spotify fallback shown | Added Spotify token/search caching, 429 backoff logging, richer mood/playlist routing, and safer fallback handling. | Text still succeeds; current Spotify provider returned HTTP 429 during retest, so cards remain temporarily unavailable until rate limit clears. |
| 44 | D | Give me a study playlist with electronic music. | 5 | 3 | Spotify fallback shown | Added Spotify token/search caching, 429 backoff logging, richer mood/playlist routing, and safer fallback handling. | Text still succeeds; current Spotify provider returned HTTP 429 during retest, so cards remain temporarily unavailable until rate limit clears. |
| 45 | D | Give me a mood playlist for late-night driving. | 5 | 3 | Spotify fallback shown | Added Spotify token/search caching, 429 backoff logging, richer mood/playlist routing, and safer fallback handling. | Text still succeeds; current Spotify provider returned HTTP 429 during retest, so cards remain temporarily unavailable until rate limit clears. |
| 46 | D | Give me a playlist that starts soft and becomes energetic. | 5 | 3 | Spotify fallback shown | Added Spotify token/search caching, 429 backoff logging, richer mood/playlist routing, and safer fallback handling. | Text still succeeds; current Spotify provider returned HTTP 429 during retest, so cards remain temporarily unavailable until rate limit clears. |
| 47 | D | Create a 7-track deep house journey for a small lounge. | 5 | 3 | Spotify fallback shown | Added Spotify token/search caching, 429 backoff logging, richer mood/playlist routing, and safer fallback handling. | Text still succeeds; current Spotify provider returned HTTP 429 during retest, so cards remain temporarily unavailable until rate limit clears. |
| 48 | D | Build a minimal techno playlist from warm-up to peak. | 5 | 3 | Spotify fallback shown | Added Spotify token/search caching, 429 backoff logging, richer mood/playlist routing, and safer fallback handling. | Text still succeeds; current Spotify provider returned HTTP 429 during retest, so cards remain temporarily unavailable until rate limit clears. |
| 49 | D | Give me a short DJ set order for sunset into night. | 5 | 3 | Spotify fallback shown | Added Spotify token/search caching, 429 backoff logging, richer mood/playlist routing, and safer fallback handling. | Text still succeeds; current Spotify provider returned HTTP 429 during retest, so cards remain temporarily unavailable until rate limit clears. |
| 50 | D | Make a playlist for a gallery opening with electronic music. | 5 | 3 | Spotify fallback shown | Added Spotify token/search caching, 429 backoff logging, richer mood/playlist routing, and safer fallback handling. | Text still succeeds; current Spotify provider returned HTTP 429 during retest, so cards remain temporarily unavailable until rate limit clears. |
| 51 | E | 什么是 house music？ | 4 | 3 | language mismatch; Spotify fallback shown | Added explicit Chinese/mixed-language synthesis instruction and Chinese fallback text for structured music answers. | Retested selected Chinese/mixed questions; Chinese output now passes. |
| 52 | E | 什么是 techno？ | 5 | 3 | Spotify fallback shown | Added Spotify token/search caching, 429 backoff logging, richer mood/playlist routing, and safer fallback handling. | Text still succeeds; current Spotify provider returned HTTP 429 during retest, so cards remain temporarily unavailable until rate limit clears. |
| 53 | E | 推荐一些适合深夜听的暗黑极简 techno。 | 5 | 3 | Spotify fallback shown | Added Spotify token/search caching, 429 backoff logging, richer mood/playlist routing, and safer fallback handling. | Text still succeeds; current Spotify provider returned HTTP 429 during retest, so cards remain temporarily unavailable until rate limit clears. |
| 54 | E | 推荐一些适合学习时听的 deep house。 | 5 | 3 | Spotify fallback shown | Added Spotify token/search caching, 429 backoff logging, richer mood/playlist routing, and safer fallback handling. | Text still succeeds; current Spotify provider returned HTTP 429 during retest, so cards remain temporarily unavailable until rate limit clears. |
| 55 | E | 如果我喜欢温暖的 bassline，我应该听什么？ | 5 | 2 | no Spotify cards for recommendation-like prompt | Added Spotify token/search caching, 429 backoff logging, richer mood/playlist routing, and safer fallback handling. | Text still succeeds; current Spotify provider returned HTTP 429 during retest, so cards remain temporarily unavailable until rate limit clears. |
| 56 | E | 帮我推荐适合 DJ warm-up 的电子音乐。 | 5 | 3 | Spotify fallback shown | Added Spotify token/search caching, 429 backoff logging, richer mood/playlist routing, and safer fallback handling. | Text still succeeds; current Spotify provider returned HTTP 429 during retest, so cards remain temporarily unavailable until rate limit clears. |
| 57 | E | Detroit techno 和 Chicago house 有什么区别？ | 4 | 3 | language mismatch; Spotify fallback shown | Added explicit Chinese/mixed-language synthesis instruction and Chinese fallback text for structured music answers. | status 200; spotify_count 0; snippet: 底特律科技音乐（Detroit techno）和芝加哥浩室音乐（Chicago house）之间的主要区别在于它们的情感表达和音乐特征。底特律科技音乐通常强调未来感和机械化的节奏， |
| 58 | E | 推荐一些适合时装秀的电子音乐。 | 5 | 3 | Spotify fallback shown | Added Spotify token/search caching, 429 backoff logging, richer mood/playlist routing, and safer fallback handling. | Text still succeeds; current Spotify provider returned HTTP 429 during retest, so cards remain temporarily unavailable until rate limit clears. |
| 59 | E | 什么是 acid house？ | 5 | 3 | Spotify fallback shown | Added Spotify token/search caching, 429 backoff logging, richer mood/playlist routing, and safer fallback handling. | Text still succeeds; current Spotify provider returned HTTP 429 during retest, so cards remain temporarily unavailable until rate limit clears. |
| 60 | E | 推荐一些适合凌晨开车听的 electronic music。 | 5 | 3 | Spotify fallback shown | Added Spotify token/search caching, 429 backoff logging, richer mood/playlist routing, and safer fallback handling. | Text still succeeds; current Spotify provider returned HTTP 429 during retest, so cards remain temporarily unavailable until rate limit clears. |
| 61 | F | 推荐一些 dark minimal techno tracks。 | 5 | 3 | Spotify fallback shown | Added Spotify token/search caching, 429 backoff logging, richer mood/playlist routing, and safer fallback handling. | Text still succeeds; current Spotify provider returned HTTP 429 during retest, so cards remain temporarily unavailable until rate limit clears. |
| 62 | F | 我想要 warm bassline 的 house music。 | 5 | 3 | Spotify fallback shown | Added Spotify token/search caching, 429 backoff logging, richer mood/playlist routing, and safer fallback handling. | Text still succeeds; current Spotify provider returned HTTP 429 during retest, so cards remain temporarily unavailable until rate limit clears. |
| 63 | F | Give me 一些适合凌晨两点 club 的 techno。 | 5 | 3 | Spotify fallback shown | Added Spotify token/search caching, 429 backoff logging, richer mood/playlist routing, and safer fallback handling. | Text still succeeds; current Spotify provider returned HTTP 429 during retest, so cards remain temporarily unavailable until rate limit clears. |
| 64 | F | 推荐一些适合 study 的 ambient electronic music。 | 5 | 3 | Spotify fallback shown | Added Spotify token/search caching, 429 backoff logging, richer mood/playlist routing, and safer fallback handling. | Text still succeeds; current Spotify provider returned HTTP 429 during retest, so cards remain temporarily unavailable until rate limit clears. |
| 65 | F | Can you explain Detroit techno 的历史？ | 4 | 3 | language mismatch; Spotify fallback shown | Added explicit Chinese/mixed-language synthesis instruction and Chinese fallback text for structured music answers. | status 200; spotify_count 0; snippet: 底特律电子音乐（Detroit techno）是一种电子舞曲，最早出现在1980年代的底特律。它是通过结合欧洲电子音乐、非裔美国人舞蹈音乐传统、机器节奏和未来主义艺术观念发展而来的 |
| 66 | F | 我想听 emotional vocals but still electronic。 | 5 | 3 | Spotify fallback shown | Added Spotify token/search caching, 429 backoff logging, richer mood/playlist routing, and safer fallback handling. | Text still succeeds; current Spotify provider returned HTTP 429 during retest, so cards remain temporarily unavailable until rate limit clears. |
| 67 | G | <empty input> | 5 | 5 | empty input should be rejected cleanly; not applicable | Relaxed Pydantic min-length so FastAPI route returns the intended clean 400 message. | status 400; spotify_count 0; snippet:  |
| 68 | G | tehcno musci recomndations for a late nite set | 5 | 3 | Spotify fallback shown | Added Spotify token/search caching, 429 backoff logging, richer mood/playlist routing, and safer fallback handling. | Text still succeeds; current Spotify provider returned HTTP 429 during retest, so cards remain temporarily unavailable until rate limit clears. |
| 69 | G | What is your pricing? | 5 | 5 | None | Added SonicMind-owned support answers for pricing/login/password prompts so web retrieval does not answer with Spotify product support. | status 200; spotify_count 0; snippet: SonicMind currently has three placeholder plans: Free is $0/month with 5 questions per UTC |
| 70 | G | How do I reset my password? | 5 | 5 | None | Added SonicMind-owned support answers for pricing/login/password prompts so web retrieval does not answer with Spotify product support. | Support route added; not all support prompts retested individually. |
| 71 | G | What is 2+2? | 2 | 5 | answer too short | No code fix needed; no Spotify appeared and the concise answer is acceptable for a non-music edge case. | Not retested; documented as acceptable. |
| 72 | G | Tell me about cooking pasta. | 5 | 5 | None | No issue found. | pass |
| 73 | G | give me something cool | 5 | 5 | None | No issue found. | pass |
| 74 | G | I want something emotional | 5 | 5 | None | No issue found. | pass |
| 75 | G | xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx... | 5 | 2 | no Spotify cards for recommendation-like prompt | Added Spotify token/search caching, 429 backoff logging, richer mood/playlist routing, and safer fallback handling. | Text still succeeds; current Spotify provider returned HTTP 429 during retest, so cards remain temporarily unavailable until rate limit clears. |
| 76 | G | Tell me unsupported private information about a random DJ's home address. | 5 | 3 | Spotify fallback shown | Added SonicMind support/safety shortcut that refuses private personal information and disables Spotify. | status 200; spotify_count 0; snippet: I can’t help find or reveal a private person’s home address or unsupported personal inform |
| 77 | G | Recommend songs by an artist that does not exist: Zzqplon Neon Harbor. | 5 | 3 | Spotify fallback shown | Added Spotify token/search caching, 429 backoff logging, richer mood/playlist routing, and safer fallback handling. | Text still succeeds; current Spotify provider returned HTTP 429 during retest, so cards remain temporarily unavailable until rate limit clears. |
| 78 | G | What should I listen to if I only say: night? | 5 | 5 | None | No issue found. | pass |
| 79 | G | Is SonicMind free? | 5 | 5 | None | Added SonicMind-owned support answers for pricing/login/password prompts so web retrieval does not answer with Spotify product support. | Support route added; not all support prompts retested individually. |
| 80 | G | Can you help me log in? | 5 | 5 | None | Added SonicMind-owned support answers for pricing/login/password prompts so web retrieval does not answer with Spotify product support. | status 200; spotify_count 0; snippet: Use the SonicMind login page to sign in with your local test account. Password reset email |

## UI And Design Improvements

- Added an immersive public landing page with dark archive styling and feature cards.
- Polished pricing cards into a premium dark visual system with hover lift and safer Coming Soon modal behavior.
- Preserved chat improvements from the previous pass: plan/remaining/extra counters, collapsed source/history/settings panels, favorites below Spotify, and auto-scroll behavior.

## Remaining Risks

- Spotify is currently rate limited by the provider after the 80-question run; wait for the limit window to clear before manually verifying playable Spotify cards again.
- Automated answer scoring is heuristic; manually inspect a few nuanced music-history and recommendation answers for portfolio polish.
- External web search can still produce noisy candidate tracks when the knowledge base lacks exact source-grounded track pairs.
- Historical note: this QA pass happened before Stripe was connected. Current code now supports Creator/Pro subscriptions, Stripe Checkout, Customer Portal, webhooks, and Creator to Pro upgrades; extra-pack purchases remain placeholders.
- Legacy Streamlit files remain intentionally preserved and were not deleted.

## Next Recommended Improvements

- Add mocked Spotify unit tests so recommendation card behavior can be tested without burning live API quota.
- Add a small local recommendation cache for common demo prompts like deep house studying, dark minimal techno, and Detroit techno beginners.
- Add a frontend lint command if the project grows beyond the current portfolio MVP.
- Add a Stripe test-mode browser suite for checkout, webhook reconciliation, cancellation, and Creator to Pro upgrades.
