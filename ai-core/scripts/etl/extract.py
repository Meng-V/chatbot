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
import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urljoin

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
    redirect_to: Optional[str] = None
    """Set when the page is a content-less redirect shim (vanity short
    URL like /adobe/, /askus). The pipeline re-fetches this target
    instead of dropping the page. The ETL fetcher follows HTTP 3xx but
    NOT <meta refresh> / JS / canonical-only shims, so without this a
    librarian-handed-out short URL silently never reaches the index."""


# Miami vanity URLs redirect via <meta http-equiv=refresh> and/or a
# lone <link rel=canonical> (no <body>). Content may have a space
# after `url=` (observed: `content="0; url= https://..."`). Both
# patterns are case-insensitive and quote-tolerant.
_META_REFRESH_RE = re.compile(
    r'<meta[^>]+http-equiv=["\']?refresh["\']?[^>]*content=["\']([^"\']+)["\']',
    re.IGNORECASE,
)
_REFRESH_URL_RE = re.compile(r'url\s*=\s*([^\s"\'>]+)', re.IGNORECASE)
_CANONICAL_RE = re.compile(
    r'<link[^>]+rel=["\']?canonical["\']?[^>]*href=["\']([^"\']+)["\']',
    re.IGNORECASE,
)


# Rejection reason for a page that was fetched fine and whose HTML is
# substantial, but which carries no extractable article text -- almost always
# client-side rendering. Deliberately NOT "empty": an empty response means the
# page is gone, while this means our crawler cannot read a page that is very
# much alive, and the two must never lead to the same action.
NO_EXTRACTABLE_TEXT = "no_extractable_text"

# Above this much HTML, "no article text" means a client-rendered shell rather
# than a page with nothing on it. /about/locations/hours/ is 33KB of chrome
# wrapped around 8 LibCal widget <script> tags; /use/borrow/reserves/ is a
# 553-byte stub. Both extract to nothing and they are not the same problem.
SHELL_MIN_HTML_CHARS = 4000


def _norm_url(u: str) -> str:
    return (u or "").rstrip("/").lower()


def find_redirect_target(html: str, base_url: str) -> Optional[str]:
    """Return the destination of a redirect SHIM, or None.

    Called only on the empty/too_short path -- a stub page with a
    `<meta refresh>` or a lone `<link rel=canonical>` pointing
    elsewhere is a redirect, not real content. Relative targets are
    resolved against base_url. Returns None if there's no shim (e.g.
    an Apache "300 Multiple Choices" page is genuine junk -> stays
    rejected)."""
    if not html:
        return None
    m = _META_REFRESH_RE.search(html)
    if m:
        mu = _REFRESH_URL_RE.search(m.group(1))
        if mu:
            tgt = urljoin(base_url, mu.group(1).strip())
            if _norm_url(tgt) != _norm_url(base_url):
                return tgt
    m = _CANONICAL_RE.search(html)
    if m:
        tgt = urljoin(base_url, m.group(1).strip())
        if _norm_url(tgt) != _norm_url(base_url):
            return tgt
    return None


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
    # Did the GOOD extractor actually get to run? The fallback chain below was
    # built for "the dependency isn't installed", but it also fired when
    # trafilatura ran fine and reported that the page has no article content --
    # and then the stdlib tag-stripper's scrape of the NAV MENU won, and was
    # recorded as a successful extraction because a menu is longer than 200
    # characters.
    #
    # That is how the 2026-08-03 refresh came to propose deleting 285 chunks of
    # live service content: /use/technology/printing/ is 28.9KB of HTML whose
    # words "per page", "PaperCut" and "cents" appear ZERO times -- the site is
    # client-rendered now -- so all we could scrape was its menu, and the
    # pipeline treated that as the page.
    trafilatura_ran = False
    trafilatura_chars = 0

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
        trafilatura_ran = True
        trafilatura_chars = len(result or "")
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

    # Fallback: readability-lxml -- same rule as the stdlib stripper below.
    # readability is a boilerplate GUESSER: handed a content-less shell it
    # happily returns the navigation menu, which is exactly what it did for
    # /use/technology/printing/ (231 chars of menu from 28.9KB of chrome).
    # It is a fallback for "trafilatura is missing", not a second opinion.
    if not body_text and not trafilatura_ran:
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

    # Final fallback: stdlib stripper -- ONLY when no real extractor got a
    # verdict. If trafilatura ran and found next to nothing, that IS the
    # verdict: this page carries no extractable article text. A tag-stripper
    # cannot know better; it can only scrape chrome.
    if not body_text and not trafilatura_ran:
        title_fb, body_text = _strip_html_fallback(html)
        title = title or title_fb

    if not body_text and trafilatura_ran and len(html or "") >= SHELL_MIN_HTML_CHARS:
        # A SUBSTANTIAL page that yields no article text: a client-rendered
        # shell. The size test matters -- a genuinely empty or stub response is
        # "empty"/"too_short" (the page has nothing), while this is "the page
        # has plenty and we cannot read it". Same output, opposite causes, and
        # only one of them is a crawler bug to fix.
        # Keep a title if we can, purely so the reject row is readable.
        title_fb, _ = _strip_html_fallback(html)
        return ExtractedDoc(
            url=url, title=title or title_fb, body_text="", breadcrumbs=[],
            word_count=0, schema_org_json=None, last_modified=last_modified,
            # A distinct reason, not "empty": the fetch worked and the HTML is
            # substantial, so this is "we cannot READ this page", which is a
            # crawler problem to fix -- not a page that went away. The
            # tombstone step keys off this to avoid deleting what it failed to
            # re-read.
            rejection_reason=NO_EXTRACTABLE_TEXT,
            redirect_to=find_redirect_target(html, url),
        )

    if not body_text:
        # Small page, nothing from trafilatura -- scrape it. On a stub there is
        # no chrome to mistake for content, so the old behaviour is right here.
        title_fb, body_text = _strip_html_fallback(html)
        title = title or title_fb

    if not body_text:
        return ExtractedDoc(
            url=url, title=title, body_text="", breadcrumbs=[],
            word_count=0, schema_org_json=None, last_modified=last_modified,
            rejection_reason="empty",
            redirect_to=find_redirect_target(html, url),
        )
    if len(body_text) < config.EXTRACT_MIN_BODY_CHARS:
        return ExtractedDoc(
            url=url, title=title, body_text="", breadcrumbs=[],
            word_count=0, schema_org_json=None, last_modified=last_modified,
            rejection_reason="too_short",
            redirect_to=find_redirect_target(html, url),
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
