from __future__ import annotations

import os

from backend.services.memory_logging import log_memory

log_memory("backend_module_start")

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.schemas import (
    AccountStatusResponse,
    AuthResponse,
    ChatRequest,
    ChatResponse,
    FavoriteTrackRequest,
    FavoriteTrackResponse,
    FavoritesResponse,
    HistoryResponse,
    HealthResponse,
    LoginRequest,
    PricingResponse,
    RegisterRequest,
    chat_result_to_response,
    extra_pack_to_response,
    plan_to_response,
    quota_to_response,
    user_to_response,
)
from backend.config.plans import EXTRA_PACKS, PLANS
from backend.services.account_service import AccountValidationError, create_account, sign_in_user
from backend.services.chat_service import answer_user_question
from backend.services.error_service import safe_error_message
from backend.services.favorite_service import delete_favorite, list_favorites, save_favorite
from backend.services.history_service import delete_saved_history, get_saved_history
from backend.services.knowledge_base_service import knowledge_base_ready
from backend.services.token_service import create_access_token, verify_access_token
from src.services.auth_service import AuthUser, get_user
from src.services.quota_service import get_quota_status


load_dotenv()
log_memory("backend_after_imports")

app = FastAPI(title="SonicMind API", version="0.1.0")
security = HTTPBearer(auto_error=False)
log_memory("backend_after_app_creation")


