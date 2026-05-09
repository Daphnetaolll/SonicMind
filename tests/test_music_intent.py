from __future__ import annotations

from src.integrations.spotify_client import build_track_card
from src.music.music_recommendation_planner import build_music_recommendation_plan
from src.music.query_understanding import understand_query


def test_mood_based_recommendation_gets_spotify_intent() -> None:
    # Mood-language recommendations should route to playable tracks with a genre hint.
    result = understand_query("I want something dark, minimal, and hypnotic.")

    assert result.intent == "track_recommendation"
    assert result.genre_hint == "minimal techno"
    assert result.needs_spotify is True
    assert result.spotify_display_target == "tracks"


def test_non_music_question_hides_spotify() -> None:
    # Non-music questions should keep Spotify hidden instead of showing unrelated cards.
    result = understand_query("How do I calculate compound interest?")

    assert result.needs_spotify is False
    assert result.spotify_display_target == "none"


def test_common_techno_typo_still_routes_as_music() -> None:
    # The query normalizer should forgive common misspellings before intent routing.
    result = understand_query("What is tehcno music?")

    assert result.intent == "genre_explanation"
    assert result.genre_hint == "techno"
    assert result.needs_spotify is True


def test_chinese_dark_minimal_query_gets_english_genre_hint() -> None:
    # Chinese mood wording should still produce useful English Spotify search terms downstream.
    result = understand_query("推荐适合深夜听的暗黑极简 techno")

    assert result.intent == "track_recommendation"
    assert result.genre_hint == "minimal techno"
    assert result.needs_spotify is True


def test_dj_set_song_recommendation_routes_to_tracks() -> None:
    # DJ-set recommendation phrasing should prefer track cards over artist or genre cards.
    result = understand_query("I am making a techno DJ set. Do you recommend songs that are popular nowadays?")

    assert result.intent == "track_recommendation"
    assert result.primary_entity_type == "track"
    assert result.genre_hint == "techno"
    assert result.spotify_display_target == "tracks"


def test_recent_dance_music_query_uses_clean_genre_hint() -> None:
    # Trend/recommendation filler words should not leak into the genre sent to search and Spotify.
    result = understand_query("recommend me some popular dance music recently")

    assert result.intent == "track_recommendation"
    assert result.primary_entity_type == "track"
    assert result.genre_hint == "electronic dance music"
    assert result.needs_spotify is True
    assert result.spotify_display_target == "tracks"


def test_drum_and_bass_alias_routes_to_known_genre() -> None:
    # Common DnB spellings should resolve to the curated genre key used by retrieval and Spotify.
    result = understand_query("What is drum & bass?")

    assert result.intent == "genre_explanation"
    assert result.genre_hint == "drum and bass"
    assert result.needs_spotify is True


def test_who_is_unknown_artist_routes_to_artist_profile() -> None:
    # Artist-profile phrasing should use lightweight external metadata instead of generic local-only retrieval.
    result = understand_query("who is john summit")

    assert result.intent == "artist_profile"
    assert result.primary_entity_type == "artist"
    assert result.entities[0].name == "John Summit"
    assert result.needs_spotify is True
    assert result.spotify_display_target == "artist_top_tracks"


def test_artist_popular_album_query_routes_to_artist_albums() -> None:
    # Album follow-ups rewritten with an artist name should request Spotify album cards for that artist.
    result = understand_query("recommand me ISOxo's popular album")

    assert result.intent == "album_recommendation"
    assert result.primary_entity_type == "artist"
    assert result.entities[0].name == "ISOxo"
    assert result.spotify_display_target == "albums"


def test_artist_popular_song_query_routes_to_artist_top_tracks() -> None:
    # Artist song follow-ups should use Spotify top tracks instead of generic genre recommendation.
    result = understand_query("can you recommand me ISOxo's popular song?")

    assert result.intent == "artist_recommendation"
    assert result.primary_entity_type == "artist"
    assert result.entities[0].name == "ISOxo"
    assert result.spotify_display_target == "artist_top_tracks"


def test_tell_me_about_genre_stays_genre_explanation() -> None:
    # Genre questions that look like profile prompts should still route to genre answers.
    result = understand_query("tell me about house music")

    assert result.intent == "genre_explanation"
    assert result.primary_entity_type == "genre"
    assert result.genre_hint == "house"


def test_recent_dance_music_plan_falls_back_to_concrete_representative_tracks(monkeypatch) -> None:
    # If live chart search has no exact artist-track pairs, return concrete tracks with a caution note.
    def fake_search_web(*_args, **_kwargs):
        return []

    monkeypatch.setattr("src.music.music_recommendation_planner.search_web", fake_search_web)

    query = "recommend me some popular dance music recently"
    understanding = understand_query(query)
    plan = build_music_recommendation_plan(query, understanding, evidence=[])

    assert plan.question_type == "trending_tracks"
    assert plan.genre_hint == "electronic dance music"
    assert plan.confidence == "PARTIAL"
    assert plan.candidate_tracks
    assert plan.candidate_tracks[0].source_type == "curated"
    assert plan.uncertainty_note is not None
    assert "rather than verified current chart hits" in plan.uncertainty_note


def test_spotify_track_embed_url_formatting() -> None:
    # Track-card builders should produce both public Spotify URLs and embeddable player URLs.
    card = build_track_card(
        {
            "id": "spotify-track-id",
            "name": "Can You Feel It",
            "external_urls": {"spotify": "https://open.spotify.com/track/spotify-track-id"},
            "artists": [{"name": "Mr. Fingers"}],
            "album": {"name": "Amnesia", "images": []},
            "popularity": 57,
        }
    )

    assert card is not None
    assert card.embed_url == "https://open.spotify.com/embed/track/spotify-track-id"
    assert card.spotify_url == "https://open.spotify.com/track/spotify-track-id"
