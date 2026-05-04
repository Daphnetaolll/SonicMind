from __future__ import annotations

from typing import Any, Literal

from src.music.curated_recommendations import get_curated_recommendation
from src.music.dynamic_recommendation_discovery import discover_recommendation_for_genre
from src.music.generated_recommendations import get_generated_recommendation, save_generated_recommendation


RecommendationSource = Literal["curated", "generated"]


def get_recommendation_for_genre(genre_hint: str | None) -> tuple[dict[str, Any], RecommendationSource] | None:
    """
    Explanation:
    Recommendation quality should degrade in a controlled order:
    1. human-curated examples,
    2. cached trusted-source discoveries,
    3. fresh trusted-source discovery.
    Spotify is deliberately not part of this decision layer.
    """
    curated = get_curated_recommendation(genre_hint)
    if curated:
        return curated, "curated"

    generated = get_generated_recommendation(genre_hint)
    if generated:
        return generated, "generated"

    discovered = discover_recommendation_for_genre(genre_hint)
    if not discovered:
        return None

    try:
        save_generated_recommendation(genre_hint, discovered)
    except OSError:
        pass
    return discovered, "generated"
