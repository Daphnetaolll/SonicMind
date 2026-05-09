from __future__ import annotations

import json
from datetime import datetime

from src.evidence import EvidenceAssessment, EvidenceItem
from src.generator import LLMConfig, synthesize_answer
from src.music.music_router import build_music_response
from src.music.schemas import (
    MusicRecommendationPlan,
    MusicRoutingResult,
    QueryUnderstandingResult,
    RankedMusicEntity,
    SpotifyCard,
)


def test_synthesis_replaces_generic_recent_dance_answer_with_track_candidates(monkeypatch) -> None:
    # Recommendation text should stay aligned with the structured track plan passed to Spotify.
    current_year = datetime.now().year

    monkeypatch.setattr("src.music.music_recommendation_planner.search_web", lambda *_args, **_kwargs: [])
    monkeypatch.setattr("src.integrations.spotify_client.spotify_credentials_ready", lambda: True)
    monkeypatch.setattr(
        "src.integrations.spotify_client.search_playlists",
        lambda query, limit=5, market="US": [
            {
                "id": "playlist-current",
                "name": "Current dance playlist",
                "external_urls": {"spotify": "https://open.spotify.com/playlist/current"},
            }
        ],
    )
    monkeypatch.setattr(
        "src.integrations.spotify_client.get_playlist_tracks",
        lambda *_args, **_kwargs: [
            {
                "id": "track-current-1",
                "name": "New Season",
                "popularity": 82,
                "external_urls": {"spotify": "https://open.spotify.com/track/current-1"},
                "artists": [{"name": "Current Dance Artist"}],
                "album": {"name": "New Season", "release_date": f"{current_year}-03-01", "images": []},
            }
        ],
    )
    monkeypatch.setattr("src.integrations.spotify_client.search_items", lambda *_args, **_kwargs: {"tracks": {"items": []}})

    def fake_call_chat_completion(**_kwargs):
        return json.dumps(
            {
                "answer": (
                    "I couldn't find specific recent popular dance music tracks to recommend. "
                    "However, house music is a prominent genre in the dance music scene."
                ),
                "certainty": "PARTIAL",
                "uncertainty_note": "The available evidence was incomplete.",
                "citations": [1],
            }
        )

    monkeypatch.setattr("src.generator.call_chat_completion", fake_call_chat_completion)

    query = "recommend me some popular dance music recently"
    evidence = [
        EvidenceItem(
            rank=1,
            source_type="local",
            source_name="SonicMind KB",
            title="House music overview",
            snippet="House music is a style of electronic dance music.",
            full_text="House music originated in Chicago and became foundational to dance music.",
            retrieval_score=0.7,
            trust_level="medium",
        )
    ]
    assessment = EvidenceAssessment(
        label="PARTIAL",
        reasons=["Evidence does not directly list recent dance tracks."],
        evidence_count=1,
        top_score=0.7,
        keyword_coverage=0.4,
    )
    music_routing = build_music_response(query, "", evidence, spotify_limit=5)

    synthesis = synthesize_answer(
        query,
        evidence,
        assessment,
        config=LLMConfig(api_key="test", model="test"),
        music_routing=music_routing,
    )

    assert "Current Dance Artist - New Season" in synthesis.answer
    assert "current picks by style" in synthesis.answer
    assert "house music is a prominent genre" not in synthesis.answer
    assert synthesis.certainty == "PARTIAL"


