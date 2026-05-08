from __future__ import annotations

from src.integrations.spotify_client import build_spotify_cards_for_entities
from src.music.schemas import MusicRecommendationPlan, QueryUnderstandingResult, RankedMusicEntity


def test_artist_album_cards_use_top_track_album_signal(monkeypatch) -> None:
    # Popular album cards should come from the artist's Spotify catalog, not broad album keyword search.
    monkeypatch.setattr("src.integrations.spotify_client.spotify_credentials_ready", lambda: True)
    monkeypatch.setattr(
        "src.integrations.spotify_client.search_artist",
        lambda name, market="US": {"id": "artist-1", "name": "ISOxo"},
    )
    monkeypatch.setattr(
        "src.integrations.spotify_client.get_artist_top_tracks",
        lambda artist_id, market="US": [
            {
                "name": "dontstopme!",
                "album": {
                    "id": "album-1",
                    "name": "kidsgonemad!",
                    "album_type": "album",
                    "release_date": "2023-10-20",
                    "external_urls": {"spotify": "https://open.spotify.com/album/album-1"},
                    "artists": [{"name": "ISOxo"}],
                    "images": [],
                },
            }
        ],
    )
    monkeypatch.setattr("src.integrations.spotify_client.get_artist_albums", lambda artist_id, market="US": [])

    cards = build_spotify_cards_for_entities(
        [RankedMusicEntity(name="ISOxo", type="artist", score=0.9, reason="test")],
        QueryUnderstandingResult(
            intent="album_recommendation",
            primary_entity_type="artist",
            genre_hint=None,
            entities=[],
            needs_resolution=False,
            needs_spotify=True,
            spotify_display_target="albums",
        ),
        recommendation_plan=MusicRecommendationPlan(question_type="none", genre_hint=None, time_window=None),
        max_cards=3,
    )

    assert len(cards) == 1
    assert cards[0].card_type == "album"
    assert cards[0].title == "kidsgonemad!"
    assert cards[0].embed_url == "https://open.spotify.com/embed/album/album-1"
