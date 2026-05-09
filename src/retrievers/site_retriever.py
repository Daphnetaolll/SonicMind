from __future__ import annotations

import json
import os
import re
from urllib import error, parse, request

from src.evidence import EvidenceItem
from src.music.query_understanding import understand_query
from src.retrievers.http_search import chunk_text, domain_from_url, fetch_text, strip_html
from src.retrievers.search_api import search_web
from src.retrievers.trusted_sources import TRUSTED_MUSIC_SOURCES, search_api_sources, source_for_domain


MUSICBRAINZ_BASE_URL = "https://musicbrainz.org/ws/2"
DISCOGS_BASE_URL = "https://api.discogs.com"
STOPWORDS = {
    "about",
    "are",
    "does",
    "genre",
    "genres",
    "its",
    "main",
    "music",
    "subgenre",
    "subgenres",
    "the",
    "their",
    "this",
    "what",
    "who",
    "which",
}


def _fetch_timeout() -> int:
    return int(os.getenv("EXTERNAL_FETCH_TIMEOUT", "12"))


def _user_agent() -> str:
    return os.getenv(
        "MUSIC_METADATA_USER_AGENT",
        "sonicmind/0.1 (https://github.com)",
    )


def _query_keywords(query: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9][a-z0-9\-]+", query.lower())
        if token not in STOPWORDS and len(token) > 2
    }


def _matches_query_topic(query: str, *values: str) -> bool:
    keywords = _query_keywords(query)
    if not keywords:
        return True
    haystack = " ".join(values).lower()
    # Topic-overlap filtering keeps generic metadata results like "What Is" out of source lists.
    return any(keyword in haystack for keyword in keywords)


def _is_low_quality_search_hit(query: str, title: str, snippet: str) -> bool:
    normalized_title = re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()
    if normalized_title in {"what is", "what what what", "home", "search", "music"}:
        return True
    return not _matches_query_topic(query, title, snippet)


def _artist_profile_lookup_query(query: str) -> str | None:
    # Reuse music intent parsing so artist questions search for the artist name, not the whole sentence.
    understanding = understand_query(query)
    if understanding.primary_entity_type != "artist":
        return None
    for entity in understanding.entities:
        if entity.type == "artist" and entity.name:
            return entity.name
    return None


def _artist_search_query(artist_name: str) -> str:
    # Bias trusted-source search toward music-profile pages when the user supplies only a name.
    return f'"{artist_name}" music artist DJ producer'


def _artist_name_tokens(name: str) -> set[str]:
    # Artist profile lookups should require the requested name tokens, not just a shared surname.
    return {
        token
        for token in re.findall(r"[a-z0-9][a-z0-9\-]+", name.lower())
        if token not in {"dj", "producer", "artist", "music"} and len(token) > 1
    }


def _filter_artist_name_matches(evidence: list[EvidenceItem], artist_name: str) -> list[EvidenceItem]:
    required = _artist_name_tokens(artist_name)
    if not required:
        return evidence

    filtered: list[EvidenceItem] = []
    for item in evidence:
        title_tokens = _artist_name_tokens(item.title)
        if required.issubset(title_tokens):
            filtered.append(item)
    return filtered


def _json_get(url: str, *, headers: dict[str, str] | None = None) -> dict:
    merged_headers = {"Accept": "application/json", "User-Agent": _user_agent()}
    if headers:
        merged_headers.update(headers)

    req = request.Request(url=url, headers=merged_headers, method="GET")
    try:
        with request.urlopen(req, timeout=_fetch_timeout()) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (error.HTTPError, error.URLError, json.JSONDecodeError):
        return {}


def _spotify_artist_evidence(query: str, *, max_results: int = 1) -> list[EvidenceItem]:
    # Spotify artist metadata is lightweight enough for Render and helps canonicalize artist spellings.
    from src.integrations.spotify_client import get_artist_top_tracks, search_artist, spotify_credentials_ready

    if not spotify_credentials_ready():
        return []

    try:
        artist = search_artist(query)
    except Exception:
        return []
    if not artist:
        return []

    name = artist.get("name") or query
    genres = ", ".join(artist.get("genres", [])[:6])
    popularity = artist.get("popularity")
    followers = artist.get("followers", {}).get("total")
    spotify_url = artist.get("external_urls", {}).get("spotify")
    artist_id = artist.get("id")
    top_tracks: list[str] = []
    if artist_id:
        try:
            for track in get_artist_top_tracks(artist_id)[:5]:
                track_name = track.get("name")
                if track_name:
                    top_tracks.append(track_name)
        except Exception:
            top_tracks = []

    text_parts = [
        f"Spotify artist result: {name}.",
        f"Genres: {genres}." if genres else "",
        f"Popularity score: {popularity}." if popularity is not None else "",
        f"Followers: {followers}." if followers is not None else "",
        f"Top tracks include: {', '.join(top_tracks)}." if top_tracks else "",
    ]
    text = " ".join(part for part in text_parts if part)
    return [
        EvidenceItem(
            rank=1,
            source_type="site",
            source_name="Spotify",
            title=name,
            snippet=text,
            full_text=text,
            retrieval_score=0.86,
            trust_level="medium",
            url=spotify_url,
            metadata={
                "purpose": "Artist catalog metadata and top-track signals",
                "access_mode": "official_api",
                "entity": "artist",
                "genres": genres,
            },
        )
    ][:max_results]


