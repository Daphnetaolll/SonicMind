from __future__ import annotations

from typing import Any


def has_role(conn: Any, user_id: str, role: str) -> bool:
    # Check role membership without returning any account details to the caller.
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT 1
            FROM admin_roles
            WHERE user_id = %s AND role = %s
            LIMIT 1
            """,
            (user_id, role),
        )
        row = cur.fetchone()
    return row is not None
