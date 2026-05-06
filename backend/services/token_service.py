from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any


DEFAULT_TOKEN_TTL_SECONDS = 60 * 60 * 24


def _token_secret() -> str:
    """
    Read the signing secret only on the backend. React receives opaque tokens,
    never API keys, database URLs, Spotify credentials, or this signing secret.
    """
    return os.getenv("BACKEND_SECRET_KEY", "dev-only-change-me")


def _urlsafe_b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _urlsafe_b64decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def create_access_token(*, user_id: str, ttl_seconds: int = DEFAULT_TOKEN_TTL_SECONDS) -> str:
    """
    Create a minimal HMAC-signed token for the React migration. This avoids a
    larger auth dependency while still preventing clients from forging user ids.
    """
    payload = {
        "sub": user_id,
        "exp": int(time.time()) + ttl_seconds,
    }
    body = _urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = hmac.new(
        _token_secret().encode("utf-8"),
        body.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return f"{body}.{_urlsafe_b64encode(signature)}"


def verify_access_token(token: str) -> dict[str, Any] | None:
    """Return the decoded payload only when the token signature and expiry are valid."""
    try:
        body, signature = token.split(".", 1)
        expected_signature = hmac.new(
            _token_secret().encode("utf-8"),
            body.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        actual_signature = _urlsafe_b64decode(signature)
        if not hmac.compare_digest(actual_signature, expected_signature):
            return None

        payload = json.loads(_urlsafe_b64decode(body).decode("utf-8"))
        if int(payload.get("exp", 0)) < int(time.time()):
            return None
        return payload if isinstance(payload, dict) else None
    except (ValueError, json.JSONDecodeError, TypeError):
        return None
