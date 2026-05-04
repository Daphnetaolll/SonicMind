from __future__ import annotations

import re
from urllib import parse, request


USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def fetch_text(url: str, timeout: int = 12) -> str:
    # Fetch HTML with a browser-like user agent for source pages that reject default Python clients.
    req = request.Request(
        url=url,
        headers={"User-Agent": USER_AGENT},
        method="GET",
    )
    with request.urlopen(req, timeout=timeout) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        return resp.read().decode(charset, errors="ignore")


def normalize_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def strip_html(raw_html: str) -> str:
    # Remove non-content HTML blocks before chunking fetched source pages.
    text = re.sub(r"(?is)<script.*?>.*?</script>", " ", raw_html)
    text = re.sub(r"(?is)<style.*?>.*?</style>", " ", text)
    text = re.sub(r"(?is)<noscript.*?>.*?</noscript>", " ", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    return normalize_text(text)


def chunk_text(text: str, chunk_size: int = 1200, overlap: int = 150) -> list[str]:
    # Split fetched page text into overlapping chunks so evidence keeps local context.
    items: list[str] = []
    if not text:
        return items

    step = max(1, chunk_size - overlap)
    for start in range(0, len(text), step):
        chunk = text[start : start + chunk_size].strip()
        if chunk:
            items.append(chunk)
    return items


def domain_from_url(url: str) -> str:
    host = parse.urlparse(url).netloc.lower()
    return host.removeprefix("www.")
