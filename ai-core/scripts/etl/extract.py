"""
Step 3 of the ETL pipeline: extract clean main-content text from HTML.

Strips nav, footer, sidebar, "related links" -- these are the source of
cross-contamination because every page links to printing/wifi.

Uses `trafilatura` as the primary extractor with a `readability-lxml`
fallback. Both are well-tested on real-world HTML; trafilatura tends to
win on noisy CMS sites (Drupal, WordPress) which is what Miami's library
site looks like.

See plan: Data preparation playbook §4 step 3.

This is a SKELETON. The function shape is finalized so the orchestrator
can call it; concrete extractor invocation is a TODO.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from . import config

logger = logging.getLogger(__name__)


@dataclass
class ExtractedDoc:
    """Clean text + metadata from a single fetched page."""

    url: str                 # canonical URL (post-redirect)
    title: Optional[str]
    body_text: str           # main-content text only
    breadcrumbs: list[str]   # ["Home", "Use the Library", "Borrow"]
    word_count: int
    schema_org_json: Optional[dict]  # parsed Schema.org JSON-LD if present
    last_modified: Optional[str]     # HTTP Last-Modified header verbatim
    rejection_reason: Optional[str]  # set if extraction failed quality gates


def _strip_html_fallback(html: str) -> tuple[Optional[str], str]:
    """Last-resort extractor: strip tags with stdlib so the pipeline is
    never blocked by a missing dep.

    Returns (title, body_text). Used when both trafilatura and readability
    fail to import OR return nothing usable. Quality is not great, but
    "something" beats "the bot has no Hamilton content because trafilatura
    isn't installed in CI".
    """
    import re
    from html.parser import HTMLParser

    class _Stripper(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.parts: list[str] = []
            self.title: Optional[str] = None
            self._in_title = False
            # Skip these subtrees entirely -- they're the boilerplate we
            # explicitly want to strip per playbook §4 step 3.
            self._skip_depth = 0
            self._skip_tags = {"nav", "footer", "aside", "script", "style", "noscript"}

        def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
            if tag in self._skip_tags:
                self._skip_depth += 1
            if tag == "title":
                self._in_title = True

        def handle_endtag(self, tag: str) -> None:
            if tag in self._skip_tags and self._skip_depth > 0:
                self._skip_depth -= 1
            if tag == "title":
                self._in_title = False

        def handle_data(self, data: str) -> None:
            if self._skip_depth > 0:
                return
            if self._in_title:
                self.title = (self.title or "") + data
                return
            self.parts.append(data)

    s = _Stripper()
    try:
        s.feed(html)
    except Exception:  # noqa: BLE001 -- tolerate any parser blowup
        return None, ""
    body = re.sub(r"\s+", " ", " ".join(s.parts)).strip()
    title = s.title.strip() if s.title else None
    return title, body


def extract(html: str, url: str, last_modified: Optional[str] = None) -> ExtractedDoc:
    """Extract main-content text from a fetched HTML page.

    Strategy (degrades gracefully):
      1. trafilatura -- best on noisy CMS sites (Drupal/WordPress).
      2. readability-lxml -- fallback if trafilatura returns too little.
      3. stdlib HTMLParser strip -- last resort if neither dep is
         installed (sandbox / CI without the full requirements file).

    Quality gates from config:
      - body_text < EXTRACT_MIN_BODY_CHARS -> rejection_reason="too_short"
      - empty body / parse failure -> rejection_reason="empty"
    """
    title: Optional[str] = None
    body_text: str = ""

    # Try trafilatura first (best-quality on Miami's Drupal site).
    try:
        import trafilatura  # type: ignore

        result = trafilatura.extract(
            html,
            include_comments=False,
            include_tables=False,
            no_fallback=False,
            url=url,
        )
        if result and len(result) >= config.EXTRACT_MIN_BODY_CHARS:
            body_text = result.strip()
        try:
            metadata = trafilatura.extract_metadata(html)
            if metadata is not None:
                title = getattr(metadata, "title", None) or title
        except Exception:  # noqa: BLE001
            pass
    except ImportError:
        logger.debug("trafilatura not installed; falling back")
    except Exception as e:  # noqa: BLE001 -- never let extractor crash pipeline
        logger.warning("trafilatura failed", extra={"url": url, "error": str(e)})

    # Fallback: readability-lxml.
    if not body_text:
        try:
            from readability import Document  # type: ignore

            doc = Document(html)
            title = title or doc.short_title()
            body_text = (doc.summary() or "").strip()
            if body_text:
                # readability returns HTML fragments; strip tags.
                _, body_text = _strip_html_fallback(body_text)
        except ImportError:
            pass
        except Exception as e:  # noqa: BLE001
            logger.warning("readability failed", extra={"url": url, "error": str(e)})

    # Final fallback: stdlib stripper.
    if not body_text:
        title_fb, body_text = _strip_html_fallback(html)
        title = title or title_fb

    if not body_text:
        return ExtractedDoc(
            url=url, title=title, body_text="", breadcrumbs=[],
            word_count=0, schema_org_json=None, last_modified=last_modified,
            rejection_reason="empty",
        )
    if len(body_text) < config.EXTRACT_MIN_BODY_CHARS:
        return ExtractedDoc(
            url=url, title=title, body_text="", breadcrumbs=[],
            word_count=0, schema_org_json=None, last_modified=last_modified,
            rejection_reason="too_short",
        )

    word_count = len(body_text.split())
    return ExtractedDoc(
        url=url,
        title=title,
        body_text=body_text,
        breadcrumbs=[],
        word_count=word_count,
        schema_org_json=None,
        last_modified=last_modified,
        rejection_reason=None,
    )
