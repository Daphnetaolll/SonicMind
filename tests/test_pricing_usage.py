from __future__ import annotations

from fastapi.testclient import TestClient

from backend.config.plans import EXTRA_PACKS, get_plan
from backend.main import app
from backend.services.token_service import create_access_token
from src.services.auth_service import AuthUser
from src.services.quota_service import QuotaStatus


client = TestClient(app)


def test_pricing_endpoint_returns_public_plan_limits() -> None:
    # Pricing is safe for logged-out users and should not include provider secrets.
    response = client.get("/api/pricing")

    assert response.status_code == 200
    data = response.json()
    assert [plan["code"] for plan in data["plans"]] == ["free", "creator", "pro"]
    assert data["plans"][0]["daily_limit"] == 5
    assert data["plans"][1]["monthly_limit"] == 200
    assert data["plans"][2]["spotify_limit"] == 15
    assert data["extra_packs"][0]["question_credits"] == EXTRA_PACKS[0].question_credits


def test_plan_config_matches_required_free_creator_pro_limits() -> None:
    # Central config is the source of truth for backend enforcement and frontend display.
    free = get_plan("free")
    creator = get_plan("creator")
    pro = get_plan("pro")

    assert free.daily_limit == 5
    assert free.max_answer_tokens == 400
    assert creator.monthly_limit == 200
    assert creator.save_history is True
    assert pro.monthly_limit == 1000
    assert pro.rag_top_k == 8
    assert pro.playlist_style is True


def test_chat_over_limit_blocks_before_answer_service(monkeypatch) -> None:
    # Over-limit requests must stop before expensive RAG, LLM, or Spotify work starts.
    user = AuthUser(id="user-over-limit", email="free@example.com", display_name=None, plan="free")
    quota = QuotaStatus(
        allowed=False,
        charge_type="none",
        remaining=0,
        remaining_daily_questions=0,
        current_plan="free",
        current_plan_name="Free",
        limit_message=get_plan("free").limit_message,
    )

    def should_not_run(**kwargs):
        raise AssertionError("answer service should not be called when quota is exhausted")

    monkeypatch.setattr("backend.main.knowledge_base_ready", lambda: True)
    monkeypatch.setattr("backend.main.get_user", lambda user_id: user if user_id == user.id else None)
    monkeypatch.setattr("backend.main.get_quota_status", lambda user_id: quota)
    monkeypatch.setattr("backend.main.answer_user_question", should_not_run)

    token = create_access_token(user_id=user.id)
    response = client.post(
        "/api/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={"question": "What is house music?"},
    )

    assert response.status_code == 402
    detail = response.json()["detail"]
    assert detail["code"] == "usage_limit_reached"
    assert detail["message"] == get_plan("free").limit_message
    assert detail["usage"]["remaining_daily_questions"] == 0
