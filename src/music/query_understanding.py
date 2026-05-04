from __future__ import annotations

import re

from src.music.entity_map import get_entity_type, known_entity_names
from src.music.schemas import MusicEntityMention, QueryUnderstandingResult


GENRE_PATTERNS = (
    "melodic techno",
    "melodic house",
    "deep house",
    "progressive house",
    "electronic music",
    "house music",
    "techno",
    "house",
    "trance",
)


def _contains_any(text: str, markers: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in markers)


def _clean_genre_candidate(candidate: str) -> str:
    candidate = re.sub(r"\b(labels|artists|songs|tracks|albums|playlists)\b.*$", "", candidate).strip(" ?.")
    candidate = re.sub(r"^(the|some)\s+", "", candidate).strip()
    return candidate


def _detect_genre(query: str) -> str | None:
    # Extract a genre hint from recommendation, trend, definition, and bilingual query patterns.
    lowered = query.lower()
    match = re.search(
        r"(?:best|top|popular|recommendations for|recommend|hottest|hot|trending|latest|new|recent|about)\s+([a-z0-9&'’.\- ]+?)\s+(?:labels|artists|songs|tracks|music|albums|playlists)",
        lowered,
    )
    if match:
        candidate = _clean_genre_candidate(match.group(1))
        if candidate and candidate not in {"the", "some", "music"}:
            return candidate

    chinese_latin_match = re.search(
        r"(?:最近|最新|最火|热门).*?([a-z0-9&'’.\- ]+?)\s*(?:音乐|歌曲|歌|tracks?|songs?)",
        lowered,
    )
    if chinese_latin_match:
        candidate = _clean_genre_candidate(chinese_latin_match.group(1))
        if candidate and candidate not in {"the", "some", "music"}:
            return candidate

    definition_match = re.search(
        r"(?:what is|define|explain|tell me about)\s+([a-z0-9&'’.\- ]+?)\??$",
        lowered,
    )
    if definition_match:
        candidate = definition_match.group(1).strip(" ?.")
        if candidate and candidate not in {"it", "this", "that", "music"}:
            return candidate

    for genre in GENRE_PATTERNS:
        if genre in lowered:
            return genre
    return None


def _extract_known_entities(query: str) -> list[MusicEntityMention]:
    # Match curated entity names directly from the user query before evidence retrieval runs.
    lowered = query.lower()
    entities: list[MusicEntityMention] = []
    for name in known_entity_names():
        if name.lower() in lowered:
            entities.append(
                MusicEntityMention(
                    name=name,
                    type=get_entity_type(name) or "unknown",
                    confidence=0.92,
                )
            )
    return entities


def understand_query(query: str) -> QueryUnderstandingResult:
    # Classify the music task and decide whether Spotify cards should be displayed.
    lowered = query.lower()
    entities = _extract_known_entities(query)
    genre_hint = _detect_genre(query)

    is_comparison = _contains_any(lowered, ("difference between", "compare", "vs", "versus", "区别", "对比"))
    is_recommendation = _contains_any(
        lowered,
        ("best", "top", "popular", "recommend", "hot", "hottest", "trending", "latest", "new", "推荐", "最棒", "最好", "热门", "最火", "最新"),
    )

    # Route user intent into a primary entity type and display target for the music module.
    if is_comparison:
        intent = "genre_comparison" if _contains_any(lowered, ("genre", "style", "风格")) else "entity_comparison"
        primary_entity_type = entities[0].type if entities and entities[0].type != "unknown" else "ambiguous"
        display_target = "optional_representative_tracks"
        needs_spotify = True
    elif _contains_any(lowered, ("label", "labels", "厂牌")):
        intent = "label_recommendation" if is_recommendation else "label_profile"
        primary_entity_type = "label"
        display_target = "representative_tracks"
        needs_spotify = True
    elif _contains_any(lowered, ("artist", "artists", "producer", "dj", "艺人", "制作人")):
        intent = "artist_recommendation" if is_recommendation else "artist_profile"
        primary_entity_type = "artist"
        display_target = "artist_top_tracks"
        needs_spotify = True
    elif _contains_any(lowered, ("track", "tracks", "song", "songs", "music", "歌曲", "音乐", "歌")) and is_recommendation:
        intent = "track_recommendation"
        primary_entity_type = "track"
        display_target = "tracks"
        needs_spotify = True
    elif _contains_any(lowered, ("album", "albums", "专辑")):
        intent = "album_recommendation" if is_recommendation else "general_music_knowledge"
        primary_entity_type = "album"
        display_target = "albums"
        needs_spotify = True
    elif _contains_any(lowered, ("playlist", "playlists", "播放列表", "歌单")):
        intent = "playlist_discovery"
        primary_entity_type = "playlist"
        display_target = "playlists"
        needs_spotify = True
    elif _contains_any(lowered, ("what is", "define", "explain", "tell me about", "是什么", "介绍")):
        if genre_hint and (not entities or any(item.type == "genre" for item in entities)):
            intent = "genre_explanation"
            primary_entity_type = "genre"
            display_target = "optional_representative_tracks"
            needs_spotify = True
        elif entities:
            intent = "entity_profile"
            primary_entity_type = entities[0].type if entities[0].type != "unknown" else "ambiguous"
            display_target = "optional_representative_tracks"
            needs_spotify = True
        else:
            intent = "genre_explanation" if genre_hint else "general_music_knowledge"
            primary_entity_type = "genre" if genre_hint else "unknown"
            display_target = "optional_representative_tracks" if genre_hint else "none"
            needs_spotify = bool(genre_hint)
    else:
        intent = "general_music_knowledge"
        primary_entity_type = entities[0].type if entities else "unknown"
        display_target = "optional_representative_tracks" if entities else "none"
        needs_spotify = bool(entities)

    needs_resolution = primary_entity_type in {"unknown", "ambiguous"} or any(item.type in {"unknown", "ambiguous"} for item in entities)
    # Return a compact structured understanding that downstream retrieval and Spotify code can share.
    return QueryUnderstandingResult(
        intent=intent,
        primary_entity_type=primary_entity_type,
        genre_hint=genre_hint,
        entities=entities,
        needs_resolution=needs_resolution,
        needs_spotify=needs_spotify,
        spotify_display_target=display_target,
    )
