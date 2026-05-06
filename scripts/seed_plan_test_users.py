from __future__ import annotations

import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv

# Allow direct script execution without installing the project as a package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.config.plans import get_plan
from src.db import connect_db, init_database
from src.repositories import user_repository
from src.services.auth_service import register_user


SEED_USERS = (
    ("freetest@example.com", "free"),
    ("creatortest@example.com", "creator"),
    ("protest@example.com", "pro"),
)


def _ensure_user(email: str, password: str):
    # Reuse existing local users when present so running the seed script is idempotent.
    with connect_db() as conn:
        row = user_repository.get_user_by_email(conn, email)
    if row:
        return row
    return register_user(email, password)


def main() -> int:
    load_dotenv()
    if os.getenv("SONICMIND_ENABLE_DEV_SEEDS") != "true":
        print("Refusing to seed users unless SONICMIND_ENABLE_DEV_SEEDS=true is set.")
        return 1

    password = os.getenv("SONICMIND_DEV_SEED_PASSWORD", "Test123456!")
    init_database()
    now = datetime.now(UTC)

    for email, plan_code in SEED_USERS:
        user = _ensure_user(email, password)
        plan = get_plan(plan_code)
        period_start = now if plan.monthly_limit is not None else None
        period_end = now + timedelta(days=30) if plan.monthly_limit is not None else None
        with connect_db() as conn:
            user_repository.update_user_plan(
                conn,
                user_id=user["id"] if isinstance(user, dict) else user.id,
                plan=plan.code,
                subscription_status="active",
                billing_period_start=period_start,
                billing_period_end=period_end,
            )
            conn.commit()
        print(f"Seeded {email} as {plan.name}.")

    print("Done. Use the configured dev password to log in locally.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
