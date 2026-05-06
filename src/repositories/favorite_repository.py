from __future__ import annotations

from typing import Any


def upsert_favorite_track(
    conn: Any,
    *,
    favorite_id: str,
    user_id: str,
    spotify_track_id: str,
    track_name: str,
    artist_name: str,
    spotify_url: str,
    album_image: str | None,
    source_question: str | None,
) -> dict[str, Any]:
    # Upsert prevents duplicate favorites when a user taps the same recommendation twice.
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO favorite_tracks (
                id,
                user_id,
                spotify_track_id,
                track_name,
                artist_name,
                spotify_url,
                album_image,
                source_question
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (user_id, spotify_track_id)
            DO UPDATE SET
                track_name = EXCLUDED.track_name,
                artist_name = EXCLUDED.artist_name,
                spotify_url = EXCLUDED.spotify_url,
                album_image = EXCLUDED.album_image,
                source_question = EXCLUDED.source_question
            RETURNING *
            """,
            (
                favorite_id,
                user_id,
                spotify_track_id,
                track_name,
                artist_name,
                spotify_url,
                album_image,
                source_question,
            ),
        )
        row = cur.fetchone()
    return dict(row)


def list_favorite_tracks(conn: Any, *, user_id: str) -> list[dict[str, Any]]:
    # Favorites are intentionally a flat list for the MVP; playlist folders can come later.
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                id,
                spotify_track_id,
                track_name,
                artist_name,
                spotify_url,
                album_image,
                source_question,
                created_at
            FROM favorite_tracks
            WHERE user_id = %s
            ORDER BY created_at DESC
            """,
            (user_id,),
        )
        rows = cur.fetchall()
    return [dict(row) for row in rows]


def delete_favorite_track(conn: Any, *, user_id: str, favorite_id: str) -> int:
    # Delete by favorite row id while scoping to the signed-in user.
    with conn.cursor() as cur:
        cur.execute(
            """
            DELETE FROM favorite_tracks
            WHERE user_id = %s AND id = %s
            """,
            (user_id, favorite_id),
        )
        return int(cur.rowcount or 0)
