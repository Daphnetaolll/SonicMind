from __future__ import annotations

import re

from src.music.entity_map import get_entity_type, known_entity_names
from src.music.schemas import MusicEntityMention, QueryUnderstandingResult


GENRE_PATTERNS = (
    "electronic dance music",
    "ambient techno",
    "minimal techno",
    "melodic techno",
    "melodic house",
    "acid house",
    "deep house",
    "progressive house",
    "drum and bass",
    "drum & bass",
    "dance music",
    "electronic music",
    "house music",
    "techno",
    "house",
    "trance",
    "dnb",
    "edm",
)
GENRE_ALIASES = {
    "dance": "electronic dance music",
    "dance music": "electronic dance music",
    "edm": "electronic dance music",
    "drum & bass": "drum and bass",
    "dnb": "drum and bass",
}
GENRE_QUERY_FILLERS = {
    "best",
    "current",
    "currently",
    "hot",
    "hottest",
    "latest",
    "me",
    "new",
    "popular",
    "recent",
    "recently",
    "some",
    "top",
    "trending",
}
ARTIST_PROFILE_PATTERNS = (
    r"\bwho(?:\s+is|['’]s)\s+(?P<name>[^?!.]+)",
    r"\btell\s+me\s+about\s+(?P<name>[^?!.]+)",
    r"\bwhat\s+do\s+you\s+know\s+about\s+(?P<name>[^?!.]+)",
    r"(?:介绍一下|介紹一下|介绍|介紹|谁是|誰是)\s*(?P<name>[A-Za-z0-9&'’.\- ]{2,80})",
)
ALBUM_ARTIST_PATTERNS = (
    r"\b(?P<name>[A-Za-z0-9&'’.\- ]{2,80})['’]s\s+(?:popular\s+|best\s+|top\s+)?albums?\b",
    r"\b(?:popular|best|top|recommend(?:ed)?)\s+albums?\s+(?:by|from)\s+(?P<name>[A-Za-z0-9&'’.\- ]{2,80})",
    r"\balbums?\s+(?:by|from)\s+(?P<name>[A-Za-z0-9&'’.\- ]{2,80})",
)
ENTITY_NAME_PARTICLES = {"and", "of", "de", "del", "da", "van", "von", "&"}

MOOD_GENRE_HINTS = (
    (("dark", "minimal", "hypnotic", "underground", "暗黑", "极简", "極簡", "深夜", "凌晨"), "minimal techno"),
    (("fast", "late-night", "late night", "energetic", "driving", "peak-time", "peak time"), "techno"),
    (("study", "studying", "focus", "学习", "ambient", "soft"), "ambient electronic music"),
    (("deep", "warm bassline", "warm basslines", "温暖", "groovy"), "deep house"),
    (("emotional", "vocal", "vocals", "melodic", "情绪", "人声"), "melodic house"),
    (("sunset", "not too aggressive", "dancing", "warm-up", "warmup"), "house"),
    (("fashion show", "runway", "时装秀"), "electronic music"),
)


def _contains_any(text: str, markers: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in markers)


def _clean_genre_candidate(candidate: str) -> str:
    candidate = re.sub(r"\b(labels|artists|songs|tracks|albums|playlists)\b.*$", "", candidate).strip(" ?.")
    words = candidate.split()
    cleaned_words = [word for word in words if word.lower().strip(" ?.!") not in GENRE_QUERY_FILLERS]
    candidate = " ".join(cleaned_words).strip()
    return candidate


def _known_genre_in_text(text: str) -> str | None:
    lowered = text.lower()
    if "tehcno" in lowered:
        return "techno"
    for genre in GENRE_PATTERNS:
        if genre in lowered:
            return GENRE_ALIASES.get(genre, genre)
    if "浩室" in text:
        return "house"
    if "电子" in text or "電子" in text:
        return "electronic music"
    if lowered.strip() in GENRE_ALIASES:
        return GENRE_ALIASES[lowered.strip()]
    return None


def _display_entity_name(candidate: str) -> str:
    # Preserve user capitalization when present; otherwise make extracted artist names readable.
    if any(char.isupper() for char in candidate):
        return candidate

    words: list[str] = []
    for word in candidate.split():
        lowered = word.lower()
        if lowered in ENTITY_NAME_PARTICLES:
            words.append(lowered)
        elif lowered == "dj":
            words.append("DJ")
        else:
            words.append(word[:1].upper() + word[1:])
    return " ".join(words)


