from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


CURATED_RECOMMENDATIONS_PATH = Path("data/music/curated_recommendations.json")


@lru_cache(maxsize=1)
def load_curated_recommendations() -> dict[str, dict[str, Any]]:
    """
    Explanation:
    Spotify keyword search produced playable but weak recommendations.
    This curated layer stores source-grounded music examples; Spotify only matches them to playable catalog items.
    """
    if not CURATED_RECOMMENDATIONS_PATH.exists():
        return {}
    return json.loads(CURATED_RECOMMENDATIONS_PATH.read_text(encoding="utf-8"))


def get_curated_recommendation(genre_hint: str | None) -> dict[str, Any] | None:
    """
    Explanation:
    Query understanding may produce either a canonical genre ("house music") or a shorthand ("house").
    Matching is intentionally strict so subgenres like "garage house" do not accidentally reuse broad "house" tracks.
    """
    if not genre_hint:
        return None

    data = load_curated_recommendations()
    key = genre_hint.strip().lower()
    candidates = [key]
    if key.endswith(" music"):
        candidates.append(key.removesuffix(" music").strip())
    else:
        candidates.append(f"{key} music")

    for candidate in candidates:
        record = data.get(candidate)
        if record and record.get("alias_for"):
            return data.get(str(record["alias_for"]).lower())
        if record:
            return record
    return None
