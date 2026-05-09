from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from src.retrievers.http_search import domain_from_url
from src.retrievers.search_api import SearchHit, search_web
from src.retrievers.trusted_sources import source_for_domain


DISCOVERY_DOMAINS = {
    "allmusic.com",
    "beatport.com",
    "billboard.com",
    "djmag.com",
    "discogs.com",
    "everynoise.com",
    "ishkur.com",
    "mixmag.net",
    "music.ishkur.com",
    "musicbrainz.org",
    "officialcharts.com",
    "ra.co",
    "rateyourmusic.com",
    "residentadvisor.net",
    "spotify.com",
    "traxsource.com",
}

NOISY_CANDIDATE_TERMS = {
    "album",
    "albums",
    "allmusic",
    "artist",
    "artists",
    "best",
    "best of",
    "box set",
    "chart",
    "chart by",
    "charts",
    "classic labels",
    "compilation",
    "discogs",
    "essential",
    "guide",
    "ishkur",
    "label",
    "labels",
    "musicbrainz",
    "playlist",
    "rate your music",
    "replies",
    "reply",
    "release",
    "releases",
    "resident advisor",
    "review",
    "reviews",
    "songs",
    "style",
    "super tracks",
    "tracks",
    "various artists",
    "various",
}

FORMAT_METADATA_PATTERN = re.compile(
    r"\b(?:\d+\s*x\s*)?(?:cd|lp|vinyl|compilation|mixed|box\s+set|album|ep|single|mixtape)\b",
    re.I,
)


@dataclass
class TrackCandidate:
    title: str
    artist: str
    sources: set[str] = field(default_factory=set)
    urls: set[str] = field(default_factory=set)
    score: float = 0.0


def _clean_text(value: str) -> str:
    cleaned = value.replace("\u2013", "-").replace("\u2014", "-").replace("\u2212", "-")
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def _clean_candidate_piece(value: str) -> str:
    value = _clean_text(value)
    value = re.split(r"\s+[|/]\s+", value, maxsplit=1)[0]
    value = re.sub(r"\s+-\s+(Discogs|MusicBrainz|AllMusic|Rate Your Music|Resident Advisor).*$", "", value, flags=re.I)
    value = re.sub(r"\s*\([^)]*(mix|remix|edit|version|remaster|live|official video)[^)]*\)\s*$", "", value, flags=re.I)
    value = value.strip(" \"'.,;:[]{}")
    if value.startswith("(") and value.endswith(")"):
        value = value[1:-1].strip()
    return value


