from __future__ import annotations

import re
from datetime import datetime

from src.evidence import EvidenceItem
from src.music.dynamic_recommendation_discovery import DISCOVERY_DOMAINS, TrackCandidate, extract_track_candidates_from_hits
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
        return [
            f'"{genre}" hottest tracks {year}',
            f'"{genre}" top tracks {year} chart',
            f'"{genre}" new tracks {year} Beatport Traxsource',
            f'"{genre}" best new tracks {year} DJ Mag Mixmag',
        ]
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
) -> MusicTrackCandidate:
    source_names = sorted(candidate.sources)
    return MusicTrackCandidate(
        title=candidate.title,
        artist=candidate.artist,
        score=round(candidate.score + _source_bonus(candidate.sources, question_type), 3),
        source_type=source_type,  # type: ignore[arg-type]
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
            for candidate in extract_track_candidates_from_hits(hits, _query_genre(understanding)):
                plan_candidates.append(
                    _to_plan_candidate(
                        candidate,
                        source_type="web_search",
                        question_type=question_type,
                        evidence=f"Extracted from trusted-source search query: {source_query}",
                    )
                )

    ranked = _merge_candidates(plan_candidates, max_candidates)
    confidence, uncertainty_note = _candidate_confidence(len(ranked), searched=searched or bool(queries))
    return MusicRecommendationPlan(
        question_type=question_type,
        genre_hint=understanding.genre_hint,
        time_window=_time_window(query),
        candidate_tracks=ranked,
        source_queries=queries,
        confidence=confidence,  # type: ignore[arg-type]
        uncertainty_note=uncertainty_note,
    )
