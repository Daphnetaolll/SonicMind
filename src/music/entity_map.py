from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from src.music.schemas import EntityType, RelatedMusicEntity


ENTITY_MAP_PATH = Path("data/music/music_entity_map.json")


@lru_cache(maxsize=1)
def load_music_entity_map() -> dict[str, dict[str, Any]]:
    if not ENTITY_MAP_PATH.exists():
        return {}
    return json.loads(ENTITY_MAP_PATH.read_text(encoding="utf-8"))


def canonical_entity_name(name: str) -> str | None:
    lowered = name.strip().lower()
    for candidate in load_music_entity_map():
        if candidate.lower() == lowered:
            return candidate
    return None


def known_entity_names() -> list[str]:
    return sorted(load_music_entity_map(), key=len, reverse=True)


def get_entity_record(name: str) -> dict[str, Any] | None:
    canonical = canonical_entity_name(name)
    if not canonical:
        return None
    return load_music_entity_map().get(canonical)


def get_entity_type(name: str) -> EntityType | None:
    record = get_entity_record(name)
    if not record:
        return None
    return record.get("canonical_type")


def get_related_entities(name: str) -> list[RelatedMusicEntity]:
    record = get_entity_record(name)
    if not record:
        return []
    related: list[RelatedMusicEntity] = []
    for item in record.get("related_entities", []):
        related.append(
            RelatedMusicEntity(
                name=item.get("name", ""),
                type=item.get("type", "unknown"),
                relationship=item.get("relationship", ""),
            )
        )
    return [item for item in related if item.name]


def entities_by_genre_and_type(genre_hint: str | None, entity_type: EntityType) -> list[str]:
    if not genre_hint:
        return []
    wanted = genre_hint.lower()
    matches: list[str] = []
    for name, record in load_music_entity_map().items():
        if record.get("canonical_type") != entity_type:
            continue
        genres = [str(item).lower() for item in record.get("genres", [])]
        if any(wanted == genre for genre in genres):
            matches.append(name)
        elif len(wanted.split()) > 1 and any(wanted in genre or genre in wanted for genre in genres):
            matches.append(name)
    return matches


def related_entities_by_type(name: str, entity_type: EntityType) -> list[RelatedMusicEntity]:
    return [item for item in get_related_entities(name) if item.type == entity_type]
