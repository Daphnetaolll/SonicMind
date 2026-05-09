from __future__ import annotations

import re
from datetime import datetime

from src.evidence import EvidenceItem
from src.music.dynamic_recommendation_discovery import DISCOVERY_DOMAINS, TrackCandidate, extract_track_candidates_from_hits
from src.music.recommendation_provider import get_recommendation_for_genre
from src.music.schemas import (
    MusicRecommendationPlan,
    MusicTrackCandidate,
    QueryUnderstandingResult,
    RecommendationQuestionType,
)
from src.retrievers.search_api import SearchHit, search_web


TRENDING_MARKERS = (
    "recent",
    "recently",
    "right now",
    "current",
    "currently",
    "latest",
    "new",
    "hot",
    "hottest",
    "trending",
    "popular now",
    "this week",
    "this month",
    "this year",
    "最近",
    "现在",
    "当下",
    "最新",
    "最火",
    "热门",
)
RECENT_RELEASE_YEAR_WINDOW = 1


def _style_buckets_for_genre(genre_hint: str | None) -> list[tuple[str, tuple[str, ...]]]:
    # Broad "dance music" requests need coverage across scenes instead of one generic EDM bucket.
    genre = (genre_hint or "electronic music").lower()
    if any(marker in genre for marker in ("dance", "edm", "electronic")):
        return [
            ("Mainstream dance / electronic", ("dance electronic", "edm", "dance pop")),
            ("House / tech house", ("house", "tech house", "afro house")),
            ("Techno / melodic techno", ("techno", "melodic techno")),
            ("Bass / DnB / trap", ("drum and bass", "dubstep", "trap")),
        ]
    if "house" in genre:
        return [
            ("House / tech house", ("house", "tech house")),
            ("Deep / melodic house", ("deep house", "melodic house")),
            ("Afro / organic house", ("afro house", "organic house")),
        ]
    if "techno" in genre:
        return [
            ("Peak-time techno", ("techno", "peak time techno")),
            ("Melodic techno", ("melodic techno",)),
            ("Hard / industrial techno", ("hard techno", "industrial techno")),
        ]
    if "drum" in genre and "bass" in genre:
        return [
            ("Dancefloor DnB", ("drum and bass", "dancefloor drum and bass")),
            ("Liquid DnB", ("liquid drum and bass",)),
            ("Jungle / breakbeat", ("jungle", "breakbeat")),
        ]
    return [(genre_hint or "Electronic music", (genre_hint or "electronic music",))]


def _lower(value: str) -> str:
    return value.lower()


def _is_trending_query(query: str) -> bool:
    lowered = _lower(query)
    return any(marker in lowered for marker in TRENDING_MARKERS)


def _question_type(query: str, understanding: QueryUnderstandingResult) -> RecommendationQuestionType:
    # Map query intent to the recommendation strategy that should feed both text and Spotify cards.
    if not understanding.needs_spotify:
        return "none"
    if understanding.intent == "playlist_discovery":
        return "playlist_discovery"
    if _is_trending_query(query) and understanding.spotify_display_target in {"tracks", "representative_tracks", "optional_representative_tracks"}:
        return "trending_tracks"
    if understanding.spotify_display_target == "tracks":
        return "track_recommendation"
    if understanding.spotify_display_target in {"representative_tracks", "optional_representative_tracks"}:
        return "representative_tracks"
    if understanding.spotify_display_target == "artist_top_tracks":
        return "artist_recommendation"
    if understanding.spotify_display_target == "playlists":
        return "playlist_discovery"
    if understanding.intent == "label_recommendation":
        return "label_recommendation"
    return "none"


def _time_window(query: str) -> str | None:
    lowered = _lower(query)
    if any(marker in lowered for marker in ("right now", "current", "currently", "latest", "new", "hot", "hottest", "trending", "最近", "现在", "当下", "最新", "最火", "热门")):
        return "recent"
    if "this week" in lowered:
        return "this_week"
    if "this month" in lowered:
        return "this_month"
    if "this year" in lowered:
        return "this_year"
    return None


def _query_genre(understanding: QueryUnderstandingResult) -> str:
    return understanding.genre_hint or "electronic music"


