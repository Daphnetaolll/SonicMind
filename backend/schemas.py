from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from backend.config.plans import ExtraPackConfig, PlanConfig
from src.services.auth_service import AuthUser
from src.services.quota_service import QuotaStatus


# Small auth and health payloads define the public API surface used by the React shell.
class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    app_env: str
    sonicmind_mode: str
    retrieval_backend: str
    knowledge_base_ready: bool
    semantic_retrieval_ready: bool
    local_embedding_enabled: bool
    reranker_enabled: bool
    rag_load_on_startup: bool
    fallback_mode: str
    heavy_dependencies_available: dict[str, bool]


class LoginRequest(BaseModel):
    email: str
    password: str


class RegisterRequest(BaseModel):
    email: str
    password: str
    confirm_password: str
    display_name: str | None = None


class UserResponse(BaseModel):
    id: str
    email: str
    display_name: str | None = None
    plan: str = "free"
    subscription_status: str = "active"


class AuthResponse(BaseModel):
    token: str
    token_type: Literal["bearer"] = "bearer"
    user: UserResponse


class PlanFeatureResponse(BaseModel):
    max_answer_tokens: int
    rag_top_k: int
    spotify_limit: int
    save_history: bool
    favorites: bool
    playlist_style: bool


class UsageStatusResponse(BaseModel):
    current_plan: str
    current_plan_name: str
    price_label: str
    remaining_questions: int
    remaining_daily_questions: int | None = None
    remaining_monthly_questions: int | None = None
    extra_question_credits: int
    limit_message: str | None = None
    features: PlanFeatureResponse


class AccountStatusResponse(BaseModel):
    user: UserResponse
    usage: UsageStatusResponse


class PlanResponse(BaseModel):
    code: str
    name: str
    price_label: str
    daily_limit: int | None = None
    monthly_limit: int | None = None
    max_answer_tokens: int
    rag_top_k: int
    spotify_limit: int
    save_history: bool
    favorites: bool
    playlist_style: bool


class ExtraPackResponse(BaseModel):
    code: str
    price_label: str
    question_credits: int
    expires_after_months: int


class PricingResponse(BaseModel):
    plans: list[PlanResponse]
    extra_packs: list[ExtraPackResponse]


class ChatTurnRequest(BaseModel):
    user: str
    assistant: str


class ChatRequest(BaseModel):
    # Constrain retrieval knobs at the API boundary so the backend cannot receive runaway values.
    question: str
    chat_history: list[ChatTurnRequest] = Field(default_factory=list)
    topk: int = Field(default=3, ge=1, le=8)
    max_history_turns: int = Field(default=3, ge=1, le=5)


# Response models mirror the inspector panels: citations, sources, music understanding, and Spotify cards.
class ChatTurnResponse(BaseModel):
    user: str
    assistant: str


class CitationResponse(BaseModel):
    number: int
    title: str
    source_type: str
    source_name: str
    url: str | None = None


class SourceResponse(BaseModel):
    rank: int
    source_type: str
    source_name: str
    title: str
    snippet: str
    full_text: str
    retrieval_score: float
    trust_level: str
    url: str | None = None
    metadata: dict[str, str] = Field(default_factory=dict)


class QueryUnderstandingResponse(BaseModel):
    intent: str
    primary_entity_type: str
    genre_hint: str | None = None
    needs_spotify: bool
    spotify_display_target: str


class RelatedEntityResponse(BaseModel):
    name: str
    type: str
    relationship: str


class RankedEntityResponse(BaseModel):
    name: str
    type: str
    score: float
    reason: str
    genres: list[str] = Field(default_factory=list)
    related_entities: list[RelatedEntityResponse] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)


class SpotifyCardResponse(BaseModel):
    card_type: str
    title: str
    subtitle: str
    spotify_url: str
    spotify_id: str | None = None
    image_url: str | None = None
    embed_url: str | None = None
    popularity: int | None = None
    source_entity: str | None = None
    metadata: dict[str, str] = Field(default_factory=dict)


