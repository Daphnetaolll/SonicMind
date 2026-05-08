from __future__ import annotations

from src.evidence import EvidenceItem
from src.retrievers.site_retriever import retrieve_site_evidence


def test_artist_profile_retrieval_uses_spotify_canonical_name(monkeypatch) -> None:
    # A lightweight Spotify artist lookup can correct the search target before trusted-source retrieval runs.
    calls: list[tuple[str, str, str | None]] = []

    monkeypatch.setattr("src.integrations.spotify_client.spotify_credentials_ready", lambda: True)
    monkeypatch.setattr(
        "src.integrations.spotify_client.search_artist",
        lambda name, market="US": {
            "id": "artist-1",
            "name": "Lilly Palmer",
            "genres": ["melodic techno", "techno"],
            "popularity": 55,
            "followers": {"total": 12345},
            "external_urls": {"spotify": "https://open.spotify.com/artist/artist-1"},
        },
    )
    monkeypatch.setattr(
        "src.integrations.spotify_client.get_artist_top_tracks",
        lambda artist_id, market="US": [{"name": "Hare Ram"}, {"name": "New Generation"}],
    )

    def fake_musicbrainz(query: str, *, max_results: int = 3) -> list[EvidenceItem]:
        calls.append(("musicbrainz", query, None))
        return [
            EvidenceItem(
                rank=1,
                source_type="site",
                source_name="MusicBrainz",
                title=query,
                snippet=f"MusicBrainz artist result: {query}.",
                full_text=f"MusicBrainz artist result: {query}.",
                retrieval_score=0.8,
                trust_level="medium",
                metadata={"access_mode": "official_api", "entity": "artist"},
            )
        ]

    def fake_discogs(query: str, *, max_results: int = 3) -> list[EvidenceItem]:
        calls.append(("discogs", query, None))
        return []

    def fake_search(query: str, *, max_results: int = 4, topic_query: str | None = None) -> list[EvidenceItem]:
        calls.append(("search", query, topic_query))
        return []

    monkeypatch.setattr("src.retrievers.site_retriever._musicbrainz_evidence", fake_musicbrainz)
    monkeypatch.setattr("src.retrievers.site_retriever._discogs_evidence", fake_discogs)
    monkeypatch.setattr("src.retrievers.site_retriever._whitelisted_search_evidence", fake_search)

    evidence = retrieve_site_evidence("who is lily palmer", max_results=4)

    assert evidence[0].source_name == "Spotify"
    assert evidence[0].title == "Lilly Palmer"
    assert "Top tracks include: Hare Ram, New Generation." in evidence[0].full_text
    assert ("musicbrainz", "Lilly Palmer", None) in calls
    assert ("discogs", "Lilly Palmer", None) in calls
    assert ("search", '"Lilly Palmer" music artist DJ producer', "Lilly Palmer") in calls


def test_artist_profile_retrieval_filters_shared_surname_noise(monkeypatch) -> None:
    # Artist-profile evidence should not include a different artist just because a surname overlaps.
    monkeypatch.setattr("src.integrations.spotify_client.spotify_credentials_ready", lambda: True)
    monkeypatch.setattr(
        "src.integrations.spotify_client.search_artist",
        lambda name, market="US": {
            "id": "artist-1",
            "name": "Lilly Palmer",
            "genres": ["techno"],
            "external_urls": {"spotify": "https://open.spotify.com/artist/artist-1"},
        },
    )
    monkeypatch.setattr("src.integrations.spotify_client.get_artist_top_tracks", lambda artist_id, market="US": [])

    def evidence_for(title: str) -> EvidenceItem:
        return EvidenceItem(
            rank=1,
            source_type="site",
            source_name="MusicBrainz",
            title=title,
            snippet=f"MusicBrainz artist result: {title}.",
            full_text=f"MusicBrainz artist result: {title}.",
            retrieval_score=0.8,
            trust_level="medium",
            metadata={"access_mode": "official_api", "entity": "artist"},
        )

    monkeypatch.setattr(
        "src.retrievers.site_retriever._musicbrainz_evidence",
        lambda query, max_results=3: [evidence_for("Lilly Palmer"), evidence_for("Robert Palmer")],
    )
    monkeypatch.setattr("src.retrievers.site_retriever._discogs_evidence", lambda query, max_results=3: [])
    monkeypatch.setattr("src.retrievers.site_retriever._whitelisted_search_evidence", lambda *args, **kwargs: [])

    titles = [item.title for item in retrieve_site_evidence("who is lily palmer", max_results=5)]

    assert "Lilly Palmer" in titles
    assert "Robert Palmer" not in titles
