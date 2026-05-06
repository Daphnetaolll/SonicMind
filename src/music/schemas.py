from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


# Literal aliases keep music routing state constrained across extractor, planner, and Spotify code.
Intent = Literal[
    "label_recommendation",
    "artist_recommendation",
    "track_recommendation",
    "genre_explanation",
    "genre_comparison",
    "album_recommendation",
    "artist_profile",
    "track_analysis",
    "label_profile",
    "playlist_discovery",
    "entity_profile",
    "entity_comparison",
    "general_music_knowledge",
]

EntityType = Literal["label", "artist", "track", "genre", "album", "playlist", "unknown", "ambiguous"]
SpotifyDisplayTarget = Literal[
    "none",
    "representative_tracks",
    "artist_top_tracks",
    "tracks",
    "albums",
    "playlists",
    "optional_representative_tracks",
]
RecommendationQuestionType = Literal[
    "none",
    "trending_tracks",
    "track_recommendation",
    "representative_tracks",
    "artist_recommendation",
    "label_recommendation",
    "playlist_discovery",
]
RecommendationSourceType = Literal["evidence", "web_search", "generated_cache", "curated", "spotify_fallback"]


# Query-understanding dataclasses describe what the user asked before retrieval or Spotify lookup.
@dataclass
class MusicEntityMention:
    name: str
    type: EntityType = "unknown"
    confidence: float = 0.0
    artist_hint: str | None = None


@dataclass
class QueryUnderstandingResult:
    intent: Intent
    primary_entity_type: EntityType
    genre_hint: str | None
    entities: list[MusicEntityMention]
    needs_resolution: bool
    needs_spotify: bool
    spotify_display_target: SpotifyDisplayTarget


# Entity-resolution dataclasses preserve candidate uncertainty for UI diagnostics and ranking.
@dataclass
class PossibleEntityType:
    type: EntityType
    confidence: float
    source: str


@dataclass
class RelatedMusicEntity:
    name: str
    type: EntityType
    relationship: str


@dataclass
class ResolvedMusicEntity:
    name: str
    resolved_type: EntityType
    confidence: float
    possible_types: list[PossibleEntityType]
    genres: list[str] = field(default_factory=list)
    related_entities: list[RelatedMusicEntity] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)


@dataclass
class RankedMusicEntity:
    name: str
    type: EntityType
    score: float
    reason: str
    genres: list[str] = field(default_factory=list)
    related_entities: list[RelatedMusicEntity] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)


@dataclass
class SpotifyCard:
    # Cards contain only browser-safe Spotify display data, never provider credentials.
    card_type: Literal["artist", "track", "album", "playlist"]
    title: str
    subtitle: str
    spotify_url: str
    spotify_id: str | None = None
    image_url: str | None = None
    embed_url: str | None = None
    popularity: int | None = None
    source_entity: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass
class MusicTrackCandidate:
    # Track candidates carry source provenance so generated recommendations stay explainable.
    title: str
    artist: str
    score: float
    source_type: RecommendationSourceType
    source_names: list[str] = field(default_factory=list)
    source_urls: list[str] = field(default_factory=list)
    evidence: str = ""
    reason: str = ""


@dataclass
class MusicRecommendationPlan:
    # The plan coordinates answer text and Spotify cards around the same source-grounded candidates.
    question_type: RecommendationQuestionType
    genre_hint: str | None
    time_window: str | None
    candidate_tracks: list[MusicTrackCandidate] = field(default_factory=list)
    source_queries: list[str] = field(default_factory=list)
    confidence: Literal["CONFIDENT", "PARTIAL", "UNCERTAIN"] = "UNCERTAIN"
    uncertainty_note: str | None = None


@dataclass
class MusicRoutingResult:
    # Music routing packages every music-specific artifact the RAG pipeline exposes to the UI.
    query_understanding: QueryUnderstandingResult
    resolved_entities: list[ResolvedMusicEntity]
    ranked_entities: list[RankedMusicEntity]
    recommendation_plan: MusicRecommendationPlan
    spotify_cards: list[SpotifyCard]
    spotify_error: str | None = None