class ChatResponse(BaseModel):
    # Chat responses combine the answer with diagnostics so the frontend does not need another round trip.
    question: str
    answer: str
    certainty: str
    uncertainty_note: str | None = None
    citations: list[CitationResponse] = Field(default_factory=list)
    sources: list[SourceResponse] = Field(default_factory=list)
    route_steps: list[str] = Field(default_factory=list)
    query_understanding: QueryUnderstandingResponse | None = None
    ranked_entities: list[RankedEntityResponse] = Field(default_factory=list)
    spotify_cards: list[SpotifyCardResponse] = Field(default_factory=list)
    spotify_error: str | None = None
    chat_history: list[ChatTurnResponse] = Field(default_factory=list)
    remaining_questions: int
    current_plan: str
    current_plan_name: str
    remaining_daily_questions: int | None = None
    remaining_monthly_questions: int | None = None
    extra_question_credits: int = 0
    limit_message: str | None = None
    plan_features: PlanFeatureResponse


class HistoryItemResponse(BaseModel):
    id: str
    question: str
    answer: str
    sources_json: list[dict] = Field(default_factory=list)
    spotify_results_json: list[dict] = Field(default_factory=list)
    created_at: datetime


class HistoryResponse(BaseModel):
    enabled: bool
    items: list[HistoryItemResponse] = Field(default_factory=list)


class FavoriteTrackRequest(BaseModel):
    spotify_track_id: str | None = None
    track_name: str
    artist_name: str
    spotify_url: str
    album_image: str | None = None
    source_question: str | None = None


class FavoriteTrackResponse(BaseModel):
    id: str
    spotify_track_id: str
    track_name: str
    artist_name: str
    spotify_url: str
    album_image: str | None = None
    source_question: str | None = None
    created_at: datetime


class FavoritesResponse(BaseModel):
    enabled: bool
    items: list[FavoriteTrackResponse] = Field(default_factory=list)


def plan_to_response(plan: PlanConfig) -> PlanResponse:
    # Serialize central plan config without exposing any billing/provider implementation details.
    return PlanResponse(
        code=plan.code,
        name=plan.name,
        price_label=plan.price_label,
        daily_limit=plan.daily_limit,
        monthly_limit=plan.monthly_limit,
        max_answer_tokens=plan.max_answer_tokens,
        rag_top_k=plan.rag_top_k,
        spotify_limit=plan.spotify_limit,
        save_history=plan.save_history,
        favorites=plan.favorites,
        playlist_style=plan.playlist_style,
    )


def extra_pack_to_response(pack: ExtraPackConfig) -> ExtraPackResponse:
    # Extra-pack payloads are placeholder product data until Stripe is connected.
    return ExtraPackResponse(
        code=pack.code,
        price_label=pack.price_label,
        question_credits=pack.question_credits,
        expires_after_months=pack.expires_after_months,
    )


def user_to_response(user: AuthUser) -> UserResponse:
    """Serialize the safe auth user shape; password hashes never enter API responses."""
    return UserResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        plan=user.plan,
        subscription_status=user.subscription_status,
    )


def quota_to_response(quota: QuotaStatus) -> UsageStatusResponse:
    # Use one serializer for login, account status, chat responses, and limit modals.
    return UsageStatusResponse(
        current_plan=quota.current_plan,
        current_plan_name=quota.current_plan_name,
        price_label=quota.price_label,
        remaining_questions=quota.remaining,
        remaining_daily_questions=quota.remaining_daily_questions,
        remaining_monthly_questions=quota.remaining_monthly_questions,
        extra_question_credits=quota.extra_question_credits,
        limit_message=quota.limit_message,
        features=PlanFeatureResponse(
            max_answer_tokens=quota.max_answer_tokens,
            rag_top_k=quota.rag_top_k,
            spotify_limit=quota.spotify_limit,
            save_history=quota.save_history,
            favorites=quota.favorites,
            playlist_style=quota.playlist_style,
        ),
    )


