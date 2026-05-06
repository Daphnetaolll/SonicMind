from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


PlanCode = Literal["free", "creator", "pro"]


@dataclass(frozen=True)
class PlanConfig:
    """Browser-safe plan settings used by quota, RAG, and Spotify controls."""

    code: PlanCode
    name: str
    price_label: str
    daily_limit: int | None
    monthly_limit: int | None
    max_answer_tokens: int
    rag_top_k: int
    spotify_limit: int
    save_history: bool
    favorites: bool
    playlist_style: bool
    limit_message: str


@dataclass(frozen=True)
class ExtraPackConfig:
    """Placeholder credit-pack config for UI display before Stripe exists."""

    code: str
    price_label: str
    question_credits: int
    expires_after_months: int


# Centralized plan config keeps frontend labels, backend enforcement, and docs aligned.
PLANS: dict[str, PlanConfig] = {
    "free": PlanConfig(
        code="free",
        name="Free",
        price_label="$0/month",
        daily_limit=5,
        monthly_limit=None,
        max_answer_tokens=400,
        rag_top_k=3,
        spotify_limit=5,
        save_history=False,
        favorites=False,
        playlist_style=False,
        limit_message=(
            "You’ve used today’s 5 free questions. Come back tomorrow or upgrade to Creator "
            "for 200 questions/month."
        ),
    ),
    "creator": PlanConfig(
        code="creator",
        name="Student / Creator",
        price_label="$4.99/month",
        daily_limit=None,
        monthly_limit=200,
        max_answer_tokens=800,
        rag_top_k=5,
        spotify_limit=10,
        save_history=True,
        favorites=True,
        playlist_style=False,
        limit_message=(
            "You’ve used your 200 monthly questions. You can upgrade to Pro or buy extra questions."
        ),
    ),
    "pro": PlanConfig(
        code="pro",
        name="Pro",
        price_label="$8.99/month",
        daily_limit=None,
        monthly_limit=1000,
        max_answer_tokens=1200,
        rag_top_k=8,
        spotify_limit=15,
        save_history=True,
        favorites=True,
        playlist_style=True,
        limit_message="You’ve used your 1000 monthly questions. You can buy extra questions.",
    ),
}


EXTRA_PACKS: tuple[ExtraPackConfig, ...] = (
    ExtraPackConfig(
        code="extra-50",
        price_label="$2.99",
        question_credits=50,
        expires_after_months=12,
    ),
    ExtraPackConfig(
        code="extra-100",
        price_label="$4.99",
        question_credits=100,
        expires_after_months=12,
    ),
)


DEFAULT_PLAN_CODE: PlanCode = "free"
ACTIVE_SUBSCRIPTION_STATUSES = {"trial", "active"}


def get_plan(plan_code: str | None) -> PlanConfig:
    # Unknown or stale plan codes degrade to Free rather than crashing the request path.
    return PLANS.get((plan_code or DEFAULT_PLAN_CODE).lower(), PLANS[DEFAULT_PLAN_CODE])


def public_plan_payload(plan: PlanConfig) -> dict[str, object]:
    # Return only product/limit fields that are safe to show in browser pricing UI.
    return {
        "code": plan.code,
        "name": plan.name,
        "price_label": plan.price_label,
        "daily_limit": plan.daily_limit,
        "monthly_limit": plan.monthly_limit,
        "max_answer_tokens": plan.max_answer_tokens,
        "rag_top_k": plan.rag_top_k,
        "spotify_limit": plan.spotify_limit,
        "save_history": plan.save_history,
        "favorites": plan.favorites,
        "playlist_style": plan.playlist_style,
    }
