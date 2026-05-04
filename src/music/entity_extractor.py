from __future__ import annotations

import re
from collections import Counter

from src.evidence import EvidenceItem
from src.music.entity_map import (
    entities_by_genre_and_type,
    get_entity_record,
    get_related_entities,
    known_entity_names,
)
from src.music.entity_type_detector import resolve_music_entity
from src.music.schemas import (
    EntityType,
    MusicEntityMention,
    QueryUnderstandingResult,
    RankedMusicEntity,
    ResolvedMusicEntity,
)


LABEL_NAME_PATTERN = re.compile(
    r"\b([A-Z][A-Za-z0-9&'’.\- ]{1,42}\s(?:Records|Recordings|Music|Trax|Underground|Rhythm|Sound|Sounds|Works))\b"
)
ARTIST_NAME_PATTERN = re.compile(
    r"\b([A-Z][A-Za-z0-9&'’.\-]+(?:\s(?:[A-Z][A-Za-z0-9&'’.\-]+|of|de|van|von|and|&)){0,4})\b"
)
TRACK_TITLE_PATTERN = re.compile(r"Discogs result:\s*([^.;]+)")
NOISY_ENTITY_NAMES = {
    "MusicBrainz",
    "Discogs",
    "Resident Advisor",
    "Rate Your Music",
    "AllMusic",
    "Every Noise",
    "Spotify",
    "United States",
    "United Kingdom",
}


def _clean_entity_name(name: str) -> str:
    name = re.sub(r"\s+", " ", name).strip(" .,;:()[]{}\"'")
    return re.sub(r"\s+-\s+.*$", "", name).strip()


def _is_useful_entity_name(name: str) -> bool:
    if len(name) < 3 or len(name) > 60:
        return False
    if name in NOISY_ENTITY_NAMES:
        return False
    if name.lower() in {"result", "unknown", "official", "records", "recordings", "music"}:
        return False
    return bool(re.search(r"[A-Za-z]", name))


def _extract_label_like_names_from_evidence(evidence_text: str) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for match in LABEL_NAME_PATTERN.finditer(evidence_text):
        name = _clean_entity_name(match.group(1))
        key = name.lower()
        if not _is_useful_entity_name(name) or key in seen:
            continue
        seen.add(key)
        names.append(name)
    return names


def _entity_type_from_evidence(item: EvidenceItem, target_type: EntityType) -> EntityType:
    metadata_type = item.metadata.get("entity")
    if metadata_type == "recording":
        return "track"
    if metadata_type == "release-group":
        return "album"
    if metadata_type in {"artist", "label"}:
        return metadata_type
    return target_type


def _extract_discogs_field_values(text: str, field: str) -> list[str]:
    pattern = re.compile(rf"{field}:\s*([^.;]+)", re.IGNORECASE)
    values: list[str] = []
    for match in pattern.finditer(text):
        values.extend(_clean_entity_name(part) for part in match.group(1).split(","))
    return [value for value in values if _is_useful_entity_name(value)]


def _extract_names_for_type(
    query_understanding: QueryUnderstandingResult,
    evidence: list[EvidenceItem],
) -> list[MusicEntityMention]:
    # Pull entity candidates from official metadata first, then supplement with evidence text patterns.
    target_type = query_understanding.primary_entity_type
    mentions: list[MusicEntityMention] = []
    seen: set[str] = set()

    def add(name: str, entity_type: EntityType, confidence: float) -> None:
        clean_name = _clean_entity_name(name)
        key = clean_name.lower()
        if key in seen or not _is_useful_entity_name(clean_name):
            return
        seen.add(key)
        mentions.append(MusicEntityMention(name=clean_name, type=entity_type, confidence=confidence))

    for item in evidence:
        evidence_type = _entity_type_from_evidence(item, target_type)
        if (
            evidence_type == target_type
            and item.metadata.get("access_mode") == "official_api"
            and not (target_type == "label" and item.source_name.lower() == "discogs")
        ):
            add(item.title, evidence_type, 0.78)

        text = f"{item.title}. {item.snippet}. {item.full_text}"
        if target_type == "label":
            for label in _extract_discogs_field_values(text, "Labels"):
                add(label, "label", 0.76)
            for label in _extract_label_like_names_from_evidence(text):
                add(label, "label", 0.62)
        elif target_type == "artist":
            if item.metadata.get("entity") == "artist":
                add(item.title, "artist", 0.78)
        elif target_type == "track":
            if item.metadata.get("entity") == "recording":
                add(item.title, "track", 0.78)
            for title in TRACK_TITLE_PATTERN.findall(text):
                add(title, "track", 0.52)
        elif target_type == "album":
            if item.metadata.get("entity") == "release-group":
                add(item.title, "album", 0.78)
            for title in TRACK_TITLE_PATTERN.findall(text):
                add(title, "album", 0.46)
        elif target_type == "playlist":
            if "playlist" in text.lower():
                add(item.title, "playlist", 0.5)

    return mentions