def _getattr(obj: Any, name: str, default: Any = None) -> Any:
    # Accept dicts and dataclasses because tests and service objects use both shapes.
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def chat_result_to_response(*, question: str, service_result: Any) -> ChatResponse:
    """
    Convert the rich RAG dataclasses into JSON-safe frontend data. This layer is
    intentionally explicit so future React components know exactly what the API
    contract is without seeing backend secrets or internal provider responses.
    """
    result = service_result.result
    remaining_quota = service_result.remaining_quota
    understanding = _getattr(result, "query_understanding")

    return ChatResponse(
        question=question,
        answer=_getattr(result, "answer", ""),
        certainty=_getattr(result, "certainty", "UNCERTAIN"),
        uncertainty_note=_getattr(result, "uncertainty_note"),
        citations=[
            CitationResponse(
                number=_getattr(item, "number", 0),
                title=_getattr(item, "title", ""),
                source_type=_getattr(item, "source_type", ""),
                source_name=_getattr(item, "source_name", ""),
                url=_getattr(item, "url"),
            )
            for item in _getattr(result, "citations", [])
        ],
        sources=[
            SourceResponse(
                rank=_getattr(item, "rank", idx),
                source_type=_getattr(item, "source_type", ""),
                source_name=_getattr(item, "source_name", ""),
                title=_getattr(item, "title", ""),
                snippet=_getattr(item, "snippet", ""),
                full_text=_getattr(item, "full_text", ""),
                retrieval_score=float(_getattr(item, "retrieval_score", 0.0)),
                trust_level=_getattr(item, "trust_level", ""),
                url=_getattr(item, "url"),
                metadata=dict(_getattr(item, "metadata", {}) or {}),
            )
            for idx, item in enumerate(_getattr(result, "used_evidence", []), start=1)
        ],
        route_steps=list(_getattr(result, "route_steps", []) or []),
        query_understanding=(
            QueryUnderstandingResponse(
                intent=_getattr(understanding, "intent", ""),
                primary_entity_type=_getattr(understanding, "primary_entity_type", ""),
                genre_hint=_getattr(understanding, "genre_hint"),
                needs_spotify=bool(_getattr(understanding, "needs_spotify", False)),
                spotify_display_target=_getattr(understanding, "spotify_display_target", "none"),
            )
            if understanding
            else None
        ),
        ranked_entities=[
            RankedEntityResponse(
                name=_getattr(item, "name", ""),
                type=_getattr(item, "type", ""),
                score=float(_getattr(item, "score", 0.0)),
                reason=_getattr(item, "reason", ""),
                genres=list(_getattr(item, "genres", []) or []),
                related_entities=[
                    RelatedEntityResponse(
                        name=_getattr(related, "name", ""),
                        type=_getattr(related, "type", ""),
                        relationship=_getattr(related, "relationship", ""),
                    )
                    for related in _getattr(item, "related_entities", [])
                ],
                sources=list(_getattr(item, "sources", []) or []),
            )
            for item in _getattr(result, "ranked_entities", [])
        ],
        spotify_cards=[
            SpotifyCardResponse(
                card_type=_getattr(item, "card_type", ""),
                title=_getattr(item, "title", ""),
                subtitle=_getattr(item, "subtitle", ""),
                spotify_url=_getattr(item, "spotify_url", ""),
                spotify_id=_getattr(item, "spotify_id"),
                image_url=_getattr(item, "image_url"),
                embed_url=_getattr(item, "embed_url"),
                popularity=_getattr(item, "popularity"),
                source_entity=_getattr(item, "source_entity"),
                metadata=dict(_getattr(item, "metadata", {}) or {}),
            )
            for item in _getattr(result, "spotify_cards", [])
        ],
        spotify_error=_getattr(_getattr(result, "music_routing"), "spotify_error"),
        chat_history=[
            ChatTurnResponse(
                user=_getattr(item, "user", ""),
                assistant=_getattr(item, "assistant", ""),
            )
            for item in _getattr(result, "updated_chat_history", [])
        ],
        remaining_questions=int(_getattr(remaining_quota, "remaining", 0)),
        current_plan=_getattr(remaining_quota, "current_plan", "free"),
        current_plan_name=_getattr(remaining_quota, "current_plan_name", "Free"),
        remaining_daily_questions=_getattr(remaining_quota, "remaining_daily_questions"),
        remaining_monthly_questions=_getattr(remaining_quota, "remaining_monthly_questions"),
        extra_question_credits=int(_getattr(remaining_quota, "extra_question_credits", 0)),
        limit_message=_getattr(remaining_quota, "limit_message"),
        plan_features=PlanFeatureResponse(
            max_answer_tokens=int(_getattr(remaining_quota, "max_answer_tokens", 400)),
            rag_top_k=int(_getattr(remaining_quota, "rag_top_k", 3)),
            spotify_limit=int(_getattr(remaining_quota, "spotify_limit", 5)),
            save_history=bool(_getattr(remaining_quota, "save_history", False)),
            favorites=bool(_getattr(remaining_quota, "favorites", False)),
            playlist_style=bool(_getattr(remaining_quota, "playlist_style", False)),
        ),
    )