def _clean_artist_candidate(candidate: str) -> str | None:
    # Strip prompt scaffolding without removing artist names such as "DJ Seinfeld".
    cleaned = re.sub(r"\s+", " ", candidate).strip(" ?.!,:;\"'")
    cleaned = re.sub(r"^(?:recommend|recommand|show|give|find|play)(?:\s+me)?\s+", "", cleaned, flags=re.I)
    cleaned = re.sub(r"^(?:the\s+artist\s+|artist\s+|producer\s+)", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\s+(?:in|from|for)\s+(?:music|techno|house|edm|electronic music).*$", "", cleaned, flags=re.I)
    cleaned = cleaned.strip(" ?.!,:;\"'")
    if not cleaned or len(cleaned) < 3:
        return None

    lowered = cleaned.lower()
    if lowered in {"album", "artist", "producer", "dj", "music", "this", "that", "it"}:
        return None
    if _known_genre_in_text(cleaned):
        return None
    if re.search(r"\b(?:album|albums|genre|style|scene|music|track|tracks|song|songs)\b", lowered):
        return None
    if not re.search(r"[A-Za-z]", cleaned):
        return None
    return _display_entity_name(cleaned)


def _detect_artist_from_patterns(query: str, patterns: tuple[str, ...]) -> str | None:
    # Keep artist-name extraction centralized so profile and album prompts resolve consistently.
    for pattern in patterns:
        match = re.search(pattern, query, flags=re.I)
        if not match:
            continue
        candidate = _clean_artist_candidate(match.group("name"))
        if candidate:
            return candidate
    return None


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
            return _known_genre_in_text(candidate) or candidate

    chinese_latin_match = re.search(
        r"(?:最近|最新|最火|热门).*?([a-z0-9&'’.\- ]+?)\s*(?:音乐|歌曲|歌|tracks?|songs?)",
        lowered,
    )
    if chinese_latin_match:
        candidate = _clean_genre_candidate(chinese_latin_match.group(1))
        if candidate and candidate not in {"the", "some", "music"}:
            return _known_genre_in_text(candidate) or candidate

    definition_match = re.search(
        r"(?:what is|define|explain|tell me about)\s+([a-z0-9&'’.\- ]+?)\??$",
        lowered,
    )
    if definition_match:
        candidate = definition_match.group(1).strip(" ?.")
        known_genre = _known_genre_in_text(candidate)
        if known_genre:
            if "difference between" in candidate or "relationship between" in candidate:
                return known_genre
            return candidate if candidate.endswith(known_genre) else known_genre
        if candidate and candidate not in {"it", "this", "that", "music"} and _contains_any(
            candidate,
            ("genre", "style", "scene"),
        ):
            return candidate

    return _known_genre_in_text(query)


def _detect_mood_genre(query: str) -> str | None:
    """
    Explanation:
    Recommendation prompts often describe a mood instead of naming a genre.
    Mapping common portfolio-demo moods to broad electronic styles gives the
    Spotify planner useful search terms without pretending we know the user's taste perfectly.
    """
    lowered = query.lower()
    for markers, genre in MOOD_GENRE_HINTS:
        if any(marker in lowered for marker in markers):
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
    genre_hint = _detect_mood_genre(query) or _detect_genre(query)
    profile_artist_name = _detect_artist_from_patterns(query, ARTIST_PROFILE_PATTERNS) if not genre_hint else None
    album_artist_name = _detect_artist_from_patterns(query, ALBUM_ARTIST_PATTERNS)
    detected_artist_name = album_artist_name or profile_artist_name
    if detected_artist_name and not any(item.name.lower() == detected_artist_name.lower() for item in entities):
        entities.append(MusicEntityMention(name=detected_artist_name, type="artist", confidence=0.66))

    is_comparison = _contains_any(lowered, ("difference between", "compare", "vs", "versus", "区别", "对比"))
    is_recommendation = _contains_any(
        lowered,
        (
            "best",
            "top",
            "popular",
            "recommend",
            "build me",
            "give me",
            "make me",
            "create",
            "i want",
            "listen to",
            "hot",
            "hottest",
            "trending",
            "latest",
            "new",
            "推荐",
            "帮我推荐",
            "最棒",
            "最好",
            "热门",
            "最火",
            "最新",
        ),
    )
    is_mood_request = bool(genre_hint) and _contains_any(
        lowered,
        ("i want", "give me", "something", "listen to", "for dancing", "for a", "music for", "适合", "想听"),
    )
    explicit_track_request = _contains_any(lowered, ("track", "tracks", "song", "songs", "歌曲", "歌"))
    playlist_style_request = _contains_any(
        lowered,
        (
            "playlist",
            "playlists",
            "dj set",
            "warm-up",
            "warmup",
            "peak-time",
            "peak time",
            "closing set",
            "set order",
            "starts soft",
            "becomes energetic",
            "播放列表",
            "歌单",
        ),
    )

    # Route user intent into a primary entity type and display target for the music module.
    if is_comparison:
        intent = "genre_comparison" if _contains_any(lowered, ("genre", "style", "风格")) else "entity_comparison"
        primary_entity_type = entities[0].type if entities and entities[0].type != "unknown" else "ambiguous"
        display_target = "optional_representative_tracks"
        needs_spotify = True
    elif playlist_style_request and not explicit_track_request and (is_recommendation or genre_hint):
        # Playlist and DJ-set prompts should produce playable track candidates, not generic DJ profile cards.
        intent = "playlist_discovery"
        primary_entity_type = "playlist"
        display_target = "tracks"
        needs_spotify = True
    elif is_mood_request:
        intent = "track_recommendation"
        primary_entity_type = "track"
        display_target = "tracks"
        needs_spotify = True
    elif _contains_any(lowered, ("label", "labels", "厂牌")):
        intent = "label_recommendation" if is_recommendation else "label_profile"
        primary_entity_type = "label"
        display_target = "representative_tracks"
        needs_spotify = True
    elif explicit_track_request and is_recommendation:
        # "DJ" can mean an artist in profile questions, but "recommend songs for a DJ set"
        # should route to playable track cards with Spotify timeline controls.
        intent = "track_recommendation"
        primary_entity_type = "track"
        display_target = "tracks"
        needs_spotify = True
    elif album_artist_name and _contains_any(lowered, ("album", "albums", "专辑")):
        intent = "album_recommendation"
        primary_entity_type = "artist"
        display_target = "albums"
        needs_spotify = True
    elif profile_artist_name:
        intent = "artist_profile"
        primary_entity_type = "artist"
        display_target = "artist_top_tracks"
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
    elif _contains_any(lowered, ("what is", "define", "explain", "tell me about", "是什么", "什么是", "介紹", "介绍")):
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
