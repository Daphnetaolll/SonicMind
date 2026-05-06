from __future__ import annotations

from src.services.auth_service import AuthUser, authenticate_user, register_user


class AccountValidationError(ValueError):
    """Raised when account form input is invalid before touching lower auth code."""


def sign_in_user(email: str, password: str) -> AuthUser:
    """
    Keep login validation outside the UI so the upcoming FastAPI endpoint can reuse
    the exact same account rules as the current Streamlit screen.
    """
    if not email.strip() or not password:
        raise AccountValidationError("Email and password are required.")

    user = authenticate_user(email, password)
    if not user:
        raise AccountValidationError("Invalid email or password.")
    return user


def create_account(
    *,
    email: str,
    password: str,
    confirm_password: str,
    display_name: str | None = None,
) -> AuthUser:
    """
    Centralize registration validation so React and Streamlit do not drift into
    slightly different password or email behavior during the migration.
    """
    if not email.strip() or not password:
        raise AccountValidationError("Email and password are required.")
    if password != confirm_password:
        raise AccountValidationError("Passwords do not match.")
    if len(password) < 8:
        raise AccountValidationError("Password must be at least 8 characters.")

    try:
        return register_user(email, password, display_name=display_name or None)
    except ValueError as exc:
        raise AccountValidationError(str(exc)) from exc
