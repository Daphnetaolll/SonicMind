# Music Recommendation Flow

## Why This Layer Exists

Earlier versions used Spotify keyword search such as `acid techno tracks` or `best uk garage`.
That made Spotify behave like a recommendation engine, which produced playable but often inaccurate tracks.

The current design separates responsibilities:

- Hybrid RAG and trusted sources explain the topic.
- `music_recommendation_planner.py` builds one shared candidate list for both the written answer and Spotify cards.
- Dynamic trusted-source discovery is the primary recommendation layer for track questions, especially recent/trending questions.
- Curated music data remains only as a fallback for non-trending representative examples.
- Spotify only finds playable catalog matches for source-grounded candidates that were already chosen.

## Current Flow

1. `query_understanding.py` detects the user's intent and genre/entity target.
2. `entity_extractor.py` ranks labels, artists, tracks, albums, or genres from trusted evidence and curated maps.
3. `music_recommendation_planner.py` builds a `MusicRecommendationPlan` with candidate tracks from current evidence and trusted-source search.
4. `dynamic_recommendation_discovery.py` extracts only explicit artist-track pairs and rejects compilation, forum, album-chart, and generic list titles.
5. `generator.py` receives the same candidate tracks that Spotify will use, so the answer and Spotify cards stay aligned.
6. `spotify_client.py` searches Spotify for exact track and artist targets from the shared plan.
7. `spotify_client.py` validates title and artist before creating a Spotify card.
8. For recent/trending track questions, `spotify_client.py` does not fall back to curated classics if dynamic candidates fail validation.
9. `app.py` displays whether the Spotify card came from evidence, web search, generated cache, curated fallback, or another source.

## Rule

Spotify does not decide recommendations. It only displays validated playable matches.
