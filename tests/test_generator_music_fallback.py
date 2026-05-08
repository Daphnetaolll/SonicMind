from __future__ import annotations

import json

from src.evidence import EvidenceAssessment, EvidenceItem
from src.generator import LLMConfig, synthesize_answer
from src.music.music_router import build_music_response


def test_synthesis_replaces_generic_recent_dance_answer_with_track_candidates(monkeypatch) -> None:
    # Recommendation text should stay aligned with the structured track plan passed to Spotify.
    monkeypatch.setattr("src.music.music_recommendation_planner.search_web", lambda *_args, **_kwargs: [])

    def fake_call_chat_completion(**_kwargs):
        return json.dumps(
            {
                "answer": (
                    "I couldn't find specific recent popular dance music tracks to recommend. "
                    "However, house music is a prominent genre in the dance music scene."
                ),
                "certainty": "PARTIAL",
                "uncertainty_note": "The available evidence was incomplete.",
                "citations": [1],
            }
        )

    monkeypatch.setattr("src.generator.call_chat_completion", fake_call_chat_completion)

    query = "recommend me some popular dance music recently"
    evidence = [
        EvidenceItem(
            rank=1,
            source_type="local",
            source_name="SonicMind KB",
            title="House music overview",
            snippet="House music is a style of electronic dance music.",
            full_text="House music originated in Chicago and became foundational to dance music.",
            retrieval_score=0.7,
            trust_level="medium",
        )
    ]
    assessment = EvidenceAssessment(
        label="PARTIAL",
        reasons=["Evidence does not directly list recent dance tracks."],
        evidence_count=1,
        top_score=0.7,
        keyword_coverage=0.4,
    )
    music_routing = build_music_response(query, "", evidence, spotify_limit=5)

    synthesis = synthesize_answer(
        query,
        evidence,
        assessment,
        config=LLMConfig(api_key="test", model="test"),
        music_routing=music_routing,
    )

    assert "Daft Punk - One More Time" in synthesis.answer
    assert "source-grounded representative picks" in synthesis.answer
    assert "house music is a prominent genre" not in synthesis.answer
    assert synthesis.certainty == "PARTIAL"
