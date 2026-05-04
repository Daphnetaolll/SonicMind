from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from uuid import uuid4

from psycopg.errors import UniqueViolation

from src.db import connect_db
from src.repositories import usage_repository, user_repository


FREE_TRIAL_QUESTIONS = 5
PBKDF2_ITERATIONS = 600_000


# AuthUser is the safe account shape returned to the UI; password hashes never leave this service.
@dataclass
class AuthUser:
    id: str
    email: str
    display_name: str | None


def _hash_password(password: str) -> str:
    # Store passwords with a per-user salt and high PBKDF2 work factor for local database auth.
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def _verify_password(password: str, stored_hash: str) -> bool:
    # Recreate the stored PBKDF2 digest and compare with constant-time equality.
    algorithm, iterations, salt_hex, digest_hex = stored_hash.split("$", 3)
    if algorithm != "pbkdf2_sha256":
        return False
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes.fromhex(salt_hex),
        int(iterations),
    )
    return hmac.compare_digest(digest.hex(), digest_hex)


def register_user(email: str, password: str, display_name: str | None = None) -> AuthUser:
    # Create the account and grant the initial free trial in one transaction.
    normalized_email = email.strip().lower()
    password_hash = _hash_password(password)
    user_id = str(uuid4())

    with connect_db() as conn:
        try:
            row = user_repository.create_user(
                conn,
                user_id=user_id,
                email=normalized_email,
                password_hash=password_hash,
                display_name=display_name,
            )
            usage_repository.insert_usage_event(
                conn,
                entry_id=str(uuid4()),
                user_id=user_id,
                subscription_id=None,
                question_log_id=None,
                event_type="free_grant",
                delta=FREE_TRIAL_QUESTIONS,
                source="auth_service.register_user",
                notes="Initial free question grant.",
            )
            conn.commit()
        except UniqueViolation as exc:
            conn.rollback()
            raise ValueError("Email already exists.") from exc

    return AuthUser(id=row["id"], email=row["email"], display_name=row["display_name"])


def authenticate_user(email: str, password: str) -> AuthUser | None:
    # Return a safe user object only when the account exists, is active, and the password matches.
    normalized_email = email.strip().lower()
    with connect_db() as conn:
        row = user_repository.get_user_by_email(conn, normalized_email)

    if not row or row["deleted_at"] is not None:
        return None
    if not _verify_password(password, row["password_hash"]):
        return None
    return AuthUser(id=row["id"], email=row["email"], display_name=row["display_name"])


def get_user(user_id: str) -> AuthUser | None:
    # Resolve the current session user from the database and ignore soft-deleted accounts.
    with connect_db() as conn:
        row = user_repository.get_user_by_id(conn, user_id)
    if not row or row["deleted_at"] is not None:
        return None
    return AuthUser(id=row["id"], email=row["email"], display_name=row["display_name"])
