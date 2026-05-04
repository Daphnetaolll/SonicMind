from __future__ import annotations

import os

from src.evidence import EvidenceItem
from src.retrievers.http_search import chunk_text, domain_from_url, fetch_text, strip_html
from src.retrievers.search_api import search_web
from src.retrievers.trusted_sources import all_trusted_domains


def _fetch_timeout() -> int:
    return int(os.getenv("EXTERNAL_FETCH_TIMEOUT", "12"))


def _fetch_web_pages_enabled() -> bool:
    return os.getenv("WEB_FETCH_RESULT_PAGES", "false").strip().lower() in {"1", "true", "yes"}


def retrieve_web_evidence(query: str, *, max_results: int = 4, timeout: int = 12) -> list[EvidenceItem]:
    # Convert general search results into low-trust evidence after local and trusted-site sources fall short.
    hits = search_web(query, max_results=max_results)
    evidence: list[EvidenceItem] = []
    trusted_domains = all_trusted_domains()

    for hit in hits:
        host = domain_from_url(hit.url)
        full_text = hit.snippet
        # Optional page fetching enriches non-trusted search hits without refetching known trusted domains.
        if _fetch_web_pages_enabled() and not any(
            host == domain or host.endswith(f".{domain}") for domain in trusted_domains
        ):
            try:
                chunks = chunk_text(strip_html(fetch_text(hit.url, timeout=_fetch_timeout())))
            except Exception:
                chunks = []
            if chunks:
                full_text = chunks[0]

        if not full_text:
            continue

        # Assign simple descending scores because external search APIs do not share one common scoring scale.
        evidence.append(
            EvidenceItem(
                rank=len(evidence) + 1,
                source_type="web",
                source_name=hit.source_name or host,
                title=hit.title,
                snippet=hit.snippet or full_text[:280],
                full_text=full_text,
                retrieval_score=max(0.25, 0.78 - (len(evidence) * 0.08)),
                trust_level="low",
                url=hit.url,
                metadata={
                    "access_mode": "formal_search_api",
                    "provider": os.getenv("WEB_SEARCH_PROVIDER", "tavily"),
                },
            )
        )
        if len(evidence) >= max_results:
            break

    return evidence
