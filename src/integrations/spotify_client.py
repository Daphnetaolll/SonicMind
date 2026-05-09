from __future__ import annotations

import base64
import json
import logging
import os
import re
import time
from functools import lru_cache
from urllib import error, parse, request

from src.music.recommendation_provider import get_recommendation_for_genre
from src.music.schemas import MusicRecommendationPlan, MusicTrackCandidate, QueryUnderstandingResult, RankedMusicEntity, SpotifyCard


SPOTIFY_API_BASE = "https://api.spotify.com/v1"
_TOKEN_CACHE: dict[str, float | str] = {"access_token": "", "expires_at": 0.0}
_BACKOFF_UNTIL = 0.0
logger = logging.getLogger(__name__)


def spotify_credentials_ready() -> bool:
    return bool(os.getenv("SPOTIFY_CLIENT_ID") and os.getenv("SPOTIFY_CLIENT_SECRET"))


def _get_access_token(timeout: int = 20) -> str:
    cached_token = str(_TOKEN_CACHE.get("access_token") or "")
    expires_at = float(_TOKEN_CACHE.get("expires_at") or 0.0)
    if cached_token and time.time() < expires_at:
        return cached_token

    client_id = os.getenv("SPOTIFY_CLIENT_ID")
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise ValueError("Missing SPOTIFY_CLIENT_ID or SPOTIFY_CLIENT_SECRET.")

    basic = base64.b64encode(f"{client_id}:{client_secret}".encode("utf-8")).decode("utf-8")
    payload = parse.urlencode({"grant_type": "client_credentials"}).encode("utf-8")
    req = request.Request(
        url="https://accounts.spotify.com/api/token",
        data=payload,
        headers={
            "Authorization": f"Basic {basic}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Spotify token request failed: HTTP {exc.code} {detail}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Spotify token request failed: {exc.reason}") from exc

    token = data.get("access_token")
    if not token:
        raise RuntimeError(f"Unexpected Spotify token response: {data}")
    # Cache the client-credentials token so one answer does not request many identical tokens.
    _TOKEN_CACHE["access_token"] = token
    _TOKEN_CACHE["expires_at"] = time.time() + max(int(data.get("expires_in", 3600)) - 60, 60)
    return token


def _api_get(path: str, params: dict[str, str] | None = None, *, timeout: int = 20) -> dict:
    global _BACKOFF_UNTIL
    if time.time() < _BACKOFF_UNTIL:
        raise RuntimeError("Spotify is temporarily rate limited.")

    token = _get_access_token(timeout=timeout)
    query = f"?{parse.urlencode(params or {})}" if params else ""
    req = request.Request(
        url=f"{SPOTIFY_API_BASE}{path}{query}",
        headers={"Authorization": f"Bearer {token}"},
        method="GET",
    )
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        if exc.code == 429:
            retry_after = exc.headers.get("Retry-After")
            try:
                delay = int(retry_after) if retry_after else 60
            except ValueError:
                delay = 60
            _BACKOFF_UNTIL = time.time() + max(delay, 30)
            logger.warning("Spotify rate limited SonicMind catalog lookup; backing off for %s seconds.", delay)
        raise RuntimeError(f"Spotify request failed: HTTP {exc.code} {detail}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Spotify request failed: {exc.reason}") from exc


@lru_cache(maxsize=512)
def _cached_search_items(query: str, item_types: str, limit: int, market: str) -> str:
    # Cache read-only Spotify catalog searches within the backend process to avoid repeated rate pressure.
    data = _api_get(
        "/search",
        {
            "q": query,
            "type": item_types,
            "limit": str(limit),
            "market": market,
        },
    )
    return json.dumps(data)


def search_items(query: str, item_types: list[str], *, limit: int = 5, market: str = "US") -> dict:
    item_type_key = ",".join(item_types)
    return json.loads(_cached_search_items(query, item_type_key, limit, market))


def search_artist(name: str, *, market: str = "US") -> dict | None:
    data = search_items(name, ["artist"], limit=1, market=market)
    items = data.get("artists", {}).get("items", [])
    return items[0] if items else None


def search_track(name: str, artist_hint: str | None = None, *, market: str = "US") -> dict | None:
    query = f'track:"{name}"'
    if artist_hint:
        query += f' artist:"{artist_hint}"'
    data = search_items(query, ["track"], limit=1, market=market)
    items = data.get("tracks", {}).get("items", [])
    return items[0] if items else None


def search_album(name: str, artist_hint: str | None = None, *, market: str = "US") -> dict | None:
    query = f'album:"{name}"'
    if artist_hint:
        query += f' artist:"{artist_hint}"'
    data = search_items(query, ["album"], limit=1, market=market)
    items = data.get("albums", {}).get("items", [])
    return items[0] if items else None


def search_playlist(query: str, *, market: str = "US") -> dict | None:
    data = search_items(query, ["playlist"], limit=1, market=market)
    items = data.get("playlists", {}).get("items", [])
    return items[0] if items else None


def search_playlists(query: str, *, limit: int = 5, market: str = "US") -> list[dict]:
    # Current recommendation discovery needs several playlist candidates, not only the first catalog hit.
    data = search_items(query, ["playlist"], limit=limit, market=market)
    return [item for item in data.get("playlists", {}).get("items", []) if item]


@lru_cache(maxsize=256)
def _cached_playlist_tracks(playlist_id: str, market: str, limit: int) -> str:
    # Cache public playlist reads so repeated "recently" questions do not hammer Spotify.
    data = _api_get(
        f"/playlists/{playlist_id}/tracks",
        {
            "market": market,
            "limit": str(limit),
            "fields": (
                "items(track(id,name,popularity,external_urls,"
                "artists(name),album(id,name,release_date,images)))"
            ),
        },
    )
    return json.dumps(data)


def get_playlist_tracks(playlist_id: str, *, market: str = "US", limit: int = 30) -> list[dict]:
    data = json.loads(_cached_playlist_tracks(playlist_id, market, limit))
    tracks: list[dict] = []
    for item in data.get("items", []):
        track = item.get("track")
        if isinstance(track, dict) and track.get("id"):
            tracks.append(track)
    return tracks


def get_artist_top_tracks(artist_id: str, *, market: str = "US") -> list[dict]:
    try:
        data = _api_get(f"/artists/{artist_id}/top-tracks", {"market": market})
        return data.get("tracks", [])
    except RuntimeError:
        artist = _api_get(f"/artists/{artist_id}")
        artist_name = artist.get("name") or ""
        return _search_artist_tracks(artist_name, market=market) if artist_name else []


def _track_has_artist(track: dict, artist_name: str) -> bool:
    # Spotify Search can return remixes and collaborations, so keep only tracks credited to the target artist.
    artists = " ".join(artist.get("name", "") for artist in track.get("artists", []) if artist.get("name"))
    normalized_artist = _normalize_match_text(artist_name)
    normalized_artists = _normalize_match_text(artists)
    return normalized_artist in normalized_artists or _token_overlap(artist_name, artists) >= 0.7


def _search_artist_tracks(artist_name: str, *, market: str = "US", limit: int = 10) -> list[dict]:
    # The deprecated top-tracks endpoint can return 403; search is the low-memory fallback for artist songs.
    if not artist_name:
        return []

    queries = [
        f'artist:"{artist_name}"',
        f"{artist_name}",
    ]
    tracks: list[dict] = []
    seen_ids: set[str] = set()
    for query in queries:
        data = search_items(query, ["track"], limit=limit, market=market)
        for item in data.get("tracks", {}).get("items", []):
            item_id = item.get("id")
            if not item_id or item_id in seen_ids:
                continue
            if not _track_has_artist(item, artist_name):
                continue
            seen_ids.add(item_id)
            tracks.append(item)
        if len(tracks) >= limit:
            break

    return sorted(tracks, key=lambda item: item.get("popularity") or 0, reverse=True)[:limit]


def get_artist_albums(artist_id: str, *, market: str = "US", limit: int = 20) -> list[dict]:
    # Artist album lookup stays in Spotify's lightweight Web API instead of using local ML retrieval.
    data = _api_get(
        f"/artists/{artist_id}/albums",
        {
            "include_groups": "album,single",
            "limit": str(limit),
            "market": market,
        },
    )
    return data.get("items", [])


def _image_url(item: dict) -> str | None:
    images = item.get("images") or item.get("album", {}).get("images") or []
    if not images:
        return None
    return images[0].get("url")


def _external_url(item: dict) -> str:
    return item.get("external_urls", {}).get("spotify", "")


def build_artist_card(item: dict, *, source_entity: str | None = None) -> SpotifyCard | None:
    url = _external_url(item)
    item_id = item.get("id")
    if not url or not item_id:
        return None
    genres = ", ".join(item.get("genres", [])[:3])
    return SpotifyCard(
        card_type="artist",
        title=item.get("name", "Unknown artist"),
        subtitle=genres or "Spotify artist",
        spotify_url=url,
        spotify_id=item_id,
        image_url=_image_url(item),
        embed_url=f"https://open.spotify.com/embed/artist/{item_id}",
        popularity=item.get("popularity"),
        source_entity=source_entity,
    )


def build_track_card(item: dict, *, source_entity: str | None = None) -> SpotifyCard | None:
    url = _external_url(item)
    item_id = item.get("id")
    if not url or not item_id:
        return None
    artists = ", ".join(artist.get("name", "") for artist in item.get("artists", []) if artist.get("name"))
    album = item.get("album", {}).get("name", "")
    subtitle = artists if not album else f"{artists} - {album}"
    return SpotifyCard(
        card_type="track",
        title=item.get("name", "Unknown track"),
        subtitle=subtitle,
        spotify_url=url,
        spotify_id=item_id,
        image_url=_image_url(item),
        embed_url=f"https://open.spotify.com/embed/track/{item_id}",
        popularity=item.get("popularity"),
        source_entity=source_entity,
    )


def build_album_card(item: dict, *, source_entity: str | None = None) -> SpotifyCard | None:
    url = _external_url(item)
    item_id = item.get("id")
    if not url or not item_id:
        return None
    artists = ", ".join(artist.get("name", "") for artist in item.get("artists", []) if artist.get("name"))
    return SpotifyCard(
        card_type="album",
        title=item.get("name", "Unknown album"),
        subtitle=artists or "Spotify album",
        spotify_url=url,
        spotify_id=item_id,
        image_url=_image_url(item),
        embed_url=f"https://open.spotify.com/embed/album/{item_id}",
        source_entity=source_entity,
    )


def build_playlist_card(item: dict, *, source_entity: str | None = None) -> SpotifyCard | None:
    url = _external_url(item)
    item_id = item.get("id")
    if not url or not item_id:
        return None
    owner = item.get("owner", {}).get("display_name", "")
    return SpotifyCard(
        card_type="playlist",
        title=item.get("name", "Unknown playlist"),
        subtitle=owner or "Spotify playlist",
        spotify_url=url,
        spotify_id=item_id,
        image_url=_image_url(item),
        embed_url=f"https://open.spotify.com/embed/playlist/{item_id}",
        source_entity=source_entity,
    )


def _normalize_match_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _tokens(value: str) -> set[str]:
    return {token for token in _normalize_match_text(value).split() if len(token) > 1}


def _token_overlap(expected: str, actual: str) -> float:
    expected_tokens = _tokens(expected)
    actual_tokens = _tokens(actual)
    if not expected_tokens or not actual_tokens:
        return 0.0
    return len(expected_tokens & actual_tokens) / len(expected_tokens)


def _track_matches_expected(track: dict, expected_title: str, expected_artist: str) -> bool:
    """
    Explanation:
    Spotify Search is a catalog lookup, not a recommendation engine.
    A result is shown only when both the title and artist are close to the curated target.
    """
    title = track.get("name", "")
    artists = " ".join(artist.get("name", "") for artist in track.get("artists", []))
    title_ok = _normalize_match_text(expected_title) in _normalize_match_text(title) or _token_overlap(expected_title, title) >= 0.7
    artist_ok = _normalize_match_text(expected_artist) in _normalize_match_text(artists) or _token_overlap(expected_artist, artists) >= 0.7
    return title_ok and artist_ok


def find_validated_track(title: str, artist: str, *, market: str = "US") -> dict | None:
    """
    Explanation:
    Previous behavior searched broad phrases like "acid techno tracks", which returned noisy catalog matches.
    This function searches an exact track+artist target, then validates the returned Spotify item before display.
    """
    queries = [
        f'track:"{title}" artist:"{artist}"',
        f"{title} {artist}",
    ]
    for query in queries:
        data = search_items(query, ["track"], limit=5, market=market)
        for item in data.get("tracks", {}).get("items", []):
            if _track_matches_expected(item, title, artist):
                return item
    return None


def _source_grounded_track_cards_for_genre(
    genre_hint: str | None,
    *,
    max_cards: int,
    market: str,
) -> list[SpotifyCard]:
    """
    Explanation:
    Genre questions should display source-grounded representative tracks, not broad Spotify keyword matches.
    The provider first checks curated data, then generated trusted-source cache, then fresh trusted-source discovery.
    """
    recommendation = get_recommendation_for_genre(genre_hint)
    if not recommendation:
        return []

    record, recommendation_source = recommendation
    cards: list[SpotifyCard] = []
    seen_urls: set[str] = set()
    for item in record.get("representative_tracks", []):
        title = item.get("title")
        artist = item.get("artist")
        if not title or not artist:
            continue
        track = find_validated_track(title, artist, market=market)
        card = build_track_card(track, source_entity=genre_hint) if track else None
        if not card or card.spotify_url in seen_urls:
            continue
        seen_urls.add(card.spotify_url)
        card.metadata["recommendation_source"] = recommendation_source
        card.metadata["recommendation_artist"] = artist
        card.metadata["recommendation_title"] = title
        card.metadata["recommendation_sources"] = ", ".join(item.get("sources", []))
        card.metadata["recommendation_explanation"] = str(record.get("explanation", ""))
        cards.append(card)
        if len(cards) >= max_cards:
            break
    return cards


def _track_card_from_spotify_candidate(candidate: MusicTrackCandidate) -> SpotifyCard | None:
    # Spotify-derived candidates already carry a playable track URL, so avoid a second noisy catalog search.
    track_url = next((url for url in candidate.source_urls if "/track/" in url), "")
    match = re.search(r"/track/([^?/#]+)", track_url)
    if not match:
        return None
    track = {
        "id": match.group(1),
        "name": candidate.title,
        "external_urls": {"spotify": track_url},
        "artists": [{"name": candidate.artist}],
        "album": {"name": candidate.style_hint or "Recent Spotify discovery", "images": []},
    }
    card = build_track_card(track, source_entity=candidate.artist)
    if card:
        card.metadata["recommendation_source"] = candidate.source_type
        card.metadata["recommendation_artist"] = candidate.artist
        card.metadata["recommendation_title"] = candidate.title
        card.metadata["recommendation_style"] = candidate.style_hint or ""
        card.metadata["recommendation_sources"] = ", ".join(candidate.source_names)
        card.metadata["recommendation_evidence"] = candidate.evidence
        card.metadata["recommendation_reason"] = candidate.reason
        card.metadata["recommendation_score"] = f"{candidate.score:.3f}"
    return card


def _track_card_for_candidate(candidate: MusicTrackCandidate, *, market: str) -> SpotifyCard | None:
    """
    Explanation:
    Dynamic recommendation candidates have already been selected from answer evidence or trusted-source search.
    Spotify is only allowed to resolve the exact title+artist pair into a playable card.
    """
    if candidate.source_type == "spotify_fallback":
        direct_card = _track_card_from_spotify_candidate(candidate)
        if direct_card:
            return direct_card

    track = find_validated_track(candidate.title, candidate.artist, market=market)
    card = build_track_card(track, source_entity=candidate.artist) if track else None
    if not card:
        return None

    card.metadata["recommendation_source"] = candidate.source_type
    card.metadata["recommendation_artist"] = candidate.artist
    card.metadata["recommendation_title"] = candidate.title
    card.metadata["recommendation_style"] = candidate.style_hint or ""
    card.metadata["recommendation_sources"] = ", ".join(candidate.source_names)
    card.metadata["recommendation_evidence"] = candidate.evidence
    card.metadata["recommendation_reason"] = candidate.reason
    card.metadata["recommendation_score"] = f"{candidate.score:.3f}"
    return card


def _track_cards_for_recommendation_plan(
    recommendation_plan: MusicRecommendationPlan | None,
    *,
    max_cards: int,
    market: str,
) -> list[SpotifyCard]:
    if not recommendation_plan or not recommendation_plan.candidate_tracks:
        return []

    cards: list[SpotifyCard] = []
    seen_urls: set[str] = set()
    for candidate in recommendation_plan.candidate_tracks:
        card = _track_card_for_candidate(candidate, market=market)
        if not card or card.spotify_url in seen_urls:
            continue
        seen_urls.add(card.spotify_url)
        cards.append(card)
        if len(cards) >= max_cards:
            break
    return cards


def _artist_top_track_cards(artist_name: str, *, max_tracks: int, market: str) -> list[SpotifyCard]:
    artist = search_artist(artist_name, market=market)
    if not artist:
        return []

    cards: list[SpotifyCard] = []
    artist_card = build_artist_card(artist, source_entity=artist_name)
    if artist_card:
        cards.append(artist_card)

    try:
        tracks = get_artist_top_tracks(artist["id"], market=market)
    except Exception:
        tracks = []
    for track in tracks[:max_tracks]:
        card = build_track_card(track, source_entity=artist_name)
        if card:
            cards.append(card)
    return cards


def _album_sort_key(item: dict) -> tuple[int, str]:
    # Prefer full albums, then newest releases when top-track evidence is not enough.
    album_type = item.get("album_type") or item.get("type") or ""
    priority = 0 if album_type == "album" else 1
    return priority, str(item.get("release_date") or "")


def _album_artists_text(item: dict) -> str:
    return " ".join(artist.get("name", "") for artist in item.get("artists", []) if artist.get("name"))


def _artist_album_cards(artist_name: str, *, max_albums: int, market: str) -> list[SpotifyCard]:
    # Use top-track album frequency as a popularity proxy, then fill from artist albums if needed.
    artist = search_artist(artist_name, market=market)
    if not artist:
        return []

    albums_by_id: dict[str, dict] = {}
    popularity_counts: dict[str, int] = {}
    try:
        tracks = get_artist_top_tracks(artist["id"], market=market)
    except Exception:
        tracks = []
    for track in tracks:
        album = track.get("album") or {}
        album_id = album.get("id")
        if not album_id:
            continue
        if _token_overlap(artist.get("name", artist_name), _album_artists_text(album)) < 0.5:
            continue
        albums_by_id[album_id] = album
        popularity_counts[album_id] = popularity_counts.get(album_id, 0) + 1

    try:
        artist_albums = get_artist_albums(artist["id"], market=market)
    except Exception:
        artist_albums = []
    for album in sorted(artist_albums, key=_album_sort_key):
        album_id = album.get("id")
        if not album_id or album_id in albums_by_id:
            continue
        albums_by_id[album_id] = album

    sorted_albums = sorted(
        albums_by_id.values(),
        key=lambda item: (
            -popularity_counts.get(item.get("id"), 0),
            0 if item.get("album_type") == "album" else 1,
            str(item.get("release_date") or ""),
        ),
    )

    cards: list[SpotifyCard] = []
    seen_urls: set[str] = set()
    for album in sorted_albums:
        card = build_album_card(album, source_entity=artist.get("name") or artist_name)
        if not card or card.spotify_url in seen_urls:
            continue
        card.metadata["selection_reason"] = "Selected from Spotify artist albums and top-track album signals."
        card.metadata["source_artist"] = artist.get("name") or artist_name
        seen_urls.add(card.spotify_url)
        cards.append(card)
        if len(cards) >= max_albums:
            break
    return cards


def build_spotify_cards_for_entities(
    ranked_entities: list[RankedMusicEntity],
    query_understanding: QueryUnderstandingResult,
    *,
    recommendation_plan: MusicRecommendationPlan | None = None,
    max_cards: int = 8,
    market: str = "US",
) -> list[SpotifyCard]:
    if not query_understanding.needs_spotify or not spotify_credentials_ready():
        return []

    cards: list[SpotifyCard] = []
    target = query_understanding.spotify_display_target
    if target in {"representative_tracks", "optional_representative_tracks", "tracks"}:
        plan_cards: list[SpotifyCard] = []
        if recommendation_plan and recommendation_plan.question_type in {"trending_tracks", "track_recommendation", "playlist_discovery"}:
            # Current/track recommendation questions need dynamic evidence before any curated fallback.
            plan_cards = _track_cards_for_recommendation_plan(
                recommendation_plan,
                max_cards=max_cards,
                market=market,
            )
            cards.extend(plan_cards)
        if recommendation_plan and recommendation_plan.question_type in {"trending_tracks", "track_recommendation", "playlist_discovery"}:
            # If live/current-source discovery does not resolve exact Spotify tracks,
            # fall back to curated genre examples instead of showing an empty player.
            if cards:
                return cards[:max_cards]

    if target in {"representative_tracks", "optional_representative_tracks"}:
        # Definition/profile pages should lead with curated representative tracks to avoid noisy search candidates.
        cards.extend(
            _source_grounded_track_cards_for_genre(
                query_understanding.genre_hint,
                max_cards=max_cards,
                market=market,
            )
        )
        if len(cards) >= max_cards:
            return cards[:max_cards]
        cards.extend(
            _track_cards_for_recommendation_plan(
                recommendation_plan,
                max_cards=max_cards - len(cards),
                market=market,
            )
        )
        if len(cards) >= max_cards:
            return cards[:max_cards]

        artist_names: list[str] = []
        for entity in ranked_entities:
            if entity.type == "artist":
                artist_names.append(entity.name)
            for related in entity.related_entities:
                if related.type == "artist":
                    artist_names.append(related.name)

        seen_artists: set[str] = set()
        for artist_name in artist_names:
            key = artist_name.lower()
            if key in seen_artists:
                continue
            seen_artists.add(key)
            artist_cards = _artist_top_track_cards(artist_name, max_tracks=1, market=market)
            cards.extend(artist_cards[-1:] or artist_cards[:1])
            if len(cards) >= max_cards:
                return cards[:max_cards]

    elif target == "artist_top_tracks":
        for entity in ranked_entities:
            if entity.type != "artist":
                continue
            cards.extend(_artist_top_track_cards(entity.name, max_tracks=2, market=market))
            if len(cards) >= max_cards:
                return cards[:max_cards]

    elif target == "tracks":
        cards.extend(
            _source_grounded_track_cards_for_genre(
                query_understanding.genre_hint,
                max_cards=max_cards,
                market=market,
            )
        )
        if len(cards) >= max_cards:
            return cards[:max_cards]

        for entity in ranked_entities:
            if entity.type != "track":
                continue
            track = search_track(entity.name, market=market)
            card = build_track_card(track, source_entity=entity.name) if track else None
            if card:
                cards.append(card)
            if len(cards) >= max_cards:
                return cards[:max_cards]

    elif target == "albums":
        for entity in ranked_entities:
            if entity.type == "artist":
                cards.extend(_artist_album_cards(entity.name, max_albums=max_cards - len(cards), market=market))
                if len(cards) >= max_cards:
                    return cards[:max_cards]
                continue
            album = search_album(entity.name, market=market)
            card = build_album_card(album, source_entity=entity.name) if album else None
            if card:
                cards.append(card)
            if len(cards) >= max_cards:
                return cards[:max_cards]

    elif target == "playlists":
        query = query_understanding.genre_hint or "electronic music"
        playlist = search_playlist(query, market=market)
        card = build_playlist_card(playlist, source_entity=query) if playlist else None
        if card:
            cards.append(card)

    return cards[:max_cards]