def _source_queries(query: str, understanding: QueryUnderstandingResult, question_type: RecommendationQuestionType) -> list[str]:
    # Build trusted-source search queries only for recommendation types that need dynamic track discovery.
    genre = _query_genre(understanding)
    year = datetime.now().year

    if question_type == "trending_tracks":
        queries: list[str] = []
        for _style_label, terms in _style_buckets_for_genre(genre):
            style = terms[0]
            queries.extend(
                [
                    f'"{style}" top tracks {year} chart Beatport Spotify playlist',
                    f'"{style}" best new tracks {year} Mixmag DJ Mag playlist',
                ]
            )
        queries.extend(
            [
                f'"{genre}" top tracks {year} chart',
                f'"{genre}" new tracks {year} Beatport Traxsource',
            ]
        )
        return queries[:10]
    if question_type == "track_recommendation":
        return [
            f'"{genre}" best tracks artists',
            f'"{genre}" essential tracks',
            f'"{genre}" top songs tracks',
        ]
    if question_type == "playlist_discovery":
        return [
            f'"{genre}" DJ set tracklist essential tracks',
            f'"{genre}" playlist tracks artists',
            f'"{genre}" mood playlist electronic tracks',
        ]
    if question_type == "representative_tracks":
        return [
            f'"{genre}" representative tracks artists',
            f'"{genre}" classic tracks',
            f'"{genre}" essential tracks artists',
        ]
    return []


def _style_hint_for_source_query(source_query: str, genre_hint: str | None) -> str | None:
    query = source_query.lower()
    for style_label, terms in _style_buckets_for_genre(genre_hint):
        if any(term in query for term in terms):
            return style_label
    return None


def _hit_from_evidence(item: EvidenceItem) -> SearchHit:
    return SearchHit(
        title=item.title,
        url=item.url or "",
        snippet=f"{item.snippet} {item.full_text}",
        source_name=item.source_name,
    )