def _musicbrainz_evidence(query: str, *, max_results: int = 3) -> list[EvidenceItem]:
    source = next(item for item in TRUSTED_MUSIC_SOURCES if item.key == "musicbrainz")
    entities = (
        ("artist", "artists"),
        ("recording", "recordings"),
        ("release-group", "release-groups"),
        ("label", "labels"),
    )
    evidence: list[EvidenceItem] = []

    for entity, response_key in entities:
        params = parse.urlencode({"query": query, "fmt": "json", "limit": "2"})
        data = _json_get(f"{MUSICBRAINZ_BASE_URL}/{entity}?{params}")
        for item in data.get(response_key, []):
            name = item.get("name") or item.get("title")
            if not name:
                continue

            disambiguation = item.get("disambiguation") or ""
            country = item.get("country") or ""
            date = item.get("first-release-date") or item.get("life-span", {}).get("begin") or ""
            tags = ", ".join(tag.get("name", "") for tag in item.get("tags", [])[:5] if tag.get("name"))
            if not _matches_query_topic(query, name, disambiguation, tags):
                continue
            text_parts = [
                f"{source.name} {entity.replace('-', ' ')} result: {name}.",
                f"Disambiguation: {disambiguation}." if disambiguation else "",
                f"Country: {country}." if country else "",
                f"Date: {date}." if date else "",
                f"Tags: {tags}." if tags else "",
            ]
            mbid = item.get("id")
            url = f"https://musicbrainz.org/{entity}/{mbid}" if mbid else source.url
            evidence.append(
                EvidenceItem(
                    rank=len(evidence) + 1,
                    source_type="site",
                    source_name=source.name,
                    title=name,
                    snippet=" ".join(part for part in text_parts if part),
                    full_text=" ".join(part for part in text_parts if part),
                    retrieval_score=max(0.75, 0.95 - (len(evidence) * 0.05)),
                    trust_level="medium",
                    url=url,
                    metadata={
                        "purpose": source.purpose,
                        "access_mode": "official_api",
                        "entity": entity,
                        "detected_entity_type": "track" if entity == "recording" else "album" if entity == "release-group" else entity,
                        "tags": tags,
                    },
                )
            )
            if len(evidence) >= max_results:
                return evidence

    return evidence


def _discogs_auth_header() -> dict[str, str]:
    token = os.getenv("DISCOGS_USER_TOKEN")
    if token:
        return {"Authorization": f"Discogs token={token}"}

    key = os.getenv("DISCOGS_CONSUMER_KEY")
    secret = os.getenv("DISCOGS_CONSUMER_SECRET")
    if key and secret:
        return {"Authorization": f"Discogs key={key}, secret={secret}"}
    return {}


