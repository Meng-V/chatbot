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


def _is_excluded(url: str) -> tuple[bool, Optional[str]]:
    """Return (excluded?, reason) for a URL."""
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
        if not urls:
            # Fall back to hand-curated seed URLs for this campus.
            urls = config.SEED_URLS.get(campus, [])
            source = "seed"
            logger.info(
                "sitemap empty/missing, using seed URLs",
                extra={"campus": campus, "n_seeds": len(urls)},
            )
        else:
            source = "sitemap"

        for url in urls:
            excluded, reason = _is_excluded(url)
            if excluded:
                rejected.append((url, reason or "unknown"))
                continue
            if url not in seen:
                seen[url] = DiscoveredUrl(url=url, campus=campus, source=source)

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