def _is_noise(value: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()
    if not normalized or len(normalized) < 2 or len(normalized) > 80:
        return True
    if normalized in NOISY_CANDIDATE_TERMS:
        return True
    if any(term == normalized for term in NOISY_CANDIDATE_TERMS):
        return True
    if any(source in normalized for source in ("allmusic", "discogs", "musicbrainz", "resident advisor", "ishkur", "every noise")):
        return True
    if normalized.startswith(("top ", "best ", "history of ", "guide to ")):
        return True
    # Reject short remixer/credit-looking fragments that Spotify can mistake for track titles.
    if normalized.endswith((" remix", " edit", " version")) and len(normalized.split()) <= 3:
        return True
    if any(len(token) == 1 for token in normalized.split()) and len(normalized.split()) <= 3:
        return True
    return not bool(re.search(r"[a-z]", normalized))


def _normalize_for_compare(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _genre_aliases(genre_hint: str) -> set[str]:
    normalized = _normalize_for_compare(genre_hint)
    aliases = {normalized}
    aliases.add(normalized.replace(" and ", " "))
    aliases.add(normalized.replace(" n ", " "))
    if "drum" in normalized and "bass" in normalized:
        aliases.update({"drum bass", "drum n bass", "dnb"})
    return {alias for alias in aliases if alias}


def _is_listing_url(url: str) -> bool:
    lowered = url.lower()
    return any(marker in lowered for marker in ("/list/", "/lists/", "/group/thread/", "/charts/top/album/", "/charts/top/ep/"))


def _looks_like_non_track_page_title(title: str) -> bool:
    normalized = _normalize_for_compare(title)
    markers = (
        "best new",
        "best of",
        "chart by",
        "charts",
        "dj top",
        "top 10",
        "top 20",
        "top 100",
        "tracks march",
        "tracks february",
        "tracks january",
    )
    return any(marker in normalized for marker in markers)


def _is_bad_artist_track_pair(artist: str, title: str, hit: SearchHit, genre_hint: str) -> bool:
    """
    Explanation:
    Search-result pages often describe compilations or forum/list pages using text that looks like "Artist - Title".
    Reject those before Spotify validation so a playable compilation does not become a recommendation.
    """
    artist_norm = _normalize_for_compare(artist)
    title_norm = _normalize_for_compare(title)
    aliases = _genre_aliases(genre_hint)

    if artist_norm in aliases or title_norm in aliases:
        return True
    if artist_norm in {"various", "various artists", "rym ultimate boxset", "kmag members"}:
        return True
    if "..." in artist or "..." in title:
        return True
    if FORMAT_METADATA_PATTERN.search(artist) or FORMAT_METADATA_PATTERN.search(title):
        return True
    if re.search(r"\b(?:reply|replies|thread|started|voted|members)\b", f"{artist} {title}", re.I):
        return True
    if re.search(r"\b(?:chart by|charts?|top 10|top 20|top 100|best new|best of)\b", f"{artist} {title}", re.I):
        return True

    generic_title_markers = ("best of", "greatest", "classic", "classics", "essential", "super tracks", "club tracks")
    if any(marker in title_norm for marker in generic_title_markers) and any(alias in title_norm for alias in aliases):
        return True

    host = domain_from_url(hit.url)
    if "discogs.com" in host and "/group/thread/" in hit.url.lower():
        return True
    return False


def _extract_middle_dot_candidates(
    candidates: dict[str, TrackCandidate],
    hit: SearchHit,
    genre_hint: str,
) -> None:
    """
    Explanation:
    Beatport chart snippets often look like "1. Track · Artist · Label".
    This source-specific parser extracts those rows instead of treating the page title as a song.
    """
    text = _clean_text(f"{hit.title}. {hit.snippet}")
    pattern = re.compile(
        r"(?:^|[.;])\s*(?:\d+\.\s*)?(?P<title>[^.;·]{2,80}?)\s+·\s+(?P<artist>[^.;·]{2,80}?)\s+·",
        re.I,
    )
    for match in pattern.finditer(text):
        _add_candidate(
            candidates,
            artist=match.group("artist"),
            title=match.group("title"),
            hit=hit,
            genre_hint=genre_hint,
            base_score=0.4,
        )


def _candidate_key(artist: str, title: str) -> str:
    normalized = f"{artist} {title}".lower()
    return re.sub(r"[^a-z0-9]+", " ", normalized).strip()


def _remove_trailing_artist_credit(title: str, artist: str) -> str:
    artist_pattern = re.escape(artist)
    return re.sub(rf"\s+by\s+{artist_pattern}\s*$", "", title, flags=re.I).strip()


def _source_name(hit: SearchHit) -> str:
    host = domain_from_url(hit.url) or hit.source_name
    source = source_for_domain(host)
    return source.name if source else host


def _source_weight(source_name: str) -> float:
    lowered = source_name.lower()
    if "discogs" in lowered or "musicbrainz" in lowered:
        return 0.34
    if "resident advisor" in lowered:
        return 0.28
    if "allmusic" in lowered or "rate your music" in lowered:
        return 0.22
    return 0.16


def _add_candidate(
    candidates: dict[str, TrackCandidate],
    *,
    artist: str,
    title: str,
    hit: SearchHit,
    genre_hint: str,
    base_score: float,
) -> None:
    artist = _clean_candidate_piece(artist)
    title = _clean_candidate_piece(title)
    title = _remove_trailing_artist_credit(title, artist)
    if _is_noise(artist) or _is_noise(title) or artist.lower() == title.lower():
        return
    if _is_bad_artist_track_pair(artist, title, hit, genre_hint):
        return

    source_name = _source_name(hit)
    key = _candidate_key(artist, title)
    if not key:
        return

    hit_text = f"{hit.title} {hit.snippet}".lower()
    genre_bonus = 0.18 if genre_hint.lower() in hit_text else 0.0
    score = base_score + _source_weight(source_name) + genre_bonus

    candidate = candidates.get(key)
    if not candidate:
        candidates[key] = TrackCandidate(title=title, artist=artist, score=score)
        candidate = candidates[key]
    else:
        candidate.score += score * 0.65

    candidate.sources.add(source_name)
    candidate.urls.add(hit.url)


def extract_track_candidates_from_hits(hits: list[SearchHit], genre_hint: str) -> list[TrackCandidate]:
    """
    Explanation:
    Spotify should not infer what represents a genre.
    This parser extracts explicit artist-track pairs from trusted-source search results before Spotify is called.
    """
    candidates: dict[str, TrackCandidate] = {}
    dash_pattern = re.compile(r"(?P<artist>[A-Za-z0-9&'()., ]{2,70})\s+-\s+(?P<title>[A-Za-z0-9&'()., ]{2,90})")
    by_pattern = re.compile(r"(?P<title>[A-Za-z0-9&'()., ]{2,90})\s+by\s+(?P<artist>[A-Za-z0-9&'()., ]{2,70})", re.I)
    quoted_by_pattern = re.compile(r'"(?P<title>[^"]{2,90})"\s+by\s+(?P<artist>[A-Za-z0-9&\'()., ]{2,70})', re.I)

    for hit in hits:
        title_text = _clean_text(hit.title)
        combined_text = _clean_text(f"{hit.title}. {hit.snippet}")
        _extract_middle_dot_candidates(candidates, hit, genre_hint)

        if not _is_listing_url(hit.url) and not _looks_like_non_track_page_title(hit.title):
            for match in dash_pattern.finditer(title_text):
                _add_candidate(
                    candidates,
                    artist=match.group("artist"),
                    title=match.group("title"),
                    hit=hit,
                    genre_hint=genre_hint,
                    base_score=0.34,
                )

        for pattern in (quoted_by_pattern, by_pattern):
            for match in pattern.finditer(combined_text):
                _add_candidate(
                    candidates,
                    artist=match.group("artist"),
                    title=match.group("title"),
                    hit=hit,
                    genre_hint=genre_hint,
                    base_score=0.24,
                )

    ranked = sorted(candidates.values(), key=lambda item: (item.score, len(item.sources)), reverse=True)
    return ranked


def discover_recommendation_for_genre(genre_hint: str | None, *, max_tracks: int = 8) -> dict[str, Any] | None:
    """
    Explanation:
    Unknown genres use Tavily/Brave only to discover source-grounded candidate tracks from a strict music-domain whitelist.
    The result is still validated later by exact Spotify title+artist matching before anything is displayed.
    """
    if not genre_hint:
        return None

    queries = [
        f'"{genre_hint}" representative tracks artists',
        f'"{genre_hint}" classic tracks',
        f'"{genre_hint}" essential tracks artists',
        f'"{genre_hint}" Discogs tracks',
    ]
    candidates_by_key: dict[str, TrackCandidate] = {}

    for query in queries:
        try:
            hits = search_web(query, max_results=6, allowed_domains=DISCOVERY_DOMAINS)
        except (RuntimeError, ValueError):
            continue
        for candidate in extract_track_candidates_from_hits(hits, genre_hint):
            key = _candidate_key(candidate.artist, candidate.title)
            existing = candidates_by_key.get(key)
            if not existing:
                candidates_by_key[key] = candidate
                continue
            existing.sources.update(candidate.sources)
            existing.urls.update(candidate.urls)
            existing.score += candidate.score * 0.75

    ranked = sorted(candidates_by_key.values(), key=lambda item: (item.score, len(item.sources)), reverse=True)
    tracks = [
        {
            "title": item.title,
            "artist": item.artist,
            "sources": sorted(item.sources),
            "source_urls": sorted(item.urls)[:3],
            "discovery_method": "trusted_search",
            "score": round(item.score, 3),
        }
        for item in ranked[:max_tracks]
    ]
    if not tracks:
        return None

    source_names = sorted({source for item in tracks for source in item.get("sources", [])})
    return {
        "explanation": (
            "Generated from trusted music-domain search results. "
            "Spotify is used only after exact title and artist validation."
        ),
        "representative_tracks": tracks,
        "sources": source_names,
    }
