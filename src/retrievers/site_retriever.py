from __future__ import annotations

import json
import os
import re
from urllib import error, parse, request

from src.evidence import EvidenceItem
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
    "which",
}


def _fetch_timeout() -> int:
    return int(os.getenv("EXTERNAL_FETCH_TIMEOUT", "12"))


def _user_agent() -> str:
    return os.getenv(
        "MUSIC_METADATA_USER_AGENT",
        "rag-agent-web-public-mvp/0.1 (https://github.com)",
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


def _whitelisted_search_evidence(query: str, *, max_results: int = 4) -> list[EvidenceItem]:
    sources = search_api_sources()
    allowed_domains = {domain for source in sources for domain in source.domains}
    if not allowed_domains:
        return []

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
        if _is_low_quality_search_hit(query, hit.title, hit.snippet):
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
    evidence.extend(_musicbrainz_evidence(query, max_results=2))
    evidence.extend(_discogs_evidence(query, max_results=2))
    evidence.extend(_whitelisted_search_evidence(query, max_results=max(0, max_results - len(evidence))))

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
