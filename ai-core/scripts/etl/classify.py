"""
Step 4 of the ETL pipeline: rule-based metadata extraction.

For each (url, body) pair, derive:
  - topic       (borrow | spaces | technology | research | policy | hours | about | collections)
  - campus      (oxford | hamilton | middletown)
  - library     (king | wertz | rentschler | gardner_harvey | sword | special | None)
  - audience    (student | faculty | grad | new_student | all)
  - featured_service (adobe_checkout | ill | makerspace | digital_collections |
                      special_collections | newspapers | None)

These tags are inherited by every chunk produced from the document, and
they're what retrieval filters on. Wrong tags here cascade into wrong
answers later -- this file deserves a chunky test suite.

See plan: Data preparation playbook §4 step 4, §7 featured services, §8 scope.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

from . import config

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DocMetadata:
    """Tags applied to a document and inherited by its chunks."""

    topic: str
    campus: str
    library: Optional[str]
    audience: list[str]
    featured_service: Optional[str]


def _infer_campus(url: str) -> str:
    """Infer campus from URL host. Fallback to 'oxford'."""
    host = (urlparse(url).hostname or "").lower()
    return config.HOST_TO_CAMPUS.get(host, "oxford")


def _infer_library(url: str, body_text: str) -> Optional[str]:
    """Infer library (building) from URL substring; fall back to None.

    Body-text matching is intentionally NOT used here -- a King page that
    mentions Hamilton in passing should NOT be re-tagged as Hamilton. The
    URL is the strongest signal.
    """
    lowered = url.lower()
    for substr, lib in config.LIBRARY_BY_URL_SUBSTRING:
        if substr in lowered:
            return lib
    return None


def _infer_topic(url: str) -> str:
    """First-match-wins prefix scan over TOPIC_BY_URL_PREFIX."""
    path = urlparse(url).path or ""
    for prefix, topic in config.TOPIC_BY_URL_PREFIX:
        if path.startswith(prefix):
            return topic
    return "about"  # safe default


def _infer_featured_service(url: str) -> Optional[str]:
    """Match URL against the featured-service substring map.

    Plan §7: this single tag drives:
      - retrieval boost (chunks tagged with the same service as the
        classifier intent rank higher)
      - UrlSeen.priority = "high" so a sitemap glitch doesn't blackhole
        the highest-value pages
    """
    lowered = url.lower()
    for substr, tag in config.FEATURED_SERVICE_PATTERNS:
        if substr in lowered:
            return tag
    return None


def _infer_audience(url: str, body_text: str) -> list[str]:
    """Infer audience from URL path + simple body keywords.

    Conservative: returns ['all'] unless we see explicit student/faculty/grad
    signals. Better to under-tag than mis-tag, since audience is used as
    a filter at retrieval time.
    """
    audiences: set[str] = set()
    lowered_url = url.lower()
    if "/students/" in lowered_url or "/student/" in lowered_url:
        audiences.add("student")
    if "/faculty/" in lowered_url or "/staff/" in lowered_url:
        audiences.add("faculty")
    if "/graduate/" in lowered_url or "/grad/" in lowered_url:
        audiences.add("grad")
    if "/new-students/" in lowered_url or "first-year" in lowered_url:
        audiences.add("new_student")
    return sorted(audiences) if audiences else ["all"]


def classify(url: str, body_text: str) -> DocMetadata:
    """Apply all rule-based metadata inference to a document.

    Pure function: same inputs -> same outputs. No I/O. Easy to test.
    """
    return DocMetadata(
        topic=_infer_topic(url),
        campus=_infer_campus(url),
        library=_infer_library(url, body_text),
        audience=_infer_audience(url, body_text),
        featured_service=_infer_featured_service(url),
    )
