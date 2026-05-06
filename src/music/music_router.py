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
    *,
    spotify_limit: int = 8,
    playlist_style: bool = False,
) -> MusicRoutingResult:
    # Build the shared music understanding artifacts before deciding whether Spotify should render.
    understanding = understand_query(query)
    resolved_entities = resolve_candidate_entities(understanding, evidence)
    ranked_entities = rank_music_entities(understanding, resolved_entities, evidence)
    recommendation_plan = build_music_recommendation_plan(
        query,
        understanding,
        evidence,
        max_candidates=spotify_limit,
    )

    # Non-Pro plans still get normal music answers, but playlist-style Spotify discovery stays gated.
    if understanding.intent == "playlist_discovery" and not playlist_style:
        understanding.needs_spotify = False

    # Spotify lookup is optional; text answers and diagnostics should still work without credentials.
    spotify_error = None
    spotify_cards = []
    if understanding.needs_spotify:
        if spotify_credentials_ready():
            try:
                spotify_cards = build_spotify_cards_for_entities(
                    ranked_entities,
                    understanding,
                    recommendation_plan=recommendation_plan,
                    max_cards=spotify_limit,
                )
            except Exception as exc:
                spotify_error = "Spotify recommendation temporarily unavailable."
        else:
            spotify_error = "Spotify recommendation temporarily unavailable."

    return MusicRoutingResult(
        query_understanding=understanding,
        resolved_entities=resolved_entities,
        ranked_entities=ranked_entities,
        recommendation_plan=recommendation_plan,
        spotify_cards=spotify_cards,
        spotify_error=spotify_error,
    )
