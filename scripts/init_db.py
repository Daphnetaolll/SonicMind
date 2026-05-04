from __future__ import annotations

import sys
from pathlib import Path

# Allow the initialization script to import src modules without package installation.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.db import connect_db, get_database_url, init_database


def main() -> None:
    # Initialize schema, then list public tables so setup output is easy to verify.
    database_url = init_database()
    with connect_db(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                ORDER BY table_name
                """
            )
            tables = cur.fetchall()

    print(f"Initialized database: {get_database_url()}")
    print("Tables:")
    for row in tables:
        print(f"- {row['table_name']}")


if __name__ == "__main__":
    main()
