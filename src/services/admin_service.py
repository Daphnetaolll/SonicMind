from __future__ import annotations

from src.db import connect_db
from src.repositories import admin_repository


def is_admin(user_id: str) -> bool:
    # Keep admin checks behind a service function so upload permissions stay centralized.
    with connect_db() as conn:
        return admin_repository.has_role(conn, user_id, "admin")
