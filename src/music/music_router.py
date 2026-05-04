from __future__ import annotations

from src.evidence import EvidenceItem
from src.integrations.spotify_client import build_spotify_cards_for_entities, spotify_credentials_ready
from src.music.entity_extractor import rank_music_entities, resolve_candidate_entities
from src.music.music_recommendation_planner import build_music_recommendation_plan
from src.music.query_understanding import understand_query
from src.music.schemas import MusicRoutingResult


def build_music_response(
    query: str,
    answer: str,
    evidence: list[EvidenceItem],
) -> MusicRoutingResult:
    understanding = understand_query(query)
    resolved_entities = resolve_candidate_entities(understanding, evidence)
    ranked_entities = rank_music_entities(understanding, resolved_entities, evidence)
    recommendation_plan = build_music_recommendation_plan(query, understanding, evidence)

    spotify_error = None
    spotify_cards = []
    if understanding.needs_spotify:
        if spotify_credentials_ready():
            try:
                spotify_cards = build_spotify_cards_for_entities(
                    ranked_entities,
                    understanding,
                    recommendation_plan=recommendation_plan,
                )
            except Exception as exc:
                spotify_error = str(exc)
        else:
            spotify_error = "Spotify credentials are not configured."

    return MusicRoutingResult(
        query_understanding=understanding,
        resolved_entities=resolved_entities,
        ranked_entities=ranked_entities,
        recommendation_plan=recommendation_plan,
        spotify_cards=spotify_cards,
        spotify_error=spotify_error,
    )