def _candidate_key(title: str, artist: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", f"{artist} {title}".lower()).strip()


def _source_bonus(source_names: set[str], question_type: RecommendationQuestionType) -> float:
    # Weight chart/editorial sources higher for trending requests and metadata sources for validation.
    lowered = " ".join(source_names).lower()
    score = 0.0
    if question_type == "trending_tracks":
        if any(name in lowered for name in ("beatport", "traxsource", "billboard", "official charts")):
            score += 0.28
        if any(name in lowered for name in ("dj mag", "mixmag", "resident advisor")):
            score += 0.18
    if any(name in lowered for name in ("discogs", "musicbrainz")):
        score += 0.12
    return score


def _to_plan_candidate(
    candidate: TrackCandidate,
    *,
    source_type: str,
    question_type: RecommendationQuestionType,
    evidence: str,
    style_hint: str | None = None,
) -> MusicTrackCandidate:
    source_names = sorted(candidate.sources)
    return MusicTrackCandidate(
        title=candidate.title,
        artist=candidate.artist,
        score=round(candidate.score + _source_bonus(candidate.sources, question_type), 3),
        source_type=source_type,  # type: ignore[arg-type]
        style_hint=style_hint,
        source_names=source_names,
        source_urls=sorted(candidate.urls)[:3],
        evidence=evidence,
        reason="Extracted as an explicit artist-track pair from source-grounded music evidence.",
    )


def _merge_candidates(candidates: list[MusicTrackCandidate], max_candidates: int) -> list[MusicTrackCandidate]:
    # Merge duplicate artist-track pairs while preserving the strongest supporting source set.
    merged: dict[str, MusicTrackCandidate] = {}
    for item in candidates:
        key = _candidate_key(item.title, item.artist)
        if not key:
            continue
        existing = merged.get(key)
        if not existing:
            merged[key] = item
            continue
        existing.score += item.score * 0.65
        existing.source_names = sorted(set(existing.source_names) | set(item.source_names))
        existing.source_urls = sorted(set(existing.source_urls) | set(item.source_urls))[:3]
        if not existing.evidence and item.evidence:
            existing.evidence = item.evidence

    ranked = sorted(merged.values(), key=lambda item: (item.score, len(item.source_names)), reverse=True)
    return ranked[:max_candidates]


def _track_release_year(track: dict) -> int | None:
    release_date = str((track.get("album") or {}).get("release_date") or "")
    match = re.match(r"^(\d{4})", release_date)
    return int(match.group(1)) if match else None


def _primary_artist(track: dict) -> str:
    artists = [artist.get("name", "") for artist in track.get("artists", []) if artist.get("name")]
    return artists[0] if artists else ""


def _spotify_track_candidate(
    track: dict,
    *,
    style_hint: str,
    source_name: str,
    source_url: str | None = None,
) -> MusicTrackCandidate | None:
    # Keep "recently" fallback honest by rejecting old catalog tracks before they reach Spotify cards.
    title = str(track.get("name") or "").strip()
    artist = _primary_artist(track).strip()
    if not title or not artist:
        return None

    current_year = datetime.now().year
    release_year = _track_release_year(track)
    if release_year is not None and release_year < current_year - RECENT_RELEASE_YEAR_WINDOW:
        return None

    popularity = int(track.get("popularity") or 0)
    recency_bonus = 0.12 if release_year == current_year else 0.04 if release_year else 0.0
    track_url = track.get("external_urls", {}).get("spotify")
    source_urls = [url for url in (track_url, source_url) if url]
    release_note = f" released in {release_year}" if release_year else ""
    return MusicTrackCandidate(
        title=title,
        artist=artist,
        score=round(0.48 + min(popularity, 100) / 100 * 0.35 + recency_bonus, 3),
        source_type="spotify_fallback",
        style_hint=style_hint,
        source_names=[source_name],
        source_urls=list(dict.fromkeys(source_urls))[:3],
        evidence=f"Spotify current catalog/playlist discovery found {artist} - {title}{release_note}.",
        reason="Selected from recent Spotify playlist/search discovery after trusted chart search had limited exact track pairs.",
    )


def _current_spotify_candidates(genre_hint: str | None, *, max_candidates: int, market: str = "US") -> list[MusicTrackCandidate]:
    """
    Explanation:
    Live web search can fail or return prose-only chart pages.
    For explicitly recent/popular questions, Spotify playlist and year-filtered catalog search gives a lightweight
    current-music fallback without loading local semantic models.
    """
    try:
        from src.integrations.spotify_client import (
            get_playlist_tracks,
            search_items,
            search_playlists,
            spotify_credentials_ready,
        )
    except Exception:
        return []

    if not spotify_credentials_ready():
        return []

    current_year = datetime.now().year
    buckets = _style_buckets_for_genre(genre_hint)
    per_style_limit = max(1, min(2, max_candidates // max(len(buckets), 1) + 1))
    selected: list[MusicTrackCandidate] = []
    overflow: list[MusicTrackCandidate] = []

    for style_label, terms in buckets:
        style_candidates: list[MusicTrackCandidate] = []
        primary_term = terms[0]
        playlist_query = f"{primary_term} hits {current_year}"
        try:
            playlists = search_playlists(playlist_query, limit=2, market=market)
        except Exception:
            playlists = []
        for playlist in playlists[:1]:
            playlist_id = playlist.get("id")
            if not playlist_id:
                continue
            playlist_name = playlist.get("name") or playlist_query
            playlist_url = playlist.get("external_urls", {}).get("spotify")
            try:
                tracks = get_playlist_tracks(playlist_id, market=market, limit=25)
            except Exception:
                tracks = []
            for track in tracks:
                candidate = _spotify_track_candidate(
                    track,
                    style_hint=style_label,
                    source_name=f"Spotify playlist: {playlist_name}",
                    source_url=playlist_url,
                )
                if candidate:
                    style_candidates.append(candidate)

        for term in terms[:2]:
            for search_query in (f'{term} year:{current_year}', f'new {term} {current_year}'):
                try:
                    data = search_items(search_query, ["track"], limit=8, market=market)
                except Exception:
                    continue
                for track in data.get("tracks", {}).get("items", []):
                    candidate = _spotify_track_candidate(
                        track,
                        style_hint=style_label,
                        source_name=f"Spotify Search: {search_query}",
                    )
                    if candidate:
                        style_candidates.append(candidate)

        ranked_style = _merge_candidates(style_candidates, max_candidates)
        selected.extend(ranked_style[:per_style_limit])
        overflow.extend(ranked_style[per_style_limit:])

    return _merge_candidates(selected + overflow, max_candidates)


def _fallback_representative_candidates(
    genre_hint: str | None,
    *,
    max_candidates: int,
) -> list[MusicTrackCandidate]:
    # When live search cannot extract current artist-track pairs, keep recommendations concrete and source-backed.
    recommendation = get_recommendation_for_genre(genre_hint)
    if not recommendation:
        return []

    record, recommendation_source = recommendation
    source_type = "curated" if recommendation_source == "curated" else "generated_cache"
    candidates: list[MusicTrackCandidate] = []
    for item in record.get("representative_tracks", []):
        title = item.get("title")
        artist = item.get("artist")
        if not title or not artist:
            continue
        source_names = list(item.get("sources", []) or record.get("sources", []) or [])
        candidates.append(
            MusicTrackCandidate(
                title=title,
                artist=artist,
                score=0.35,
                source_type=source_type,  # type: ignore[arg-type]
                style_hint=None,
                source_names=source_names,
                source_urls=list(item.get("source_urls", []) or [])[:3],
                evidence=str(record.get("explanation", "")),
                reason="Used as a source-grounded representative fallback when recent track search had no exact candidates.",
            )
        )
        if len(candidates) >= max_candidates:
            break
    return candidates


def _candidate_confidence(candidate_count: int, searched: bool) -> tuple[str, str | None]:
    # Convert candidate coverage into a user-facing confidence label and uncertainty note.
    if candidate_count >= 4:
        return "CONFIDENT", None
    if candidate_count >= 2:
        return "PARTIAL", "Only a small number of source-grounded track candidates were found."
    if candidate_count == 1:
        return "PARTIAL", "Only one source-grounded track candidate was found."
    if searched:
        return "UNCERTAIN", "Trusted-source search did not return explicit artist-track candidates."
    return "UNCERTAIN", "No dynamic music recommendation search was needed for this question."


def build_music_recommendation_plan(
    query: str,
    understanding: QueryUnderstandingResult,
    evidence: list[EvidenceItem],
    *,
    max_candidates: int = 8,
) -> MusicRecommendationPlan:
    """
    Explanation:
    This is the shared recommendation layer for both the text answer and Spotify cards.
    It chooses candidate tracks from evidence and trusted web results before Spotify is allowed to display anything.
    """
    question_type = _question_type(query, understanding)
    if question_type == "none":
        return MusicRecommendationPlan(
            question_type="none",
            genre_hint=understanding.genre_hint,
            time_window=None,
            confidence="UNCERTAIN",
            uncertainty_note="No Spotify-oriented recommendation plan was needed.",
        )

    plan_candidates: list[MusicTrackCandidate] = []

    # Start with tracks already present in the answer evidence so text and cards stay synchronized.
    evidence_hits = [_hit_from_evidence(item) for item in evidence if item.url or item.full_text]
    for candidate in extract_track_candidates_from_hits(evidence_hits, _query_genre(understanding)):
        plan_candidates.append(
            _to_plan_candidate(
                candidate,
                source_type="evidence",
                question_type=question_type,
                evidence="Extracted from the RAG evidence already used for the answer.",
                style_hint=None,
            )
        )

    queries = _source_queries(query, understanding, question_type)
    searched = False
    if queries and len(plan_candidates) < max_candidates:
        # Expand only through trusted music domains and keep search failure non-fatal.
        for source_query in queries:
            try:
                hits = search_web(source_query, max_results=6, allowed_domains=DISCOVERY_DOMAINS)
            except (RuntimeError, ValueError):
                hits = []
            searched = searched or bool(hits)
            style_hint = _style_hint_for_source_query(source_query, understanding.genre_hint)
            for candidate in extract_track_candidates_from_hits(hits, _query_genre(understanding)):
                plan_candidates.append(
                    _to_plan_candidate(
                        candidate,
                        source_type="web_search",
                        question_type=question_type,
                        evidence=f"Extracted from trusted-source search query: {source_query}",
                        style_hint=style_hint,
                    )
                )

    ranked = _merge_candidates(plan_candidates, max_candidates)
    if question_type == "trending_tracks" and len(ranked) < max_candidates:
        ranked = _merge_candidates(
            ranked + _current_spotify_candidates(understanding.genre_hint, max_candidates=max_candidates),
            max_candidates,
        )

    fallback_used = False
    if not ranked and question_type != "trending_tracks":
        ranked = _fallback_representative_candidates(
            understanding.genre_hint,
            max_candidates=max_candidates,
        )
        fallback_used = bool(ranked)

    confidence, uncertainty_note = _candidate_confidence(len(ranked), searched=searched or bool(queries))
    if fallback_used:
        confidence = "PARTIAL"
        if question_type == "trending_tracks":
            uncertainty_note = (
                "Trusted-source search did not return exact recent artist-track candidates, "
                "so these are source-grounded representative tracks rather than verified current chart hits."
            )
        else:
            uncertainty_note = "Used source-grounded representative tracks because dynamic search found no exact candidates."
    elif question_type == "trending_tracks" and ranked:
        uncertainty_note = uncertainty_note or (
            "Current picks were assembled from trusted chart/playlist search and recent Spotify catalog signals."
        )
    elif question_type == "trending_tracks" and not ranked:
        uncertainty_note = (
            "Current chart/playlist search did not return verified recent track candidates. "
            "Configure web search and Spotify credentials for live recent recommendations."
        )
    return MusicRecommendationPlan(
        question_type=question_type,
        genre_hint=understanding.genre_hint,
        time_window=_time_window(query),
        candidate_tracks=ranked,
        source_queries=queries,
        confidence=confidence,  # type: ignore[arg-type]
        uncertainty_note=uncertainty_note,
    )