def test_synthesis_replaces_generic_album_answer_with_spotify_album_card(monkeypatch) -> None:
    # Album cards should rescue follow-up album answers that the LLM phrases as missing evidence.
    def fake_call_chat_completion(**_kwargs):
        return json.dumps(
            {
                "answer": "I couldn't find specific information about a popular album by ISOxo.",
                "certainty": "PARTIAL",
                "uncertainty_note": "No album was mentioned in the evidence.",
                "citations": [1],
            }
        )

    monkeypatch.setattr("src.generator.call_chat_completion", fake_call_chat_completion)

    evidence = [
        EvidenceItem(
            rank=1,
            source_type="site",
            source_name="Spotify",
            title="ISOxo",
            snippet="Spotify artist result: ISOxo.",
            full_text="Spotify artist result: ISOxo. Top tracks include: dontstopme!.",
            retrieval_score=0.86,
            trust_level="medium",
            metadata={"entity": "artist"},
        )
    ]
    assessment = EvidenceAssessment(
        label="PARTIAL",
        reasons=["Artist evidence is available, but album evidence is limited."],
        evidence_count=1,
        top_score=0.86,
        keyword_coverage=0.5,
    )
    music_routing = MusicRoutingResult(
        query_understanding=QueryUnderstandingResult(
            intent="album_recommendation",
            primary_entity_type="artist",
            genre_hint=None,
            entities=[],
            needs_resolution=False,
            needs_spotify=True,
            spotify_display_target="albums",
        ),
        resolved_entities=[],
        ranked_entities=[RankedMusicEntity(name="ISOxo", type="artist", score=0.9, reason="test")],
        recommendation_plan=MusicRecommendationPlan(question_type="none", genre_hint=None, time_window=None),
        spotify_cards=[
            SpotifyCard(
                card_type="album",
                title="kidsgonemad!",
                subtitle="ISOxo",
                spotify_url="https://open.spotify.com/album/album-1",
                source_entity="ISOxo",
            )
        ],
    )

    synthesis = synthesize_answer(
        "recommand me ISOxo's popular album",
        evidence,
        assessment,
        config=LLMConfig(api_key="test", model="test"),
        music_routing=music_routing,
    )

    assert "kidsgonemad!" in synthesis.answer
    assert "couldn't find specific information" not in synthesis.answer


def test_synthesis_replaces_generic_artist_song_answer_with_spotify_tracks(monkeypatch) -> None:
    # Artist top-track cards should prevent generic local-KB fragments from becoming the final answer.
    def fake_call_chat_completion(**_kwargs):
        return json.dumps(
            {
                "answer": "For this style, the strongest track candidates I found are Techno.",
                "certainty": "PARTIAL",
                "uncertainty_note": "The available evidence was incomplete.",
                "citations": [1],
            }
        )

    monkeypatch.setattr("src.generator.call_chat_completion", fake_call_chat_completion)

    evidence = [
        EvidenceItem(
            rank=1,
            source_type="site",
            source_name="Spotify",
            title="ISOxo",
            snippet="Spotify artist result: ISOxo.",
            full_text="Spotify artist result: ISOxo. Top tracks include: dontstopme!.",
            retrieval_score=0.86,
            trust_level="medium",
            metadata={"entity": "artist"},
        )
    ]
    assessment = EvidenceAssessment(
        label="PARTIAL",
        reasons=["Artist evidence is available."],
        evidence_count=1,
        top_score=0.86,
        keyword_coverage=0.5,
    )
    music_routing = MusicRoutingResult(
        query_understanding=QueryUnderstandingResult(
            intent="artist_recommendation",
            primary_entity_type="artist",
            genre_hint=None,
            entities=[],
            needs_resolution=False,
            needs_spotify=True,
            spotify_display_target="artist_top_tracks",
        ),
        resolved_entities=[],
        ranked_entities=[RankedMusicEntity(name="ISOxo", type="artist", score=0.9, reason="test")],
        recommendation_plan=MusicRecommendationPlan(question_type="artist_recommendation", genre_hint=None, time_window=None),
        spotify_cards=[
            SpotifyCard(
                card_type="track",
                title="dontstopme!",
                subtitle="ISOxo - kidsgonemad!",
                spotify_url="https://open.spotify.com/track/track-1",
                source_entity="ISOxo",
            )
        ],
    )

    synthesis = synthesize_answer(
        "can you recommand me ISOxo's popular song?",
        evidence,
        assessment,
        config=LLMConfig(api_key="test", model="test"),
        music_routing=music_routing,
    )

    assert "dontstopme!" in synthesis.answer
    assert "Techno" not in synthesis.answer
