from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


AccessMode = Literal["official_api", "search_api"]


@dataclass(frozen=True)
class TrustedSource:
    # TrustedSource records both source purpose and access mode so routing can explain provenance.
    key: str
    name: str
    purpose: str
    url: str
    domains: tuple[str, ...]
    access_mode: AccessMode
    fetch_body: bool = False


TRUSTED_MUSIC_SOURCES: tuple[TrustedSource, ...] = (
    TrustedSource(
        key="musicbrainz",
        name="MusicBrainz",
        purpose="Song, artist, album, and release metadata",
        url="https://musicbrainz.org/",
        domains=("musicbrainz.org",),
        access_mode="official_api",
    ),
    TrustedSource(
        key="discogs",
        name="Discogs",
        purpose="Release versions, labels, vinyl, and underground electronic music metadata",
        url="https://www.discogs.com/",
        domains=("discogs.com", "api.discogs.com"),
        access_mode="official_api",
    ),
    TrustedSource(
        key="residentadvisor",
        name="Resident Advisor",
        purpose="Electronic music scenes, artists, labels, events, and editorial context",
        url="https://ra.co/",
        domains=("ra.co", "residentadvisor.net"),
        access_mode="search_api",
        fetch_body=False,
    ),
    TrustedSource(
        key="beatport",
        name="Beatport",
        purpose="Current electronic music charts, releases, tracks, labels, and DJ-oriented genre pages",
        url="https://www.beatport.com/",
        domains=("beatport.com",),
        access_mode="search_api",
        fetch_body=False,
    ),
    TrustedSource(
        key="traxsource",
        name="Traxsource",
        purpose="House, garage, soulful, and underground dance music charts and releases",
        url="https://www.traxsource.com/",
        domains=("traxsource.com",),
        access_mode="search_api",
        fetch_body=False,
    ),
    TrustedSource(
        key="billboard",
        name="Billboard",
        purpose="Mainstream and dance/electronic chart context",
        url="https://www.billboard.com/",
        domains=("billboard.com",),
        access_mode="search_api",
        fetch_body=False,
    ),
    TrustedSource(
        key="officialcharts",
        name="Official Charts",
        purpose="UK chart context for current tracks and releases",
        url="https://www.officialcharts.com/",
        domains=("officialcharts.com",),
        access_mode="search_api",
        fetch_body=False,
    ),
    TrustedSource(
        key="djmag",
        name="DJ Mag",
        purpose="Electronic music editorial, charts, artists, festivals, and scene context",
        url="https://djmag.com/",
        domains=("djmag.com",),
        access_mode="search_api",
        fetch_body=False,
    ),
    TrustedSource(
        key="mixmag",
        name="Mixmag",
        purpose="Electronic music editorial, tracks, mixes, and current club culture context",
        url="https://mixmag.net/",
        domains=("mixmag.net",),
        access_mode="search_api",
        fetch_body=False,
    ),
    TrustedSource(
        key="everynoise",
        name="Every Noise at Once",
        purpose="Music genre relationship map",
        url="https://everynoise.com/",
        domains=("everynoise.com",),
        access_mode="search_api",
        fetch_body=True,
    ),
    TrustedSource(
        key="ishkur",
        name="Ishkur's Guide",
        purpose="Electronic music genre explanations",
        url="https://music.ishkur.com/",
        domains=("music.ishkur.com", "ishkur.com"),
        access_mode="search_api",
        fetch_body=True,
    ),
    TrustedSource(
        key="rateyourmusic",
        name="Rate Your Music",
        purpose="Album, genre, and community evaluation context",
        url="https://rateyourmusic.com/",
        domains=("rateyourmusic.com",),
        access_mode="search_api",
        fetch_body=False,
    ),
    TrustedSource(
        key="allmusic",
        name="AllMusic",
        purpose="Artist and album explanatory text",
        url="https://www.allmusic.com/",
        domains=("allmusic.com",),
        access_mode="search_api",
        fetch_body=False,
    ),
    TrustedSource(
        key="spotify",
        name="Spotify Web API",
        purpose="BPM, audio features, similar songs, and listening links when configured",
        url="https://developer.spotify.com/documentation/web-api",
        domains=("spotify.com", "open.spotify.com", "api.spotify.com"),
        access_mode="search_api",
        fetch_body=False,
    ),
)


def all_trusted_domains() -> set[str]:
    # Flatten configured domains for web-retriever filtering and search API allow lists.
    domains: set[str] = set()
    for source in TRUSTED_MUSIC_SOURCES:
        domains.update(source.domains)
    return domains


def search_api_sources() -> tuple[TrustedSource, ...]:
    # Search-backed sources are safe to query through the external provider when local evidence is partial.
    return tuple(source for source in TRUSTED_MUSIC_SOURCES if source.access_mode == "search_api")


def source_for_domain(host: str) -> TrustedSource | None:
    # Resolve subdomains back to their configured source record for evidence labels and trust metadata.
    clean_host = host.lower().removeprefix("www.")
    for source in TRUSTED_MUSIC_SOURCES:
        if any(clean_host == domain or clean_host.endswith(f".{domain}") for domain in source.domains):
            return source
    return None