def _discogs_evidence(query: str, *, max_results: int = 3) -> list[EvidenceItem]:
    source = next(item for item in TRUSTED_MUSIC_SOURCES if item.key == "discogs")
    params = parse.urlencode({"q": query, "per_page": str(max_results), "page": "1"})
    data = _json_get(f"{DISCOGS_BASE_URL}/database/search?{params}", headers=_discogs_auth_header())
    evidence: list[EvidenceItem] = []

    for item in data.get("results", [])[:max_results]:
        title = item.get("title") or "Discogs result"
        labels = ", ".join(item.get("label", [])[:3]) if isinstance(item.get("label"), list) else ""
        formats = ", ".join(item.get("format", [])[:3]) if isinstance(item.get("format"), list) else ""
        styles = ", ".join(item.get("style", [])[:5]) if isinstance(item.get("style"), list) else ""
        genres = ", ".join(item.get("genre", [])[:5]) if isinstance(item.get("genre"), list) else ""
        year = item.get("year") or ""
        if not _matches_query_topic(query, title, labels, genres, styles):
            continue
        text_parts = [
            f"Discogs result: {title}.",
            f"Year: {year}." if year else "",
            f"Labels: {labels}." if labels else "",
            f"Formats: {formats}." if formats else "",
            f"Genres: {genres}." if genres else "",
            f"Styles: {styles}." if styles else "",
        ]
        url = item.get("uri")
        if url and url.startswith("/"):
            url = f"https://www.discogs.com{url}"
        evidence.append(
            EvidenceItem(
                rank=len(evidence) + 1,
                source_type="site",
                source_name=source.name,
                title=title,
                snippet=" ".join(part for part in text_parts if part),
                full_text=" ".join(part for part in text_parts if part),
                retrieval_score=max(0.7, 0.9 - (len(evidence) * 0.06)),
                trust_level="medium",
                url=url or source.url,
                metadata={
                    "purpose": source.purpose,
                    "access_mode": "official_api",
                    "labels": labels,
                    "genres": genres,
                    "styles": styles,
                    "formats": formats,
                },
            )
        )

    return evidence


def _whitelisted_search_evidence(
    query: str,
    *,
    max_results: int = 4,
    topic_query: str | None = None,
) -> list[EvidenceItem]:
    sources = search_api_sources()
    allowed_domains = {domain for source in sources for domain in source.domains}
    if not allowed_domains or max_results <= 0:
        return []

    filter_query = topic_query or query
    site_terms = " OR ".join(f"site:{source.domains[0]}" for source in sources)
    hits = search_web(
        f"{query} ({site_terms})",
        max_results=max_results * 2,
        allowed_domains=allowed_domains,
    )
    evidence: list[EvidenceItem] = []

    for hit in hits:
        source = source_for_domain(domain_from_url(hit.url))
        if not source:
            continue
        if _is_low_quality_search_hit(filter_query, hit.title, hit.snippet):
            continue

        full_text = hit.snippet
        if source.fetch_body:
            try:
                chunks = chunk_text(strip_html(fetch_text(hit.url, timeout=_fetch_timeout())))
            except Exception:
                chunks = []
            if chunks:
                full_text = chunks[0]

        if not full_text:
            continue

        evidence.append(
            EvidenceItem(
                rank=len(evidence) + 1,
                source_type="site",
                source_name=source.name,
                title=hit.title,
                snippet=hit.snippet or full_text[:280],
                full_text=full_text,
                retrieval_score=max(0.45, 0.82 - (len(evidence) * 0.06)),
                trust_level="medium",
                url=hit.url,
                metadata={"purpose": source.purpose, "access_mode": "search_api"},
            )
        )
        if len(evidence) >= max_results:
            break

    return evidence


def retrieve_site_evidence(query: str, *, max_results: int = 6, timeout: int = 12) -> list[EvidenceItem]:
    evidence = []
    artist_lookup = _artist_profile_lookup_query(query)
    lookup_query = artist_lookup or query
    search_query = _artist_search_query(lookup_query) if artist_lookup else query

    spotify_evidence = _spotify_artist_evidence(lookup_query, max_results=1) if artist_lookup else []
    evidence.extend(spotify_evidence)
    if spotify_evidence:
        lookup_query = spotify_evidence[0].title
        search_query = _artist_search_query(lookup_query)

    musicbrainz_evidence = _musicbrainz_evidence(lookup_query, max_results=2)
    discogs_evidence = _discogs_evidence(lookup_query, max_results=2)
    if artist_lookup:
        musicbrainz_evidence = _filter_artist_name_matches(musicbrainz_evidence, lookup_query)
        discogs_evidence = _filter_artist_name_matches(discogs_evidence, lookup_query)
    evidence.extend(musicbrainz_evidence)
    evidence.extend(discogs_evidence)
    evidence.extend(
        _whitelisted_search_evidence(
            search_query,
            max_results=max(0, max_results - len(evidence)),
            topic_query=lookup_query,
        )
    )

    return [
        EvidenceItem(
            rank=idx,
            source_type=item.source_type,
            source_name=item.source_name,
            title=item.title,
            snippet=item.snippet,
            full_text=item.full_text,
            retrieval_score=item.retrieval_score,
            trust_level=item.trust_level,
            url=item.url,
            chunk_id=item.chunk_id,
            metadata=item.metadata,
        )
        for idx, item in enumerate(evidence[:max_results], start=1)
    ]