def _cors_origins() -> list[str]:
    """
    Allow local React dev servers by default. Production origins should be set in
    backend environment variables, never hard-coded in frontend code with secrets.
    """
    configured = os.getenv("BACKEND_CORS_ORIGINS")
    if configured:
        return [origin.strip() for origin in configured.split(",") if origin.strip()]
    return [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> AuthUser:
    """
    Resolve a bearer token into the existing AuthUser model. The frontend only
    stores this opaque token; database lookups and credential checks stay here.
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token.",
        )

    payload = verify_access_token(credentials.credentials)
    user_id = payload.get("sub") if payload else None
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
        )

    user = get_user(str(user_id))
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
        )
    return user


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    # Include knowledge-base readiness so deployment checks can catch missing generated artifacts.
    ready = knowledge_base_ready()
    log_memory("health_check", knowledge_base_ready=ready)
    return HealthResponse(
        status="ok",
        service="sonicmind-api",
        knowledge_base_ready=ready,
    )


@app.get("/api/pricing", response_model=PricingResponse)
def pricing() -> PricingResponse:
    # Pricing data is public and contains no payment secrets; buttons remain placeholders for now.
    return PricingResponse(
        plans=[plan_to_response(plan) for plan in PLANS.values()],
        extra_packs=[extra_pack_to_response(pack) for pack in EXTRA_PACKS],
    )


@app.get("/api/me", response_model=AccountStatusResponse)
def me(current_user: AuthUser = Depends(get_current_user)) -> AccountStatusResponse:
    # Account status gives React fresh server-owned quota data after refreshes and logins.
    quota = get_quota_status(current_user.id)
    return AccountStatusResponse(user=user_to_response(current_user), usage=quota_to_response(quota))


@app.post("/api/login", response_model=AuthResponse)
def login(payload: LoginRequest) -> AuthResponse:
    # Login returns only a signed token and safe user fields; password hashes never cross this boundary.
    try:
        user = sign_in_user(payload.email, payload.password)
    except AccountValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        # Auth depends on backend-only database configuration; return a clean API error if local env is missing.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=safe_error_message(exc, fallback="Login is unavailable right now."),
        ) from exc

    return AuthResponse(
        token=create_access_token(user_id=user.id),
        user=user_to_response(user),
    )


@app.post("/api/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest) -> AuthResponse:
    # Registration shares account validation with Streamlit during the React migration.
    try:
        user = create_account(
            email=payload.email,
            password=payload.password,
            confirm_password=payload.confirm_password,
            display_name=payload.display_name,
        )
    except AccountValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        # Registration should not leak SQL, connection, or schema details to the browser.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=safe_error_message(exc, fallback="Registration is unavailable right now."),
        ) from exc

    return AuthResponse(
        token=create_access_token(user_id=user.id),
        user=user_to_response(user),
    )


@app.post("/api/chat", response_model=ChatResponse)
def chat(payload: ChatRequest, current_user: AuthUser = Depends(get_current_user)) -> ChatResponse:
    # Validate cheap request preconditions before starting the charged question lifecycle.
    log_memory("before_chat_request")
    question = payload.question.strip()
    if not question:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Question is required.",
        )
    ready = knowledge_base_ready()
    log_memory("after_knowledge_base_ready_check", knowledge_base_ready=ready)
    if not ready and os.getenv("RAG_FALLBACK_MODE", "keyword").strip().lower() not in {"llm_only", "keyword"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Knowledge base is not ready.",
        )

    quota = get_quota_status(current_user.id)
    if not quota.allowed:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "code": "usage_limit_reached",
                "message": quota.limit_message or "No remaining question quota.",
                "usage": quota_to_response(quota).model_dump(),
            },
        )

    # The chat service owns logging, answer generation, and quota charging as one operation.
    try:
        log_memory("before_answer_user_question", topk=quota.rag_top_k)
        service_result = answer_user_question(
            user_id=current_user.id,
            question=question,
            quota=quota,
            chat_history=[turn.model_dump() for turn in payload.chat_history],
            topk=quota.rag_top_k,
            max_history_turns=payload.max_history_turns,
        )
        log_memory("after_answer_user_question")
    except Exception as exc:
        log_memory("chat_request_failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_message(exc, fallback="The question could not be answered right now."),
        ) from exc

    log_memory("after_chat_request")
    return chat_result_to_response(question=question, service_result=service_result)


@app.get("/api/history", response_model=HistoryResponse)
def history(current_user: AuthUser = Depends(get_current_user)) -> HistoryResponse:
    # Free users keep temporary browser history only; paid plans can read saved backend history.
    quota = get_quota_status(current_user.id)
    if not quota.save_history:
        return HistoryResponse(enabled=False, items=[])
    try:
        return HistoryResponse(enabled=True, items=get_saved_history(current_user.id))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=safe_error_message(exc, fallback="Saved history is unavailable right now."),
        ) from exc


@app.delete("/api/history")
def delete_history(current_user: AuthUser = Depends(get_current_user)) -> dict[str, int]:
    # History deletion is gated by plan and does not touch question usage records.
    quota = get_quota_status(current_user.id)
    if not quota.save_history:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Saved history is available on Creator and Pro plans.",
        )
    deleted = delete_saved_history(current_user.id)
    return {"deleted": deleted}


@app.get("/api/favorites", response_model=FavoritesResponse)
def favorites(current_user: AuthUser = Depends(get_current_user)) -> FavoritesResponse:
    # Favorite reads are plan-gated but never deduct usage.
    quota = get_quota_status(current_user.id)
    if not quota.favorites:
        return FavoritesResponse(enabled=False, items=[])
    return FavoritesResponse(enabled=True, items=list_favorites(current_user.id))


@app.post("/api/favorites", response_model=FavoriteTrackResponse, status_code=status.HTTP_201_CREATED)
def add_favorite(
    payload: FavoriteTrackRequest,
    current_user: AuthUser = Depends(get_current_user),
) -> FavoriteTrackResponse:
    # Favorites are only available on plans with durable saved music state.
    quota = get_quota_status(current_user.id)
    if not quota.favorites:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Favorites are available on Creator and Pro plans.",
        )
    try:
        return FavoriteTrackResponse(
            **save_favorite(
                user_id=current_user.id,
                spotify_track_id=payload.spotify_track_id,
                track_name=payload.track_name,
                artist_name=payload.artist_name,
                spotify_url=payload.spotify_url,
                album_image=payload.album_image,
                source_question=payload.source_question,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@app.delete("/api/favorites/{favorite_id}")
def remove_favorite(
    favorite_id: str,
    current_user: AuthUser = Depends(get_current_user),
) -> dict[str, int]:
    # Favorite deletion is scoped to the signed-in user by the repository layer.
    quota = get_quota_status(current_user.id)
    if not quota.favorites:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Favorites are available on Creator and Pro plans.",
        )
    return {"deleted": delete_favorite(current_user.id, favorite_id)}
