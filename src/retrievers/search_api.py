from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from urllib import error, parse, request

from src.retrievers.http_search import domain_from_url


BRAVE_WEB_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"
TAVILY_SEARCH_URL = "https://api.tavily.com/search"


@dataclass
class SearchHit:
    # SearchHit is the provider-neutral shape consumed by site, web, and recommendation retrieval.
    title: str
    url: str
    snippet: str
    source_name: str


def _search_provider() -> str:
    return os.getenv("WEB_SEARCH_PROVIDER", "tavily").strip().lower()


def _fetch_timeout() -> int:
    return int(os.getenv("EXTERNAL_FETCH_TIMEOUT", "12"))


def _brave_api_key() -> str | None:
    return _usable_api_key(os.getenv("BRAVE_SEARCH_API_KEY") or os.getenv("WEB_SEARCH_API_KEY"))


def _tavily_api_key() -> str | None:
    return _usable_api_key(os.getenv("TAVILY_API_KEY") or os.getenv("WEB_SEARCH_API_KEY"))


def _usable_api_key(value: str | None) -> str | None:
    # Treat placeholder strings as missing keys so examples do not trigger external requests.
    if not value:
        return None
    cleaned = value.strip()
    if cleaned.lower() in {"your_key", "your_api_key", "your_tavily_api_key", "replace_me"}:
        return None
    return cleaned


def _clean_snippet(value: str | list[str] | None) -> str:
    if isinstance(value, list):
        value = " ".join(item for item in value if item)
    if not value:
        return ""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", str(value))).strip()


def search_web(
    query: str,
    *,
    max_results: int = 5,
    allowed_domains: set[str] | None = None,
) -> list[SearchHit]:
    # Dispatch through the configured provider while keeping downstream retrieval provider-agnostic.
    provider = _search_provider()
    if provider == "tavily":
        return search_tavily(query, max_results=max_results, allowed_domains=allowed_domains)
    if provider == "brave":
        return search_brave(query, max_results=max_results, allowed_domains=allowed_domains)

    raise ValueError(f"Unsupported WEB_SEARCH_PROVIDER: {provider}")


def search_tavily(
    query: str,
    *,
    max_results: int = 5,
    allowed_domains: set[str] | None = None,
) -> list[SearchHit]:
    # Tavily supports domain include lists, which keeps trusted-source searches constrained.
    api_key = _tavily_api_key()
    if not api_key:
        return []

    search_depth = os.getenv("TAVILY_SEARCH_DEPTH", "basic")
    include_raw = os.getenv("TAVILY_INCLUDE_RAW_CONTENT", "false").strip().lower() in {"1", "true", "yes"}
    payload = {
        "query": query,
        "search_depth": search_depth,
        "max_results": max_results,
        "topic": os.getenv("TAVILY_TOPIC", "general"),
        "include_answer": False,
        "include_raw_content": "text" if include_raw else False,
        "include_images": False,
        "include_favicon": True,
    }
    if search_depth == "advanced":
        payload["chunks_per_source"] = int(os.getenv("TAVILY_CHUNKS_PER_SOURCE", "3"))
    if allowed_domains:
        payload["include_domains"] = sorted(allowed_domains)

    req = request.Request(
        url=TAVILY_SEARCH_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=_fetch_timeout()) as resp:
            raw = resp.read().decode("utf-8")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Tavily Search API failed: HTTP {exc.code} {detail}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Tavily Search API failed: {exc.reason}") from exc

    data = json.loads(raw)
    hits: list[SearchHit] = []
    for item in data.get("results", []):
        item_url = item.get("url") or ""
        if not item_url.startswith("http"):
            continue
        host = domain_from_url(item_url)
        if allowed_domains and not any(host == domain or host.endswith(f".{domain}") for domain in allowed_domains):
            continue

        raw_content = item.get("raw_content") or ""
        content = raw_content if include_raw and raw_content else item.get("content")
        hits.append(
            SearchHit(
                title=item.get("title") or host,
                url=item_url,
                snippet=_clean_snippet(content),
                source_name=host,
            )
        )
        if len(hits) >= max_results:
            break

    return hits


def search_brave(
    query: str,
    *,
    max_results: int = 5,
    allowed_domains: set[str] | None = None,
) -> list[SearchHit]:
    # Brave search uses query parameters and post-filters domains to mirror Tavily behavior.
    api_key = _brave_api_key()
    if not api_key:
        return []

    params = {
        "q": query,
        "count": str(max_results),
        "country": os.getenv("WEB_SEARCH_COUNTRY", "us"),
        "search_lang": os.getenv("WEB_SEARCH_LANG", "en"),
        "safesearch": os.getenv("WEB_SEARCH_SAFESEARCH", "moderate"),
    }
    url = f"{BRAVE_WEB_SEARCH_URL}?{parse.urlencode(params)}"
    req = request.Request(
        url=url,
        headers={
            "Accept": "application/json",
            "X-Subscription-Token": api_key,
        },
        method="GET",
    )

    try:
        with request.urlopen(req, timeout=_fetch_timeout()) as resp:
            raw = resp.read().decode("utf-8")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Brave Search API failed: HTTP {exc.code} {detail}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Brave Search API failed: {exc.reason}") from exc

    data = json.loads(raw)
    results = data.get("web", {}).get("results", [])
    hits: list[SearchHit] = []
    for item in results:
        item_url = item.get("url") or ""
        if not item_url.startswith("http"):
            continue
        host = domain_from_url(item_url)
        if allowed_domains and not any(host == domain or host.endswith(f".{domain}") for domain in allowed_domains):
            continue

        profile = item.get("profile") or {}
        snippet = _clean_snippet(item.get("description")) or _clean_snippet(item.get("extra_snippets"))
        hits.append(
            SearchHit(
                title=item.get("title") or host,
                url=item_url,
                snippet=snippet,
                source_name=profile.get("long_name") or profile.get("name") or host,
            )
        )
        if len(hits) >= max_results:
            break

    return hits
