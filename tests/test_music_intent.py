from __future__ import annotations

from src.integrations.spotify_client import build_track_card
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