def extract_candidate_entities(
    query_understanding: QueryUnderstandingResult,
    evidence: list[EvidenceItem],
) -> list[MusicEntityMention]:
    # Combine query mentions, curated maps, and evidence-derived names into one candidate list.
    candidates = list(query_understanding.entities)
    seen = {item.name.lower() for item in candidates}
    evidence_text = " ".join(f"{item.title} {item.snippet} {item.full_text}" for item in evidence).lower()

    for name in known_entity_names():
        if name.lower() in seen:
            continue
        if name.lower() in evidence_text:
            record = get_entity_record(name) or {}
            candidates.append(
                MusicEntityMention(
                    name=name,
                    type=record.get("canonical_type", "unknown"),
                    confidence=0.72,
                )
            )
            seen.add(name.lower())

    if not candidates and query_understanding.genre_hint:
        for name in entities_by_genre_and_type(query_understanding.genre_hint, query_understanding.primary_entity_type):
            record = get_entity_record(name) or {}
            candidates.append(
                MusicEntityMention(
                    name=name,
                    type=record.get("canonical_type", "unknown"),
                    confidence=0.68,
                )
            )

    if query_understanding.primary_entity_type == "label":
        raw_evidence_text = " ".join(f"{item.title} {item.snippet} {item.full_text}" for item in evidence)
        for name in _extract_label_like_names_from_evidence(raw_evidence_text):
            key = name.lower()
            if key not in seen:
                candidates.append(MusicEntityMention(name=name, type="label", confidence=0.58))
                seen.add(key)

    for mention in _extract_names_for_type(query_understanding, evidence):
        if mention.name.lower() not in seen:
            candidates.append(mention)
            seen.add(mention.name.lower())

    return candidates


def resolve_candidate_entities(
    query_understanding: QueryUnderstandingResult,
    evidence: list[EvidenceItem],
) -> list[ResolvedMusicEntity]:
    # Resolve each mention against curated data and evidence before ranking.
    return [
        resolve_music_entity(
            mention,
            evidence=evidence,
            genre_hint=query_understanding.genre_hint,
        )
        for mention in extract_candidate_entities(query_understanding, evidence)
    ]


def _target_entity_type(query_understanding: QueryUnderstandingResult) -> EntityType:
    if query_understanding.primary_entity_type in {"label", "artist", "track", "album", "playlist", "genre"}:
        return query_understanding.primary_entity_type
    return "unknown"


def rank_music_entities(
    query_understanding: QueryUnderstandingResult,
    resolved_entities: list[ResolvedMusicEntity],
    evidence: list[EvidenceItem],
    *,
    max_results: int = 6,
) -> list[RankedMusicEntity]:
    # Rank entities by target type, evidence mentions, genre relevance, and curated source confidence.
    target_type = _target_entity_type(query_understanding)
    entity_names: list[str] = []

    if target_type != "unknown":
        entity_names.extend(item.name for item in resolved_entities if item.resolved_type == target_type)
        if query_understanding.genre_hint:
            entity_names.extend(entities_by_genre_and_type(query_understanding.genre_hint, target_type))

    if target_type == "genre" and query_understanding.genre_hint:
        entity_names.append(query_understanding.genre_hint)

    if not entity_names and target_type in {"track", "album", "playlist"}:
        return []

    if not entity_names:
        entity_names.extend(item.name for item in resolved_entities)

    evidence_text = " ".join(f"{item.title} {item.snippet} {item.full_text}" for item in evidence).lower()
    source_mentions = Counter()
    for item in evidence:
        item_text = f"{item.title} {item.snippet} {item.full_text}".lower()
        for name in entity_names:
            if name.lower() in item_text:
                source_mentions[name] += 1

    counts = Counter()
    ranked: list[RankedMusicEntity] = []
    seen: set[str] = set()

    for name in entity_names:
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        counts[name] = evidence_text.count(key)
        record = get_entity_record(name) or {}
        entity_type = record.get("canonical_type") or next(
            (item.resolved_type for item in resolved_entities if item.name.lower() == key),
            target_type,
        )
        score = 0.55 + min(0.25, counts[name] * 0.05)
        score += min(0.16, source_mentions[name] * 0.04)
        if query_understanding.genre_hint and query_understanding.genre_hint.lower() in [
            str(item).lower() for item in record.get("genres", [])
        ]:
            score += 0.15
        if record:
            score += 0.1
        if not record and counts[name]:
            score += 0.06

        ranked.append(
            RankedMusicEntity(
                name=name,
                type=entity_type,
                score=min(score, 0.98),
                reason="Ranked from trusted evidence, source mentions, genre relevance, and curated music data.",
                genres=list(record.get("genres", [])),
                related_entities=get_related_entities(name),
                sources=list(record.get("sources", [])),
            )
        )

    ranked.sort(key=lambda item: item.score, reverse=True)
    return ranked[:max_results]
