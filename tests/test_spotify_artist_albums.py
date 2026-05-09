from __future__ import annotations

from src.integrations.spotify_client import build_spotify_cards_for_entities, get_artist_top_tracks
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


def test_artist_top_tracks_falls_back_to_search_when_endpoint_is_forbidden(monkeypatch) -> None:
    # Spotify's deprecated top-tracks endpoint can return 403, so artist track cards need a search fallback.
    def fake_api_get(path: str, params: dict[str, str] | None = None):
        if path == "/artists/artist-1/top-tracks":
            raise RuntimeError("Spotify request failed: HTTP 403 Forbidden")
        if path == "/artists/artist-1":
            return {"id": "artist-1", "name": "John Summit"}
        return {}

    def fake_search_items(query: str, item_types: list[str], *, limit: int = 5, market: str = "US") -> dict:
        return {
            "tracks": {
                "items": [
                    {
                        "id": "track-1",
                        "name": "Shiver",
                        "popularity": None,
                        "artists": [{"name": "John Summit"}, {"name": "HAYLA"}],
                    },
                    {
                        "id": "track-2",
                        "name": "Unrelated Track",
                        "popularity": None,
                        "artists": [{"name": "Someone Else"}],
                    },
                ]
            }
        }

    monkeypatch.setattr("src.integrations.spotify_client._api_get", fake_api_get)
    monkeypatch.setattr("src.integrations.spotify_client.search_items", fake_search_items)

    tracks = get_artist_top_tracks("artist-1")

    assert [track["name"] for track in tracks] == ["Shiver"]
