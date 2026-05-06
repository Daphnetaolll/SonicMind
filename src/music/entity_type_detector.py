from __future__ import annotations

from collections import Counter

from src.evidence import EvidenceItem
from src.music.entity_map import get_entity_record, get_related_entities
from src.music.schemas import MusicEntityMention, PossibleEntityType, ResolvedMusicEntity


TYPE_MARKERS = {
    "label": ("label", "record label", "imprint", "厂牌"),
    "artist": ("artist", "producer", "dj", "duo", "艺人", "制作人"),
    "track": ("track", "song", "single", "歌曲"),
    "genre": ("genre", "style", "sound", "风格"),
    "album": ("album", "lp", "专辑"),
    "playlist": ("playlist", "歌单", "播放列表"),
}


def _evidence_type_votes(name: str, evidence: list[EvidenceItem]) -> Counter:
    # Count nearby type markers in retrieved evidence to resolve ambiguous music entity mentions.
    votes: Counter = Counter()
    lowered_name = name.lower()
    for item in evidence:
        haystack = f"{item.title} {item.snippet} {item.full_text}".lower()
        if lowered_name not in haystack:
            continue
        for entity_type, markers in TYPE_MARKERS.items():
            if any(marker in haystack for marker in markers):
                votes[entity_type] += 1
    return votes


def resolve_music_entity(
    mention: MusicEntityMention,
    *,
    evidence: list[EvidenceItem],
    genre_hint: str | None = None,
) -> ResolvedMusicEntity:
    # Blend curated metadata, query hints, and evidence votes into one resolved entity type.
    possible: list[PossibleEntityType] = []
    record = get_entity_record(mention.name)

    if record:
        possible.append(
            PossibleEntityType(
                type=record.get("canonical_type", "unknown"),
                confidence=0.9,
                source="curated_map",
            )
        )

    if mention.type not in {"unknown", "ambiguous"}:
        possible.append(PossibleEntityType(type=mention.type, confidence=max(mention.confidence, 0.65), source="query"))

    votes = _evidence_type_votes(mention.name, evidence)
    for entity_type, count in votes.most_common():
        possible.append(PossibleEntityType(type=entity_type, confidence=min(0.78, 0.45 + (count * 0.12)), source="evidence"))

    if not possible:
        possible.append(PossibleEntityType(type="unknown", confidence=0.25, source="fallback"))

    best = max(possible, key=lambda item: item.confidence)
    genres = list(record.get("genres", [])) if record else ([genre_hint] if genre_hint else [])
    sources = list(record.get("sources", [])) if record else []

    return ResolvedMusicEntity(
        name=mention.name,
        resolved_type=best.type,
        confidence=best.confidence,
        possible_types=possible,
        genres=genres,
        related_entities=get_related_entities(mention.name),
        sources=sources,
    )
