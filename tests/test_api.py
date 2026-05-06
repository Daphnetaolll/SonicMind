from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

from fastapi.testclient import TestClient

from backend.main import app
from backend.services.chat_service import ChatServiceResult
from backend.services.token_service import create_access_token
from src.services.auth_service import AuthUser
from src.services.quota_service import QuotaStatus


client = TestClient(app)


@dataclass
class FakeRagResult:
    # The API serializer only needs this subset of the full RAG result for endpoint tests.
    answer: str
    certainty: str
    uncertainty_note: str | None
    citations: list
    used_evidence: list
    route_steps: list[str]
    query_understanding: object
    ranked_entities: list
    spotify_cards: list
    updated_chat_history: list


def test_health_endpoint_reports_ok(monkeypatch) -> None:
    # Patch readiness so the health test focuses on response shape instead of local artifacts.
    monkeypatch.setattr("backend.main.knowledge_base_ready", lambda: True)

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "sonicmind-api",
        "knowledge_base_ready": True,
    }


def test_chat_endpoint_returns_serialized_rag_result(monkeypatch) -> None:
    # Build lightweight service objects so the endpoint contract can be tested without running retrieval.
    user = AuthUser(id="user-1", email="daphne@example.com", display_name="Daphne")
    quota = QuotaStatus(
        allowed=True,
        charge_type="free",
        remaining=5,
        subscription_id=None,
        period_start=None,
        period_end=None,
    )
    remaining_quota = QuotaStatus(
        allowed=True,
        charge_type="free",
        remaining=4,
        subscription_id=None,
        period_start=None,
        period_end=None,
    )

    def fake_answer_user_question(**kwargs):
        # Assert the endpoint passes authenticated user and trimmed question into the service layer.
        assert kwargs["user_id"] == "user-1"
        assert kwargs["question"] == "What is house music?"
        return ChatServiceResult(
            result=FakeRagResult(
                answer="House music is a Chicago-born form of electronic dance music.",
                certainty="CONFIDENT",
                uncertainty_note=None,
                citations=[
                    SimpleNamespace(
                        number=1,
                        title="House Music",
                        source_type="local",
                        source_name="House.txt",
                        url=None,
                    )
                ],
                used_evidence=[
                    SimpleNamespace(
                        rank=1,
                        source_type="local",
                        source_name="House.txt",
                        title="House Music",
                        snippet="House music emerged in Chicago.",
                        full_text="House music is a style of electronic dance music.",
                        retrieval_score=0.91,
                        trust_level="high",
                        url=None,
                        metadata={},
                    )
                ],
                route_steps=["local:sufficient"],
                query_understanding=SimpleNamespace(
                    intent="genre_explanation",
                    primary_entity_type="genre",
                    genre_hint="house",
                    needs_spotify=False,
                    spotify_display_target="none",
                ),
                ranked_entities=[],
                spotify_cards=[],
                updated_chat_history=[
                    SimpleNamespace(
                        user="What is house music?",
                        assistant="House music is a Chicago-born form of electronic dance music.",
                    )
                ],
            ),
            remaining_quota=remaining_quota,
        )

    monkeypatch.setattr("backend.main.knowledge_base_ready", lambda: True)
    monkeypatch.setattr("backend.main.get_user", lambda user_id: user if user_id == "user-1" else None)
    monkeypatch.setattr("backend.main.get_quota_status", lambda user_id: quota)
    monkeypatch.setattr("backend.main.answer_user_question", fake_answer_user_question)

    token = create_access_token(user_id="user-1")
    # A valid token should produce a serialized answer, source list, music fields, and updated quota.
    response = client.post(
        "/api/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={"question": "What is house music?"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["answer"] == "House music is a Chicago-born form of electronic dance music."
    assert data["remaining_questions"] == 4
    assert data["sources"][0]["title"] == "House Music"
    assert data["query_understanding"]["genre_hint"] == "house"
    assert data["spotify_error"] is None


def test_login_returns_clean_error_when_backend_storage_is_unavailable(monkeypatch) -> None:
    # Storage failures should be sanitized before returning them to browser clients.
    def unavailable_login(email, password):
        raise ValueError("Missing DATABASE_URL.")

    monkeypatch.setattr("backend.main.sign_in_user", unavailable_login)

    response = client.post(
        "/api/login",
        json={"email": "nobody@example.com", "password": "wrong-password"},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Account or quota storage is unavailable right now. Please try again shortly."
