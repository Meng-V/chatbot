"""
Step 1 of the ETL pipeline: discover URLs to crawl.

Pulls each campus's sitemap (with seed-URL fallback for sites that don't
publish one), filters out excluded prefixes (news/events/test/staging),
and returns a deduplicated set of URLs to fetch.

See plan: Data preparation playbook §4 step 1, §8 multi-domain handling.

This is a SKELETON. The actual sitemap-parsing logic is intentionally
left as a TODO with a clear interface so the next implementer doesn't
have to reverse-engineer the contract.
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

import requests

from . import config

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DiscoveredUrl:
    """A single URL discovered during the crawl."""

    url: str
    campus: str       # canonical campus ID, see src/scope/aliases.py
    source: str       # "sitemap" | "seed" | "manual"


def _is_library_url(url: str) -> bool:
    """Return True if `url` matches the positive library-content allowlist.

    A URL is library content if EITHER:
      - its host starts with one of LIBRARY_HOST_PREFIXES (`lib.`, `www.lib.`), OR
      - its path contains one of LIBRARY_PATH_SUBSTRINGS (`/library/`).

    Required because Middletown's sitemap 308-redirects to a regional
    sitemap with 2,487 entries of which zero are library content. Without
    this filter, the ETL would crawl ~2,300 non-library URLs and produce
    hundreds of TooManyRedirects fetch failures on marketing-comms pages.
    See findings/2026-05-13_etl_first_run.md.
    """
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    path = parsed.path or ""
    for host_prefix in config.LIBRARY_HOST_PREFIXES:
        if host.startswith(host_prefix):
            return True
    for path_substr in config.LIBRARY_PATH_SUBSTRINGS:
        if path_substr in path:
            return True
    return False


def _is_excluded(url: str) -> tuple[bool, Optional[str]]:
    """Return (excluded?, reason) for a URL.

    Three checks, in order:
      1. Positive library-content gate (host=lib.* or path contains
         /library/). Anything outside this is rejected with
         reason="not_library_url" -- the cheapest possible reject.
      2. Path-prefix exclusion list (news, events, exhibits, internal
         `/_*` template paths).
      3. Substring exclusion (404 pages, test pages, READMEs).
    """
    if not _is_library_url(url):
        return True, "not_library_url"
    parsed = urlparse(url)
    path = parsed.path or ""
    for prefix in config.EXCLUDE_URL_PREFIXES:
        if path.startswith(prefix):
            return True, f"prefix={prefix}"
    lowered = url.lower()
    for substr in config.EXCLUDE_URL_SUBSTRINGS:
        if substr in lowered:
            return True, f"substring={substr}"
    return False, None


def _fetch_sitemap(sitemap_url: str) -> list[str]:
    """Fetch a sitemap.xml and return the list of <loc> URLs.

    Returns an empty list on any failure -- caller falls back to seed URLs.
    """
    try:
        resp = requests.get(
            sitemap_url,
            timeout=config.REQUEST_TIMEOUT_SECONDS,
            headers={"User-Agent": config.USER_AGENT},
            verify=urlparse(sitemap_url).hostname not in config.TLS_SKIP_ALLOWLIST,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.warning("sitemap fetch failed", extra={"url": sitemap_url, "error": str(e)})
        return []

    try:
        root = ET.fromstring(resp.content)
        # Strip namespace -- sitemap XML uses xmlns; .findall("loc") won't match.
        ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        return [loc.text.strip() for loc in root.findall(".//sm:loc", ns) if loc.text]
    except ET.ParseError as e:
        logger.warning("sitemap parse failed", extra={"url": sitemap_url, "error": str(e)})
        return []


def discover() -> list[DiscoveredUrl]:
    """Discover all URLs to crawl across all campus domains.

    Returns:
        List of DiscoveredUrl, deduplicated by URL (first-source-wins).
    """
    seen: dict[str, DiscoveredUrl] = {}
    rejected: list[tuple[str, str]] = []  # (url, reason)

    for campus, sitemap_url in config.SITEMAPS.items():
        urls = _fetch_sitemap(sitemap_url)
        sitemap_used = bool(urls)

        if not sitemap_used:
            # Fall back to hand-curated seed URLs for this campus.
            urls = config.SEED_URLS.get(campus, [])
            source = "seed"
            logger.info(
                "sitemap empty/missing, using seed URLs",
                extra={"campus": campus, "n_seeds": len(urls)},
            )
        else:
            source = "sitemap"

        kept_for_campus = 0
        for url in urls:
            excluded, reason = _is_excluded(url)
            if excluded:
                rejected.append((url, reason or "unknown"))
                continue
            if url not in seen:
                seen[url] = DiscoveredUrl(url=url, campus=campus, source=source)
                kept_for_campus += 1

        # Sitemap-then-empty-after-filter recovery: if the sitemap was
        # non-empty but the positive library-content filter drained the
        # entire batch (real case: Middletown's sitemap 308-redirects to
        # the regional sitemap with 2,487 non-library URLs), retry with
        # the seed URLs so the campus isn't silently dropped from the
        # corpus.
        if sitemap_used and kept_for_campus == 0:
            seed_urls = config.SEED_URLS.get(campus, [])
            if seed_urls:
                logger.info(
                    "sitemap returned only non-library URLs, falling back to seeds",
                    extra={"campus": campus, "n_seeds": len(seed_urls)},
                )
                for url in seed_urls:
                    excluded, reason = _is_excluded(url)
                    if excluded:
                        rejected.append((url, reason or "unknown"))
                        continue
                    if url not in seen:
                        seen[url] = DiscoveredUrl(
                            url=url, campus=campus, source="seed",
                        )

    logger.info(
        "discovery complete",
        extra={
            "kept": len(seen),
            "rejected": len(rejected),
            "by_campus": {
                c: sum(1 for d in seen.values() if d.campus == c)
                for c in config.SITEMAPS
            },
        },
    )
    return list(seen.values())
