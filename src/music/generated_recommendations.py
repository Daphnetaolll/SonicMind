from __future__ import annotations

import json
from pathlib import Path
from typing import Any


GENERATED_RECOMMENDATIONS_PATH = Path("data/music/generated_recommendations.json")


def _normalize_genre_key(genre_hint: str | None) -> str | None:
    if not genre_hint:
        return None
    key = " ".join(genre_hint.strip().lower().split())
    return key or None


def load_generated_recommendations() -> dict[str, dict[str, Any]]:
    """
    Explanation:
    Curated recommendations are still the highest-quality layer, but they cannot cover every music style.
    This cache stores trusted-source discoveries for unknown genres so repeated queries avoid another web search.
    """
    if not GENERATED_RECOMMENDATIONS_PATH.exists():
        return {}
    try:
        return json.loads(GENERATED_RECOMMENDATIONS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def get_generated_recommendation(genre_hint: str | None) -> dict[str, Any] | None:
    key = _normalize_genre_key(genre_hint)
    if not key:
        return None
    return load_generated_recommendations().get(key)


def save_generated_recommendation(genre_hint: str | None, record: dict[str, Any]) -> None:
    """
    Explanation:
    Generated recommendations are non-secret local cache data.
    Save failures are intentionally ignored by the caller so a read-only deployment can still answer normally.
    """
    key = _normalize_genre_key(genre_hint)
    if not key:
        return

    data = load_generated_recommendations()
    data[key] = record
    GENERATED_RECOMMENDATIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    GENERATED_RECOMMENDATIONS_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
