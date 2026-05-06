from __future__ import annotations

import re
from uuid import uuid4

from src.db import connect_db
from src.repositories import favorite_repository


def extract_spotify_track_id(spotify_url: str) -> str | None:
    # Accept normal Spotify track URLs and strip query strings before storing the stable id.
    match = re.search(r"open\.spotify\.com/track/([^?/#]+)", spotify_url)
    return match.group(1) if match else None


def list_favorites(user_id: str) -> list[dict]:
    # Favorite reads are free because they only display existing saved tracks.
    with connect_db() as conn:
        return favorite_repository.list_favorite_tracks(conn, user_id=user_id)


def save_favorite(
    *,
    user_id: str,
    spotify_track_id: str | None,
    track_name: str,
    artist_name: str,
    spotify_url: str,
    album_image: str | None,
    source_question: str | None,
) -> dict:
    # Validate that favorites are track-level Spotify URLs before writing the simple MVP list.
    resolved_track_id = spotify_track_id or extract_spotify_track_id(spotify_url)
    if not resolved_track_id:
        raise ValueError("Only Spotify track recommendations can be favorited.")

    with connect_db() as conn:
        row = favorite_repository.upsert_favorite_track(
            conn,
            favorite_id=str(uuid4()),
            user_id=user_id,
            spotify_track_id=resolved_track_id,
            track_name=track_name,
            artist_name=artist_name,
            spotify_url=spotify_url,
            album_image=album_image,
            source_question=source_question,
        )
        conn.commit()
    return row


def delete_favorite(user_id: str, favorite_id: str) -> int:
    # Deleting a favorite never affects saved chat history or quota.
    with connect_db() as conn:
        deleted = favorite_repository.delete_favorite_track(
            conn,
            user_id=user_id,
            favorite_id=favorite_id,
        )
        conn.commit()
        return deleted
