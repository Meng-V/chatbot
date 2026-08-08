"""LibAnswers FAQ source for the ETL.

The library runs a public FAQ at libanswers.lib.miamioh.edu -- 116 answers
written and maintained by library staff. None of it was in the corpus.
That is a real gap and not an even one: the most-asked FAQ on the site is
"How do I print in the Libraries?" (2,291 lookups), and printing is one of
the topics whose page on the main site is a shell with no prose for the
crawler to extract. Same for wi-fi, and for the NYT / WSJ / Washington
Post access questions, which together account for ~13,000 lookups.

WHY THE API AND NOT THE RENDERED PAGE
    The public FAQ page embeds a live view counter -- "Answered By: ...
    Last Updated: ... Views: 227". That number moves every day, so a
    crawl of these pages would report all 116 as CHANGED on every run,
    re-embed all of them, and bury any real edit in the diff report.
    The API returns the same answer without the counter, without the
    staff byline, and without the page chrome: 497 clean characters where
    the scrape gives 1,124 noisy ones for the same FAQ.

    Credentials are the LIBANS_* pair already in .env for ticket
    submission; `/api/1.1/faqs` needs no extra scope.

WHY THESE SKIP extract()
    extract() rejects any document under EXTRACT_MIN_BODY_CHARS (200) as
    a stub. That is the right rule for a scraped web page -- under 200
    characters of prose means the crawler found chrome, not content. It
    is the wrong rule here: 26 of the 116 FAQs are shorter than that and
    complete, because a short question truthfully answered gets a short
    answer. These documents were quality-gated by the librarian who
    wrote them, so they are built as ExtractedDoc directly rather than
    being round-tripped through HTML and re-parsed.

WHAT IS DELIBERATELY DROPPED
    - `url.admin` (the staff edit link) is never indexed; only
      `url.public`.
    - FAQs whose answer is empty after cleaning.
"""

from __future__ import annotations

import html as _html
import logging
import os
import re
from typing import Any, Callable, Iterable, Optional

from scripts.etl import classify, discover, extract

logger = logging.getLogger("etl.libanswers")

FAQ_HOST = "libanswers.lib.miamioh.edu"

# The API caps a page at 20 regardless of the `limit` we ask for, so
# paginate until a page comes back empty rather than until it comes back
# short -- a `len(page) < limit` test stops after the first page and
# silently indexes 20 of 116.
_PAGE_LIMIT = 100
_MAX_PAGES = 30

# LibAnswers' own topic names -> the corpus topic vocabulary
# (config.TOPIC_BY_URL_PREFIX values). Only unambiguous pairs are
# mapped; anything else becomes "service", which is what a question
# about using the library is. classify() would otherwise put every FAQ
# under "about" via its URL-prefix fallback, since /faq/<id> matches no
# prefix. Nothing filters on topic at retrieval time today -- this is
# metadata accuracy, not a behaviour change.
_TOPIC_MAP: dict[str, str] = {
    "circulation": "borrow",
    "checkout": "borrow",
    "access services": "borrow",
    "books": "borrow",
    "ohiolink": "borrow",
    "research": "research",
    "searching": "research",
    "citations": "research",
    "databases": "research",
    "e-resources": "research",
    "newspaper": "research",
    "technology": "technology",
    "printing": "technology",
}


class LibAnswersError(RuntimeError):
    """Raised when the API cannot be reached or refuses the credentials."""


# --- HTML -> text -----------------------------------------------------------

_TAG_RE = re.compile(r"<[^>]+>")
_SCRIPT_RE = re.compile(r"(?is)<(script|style)[^>]*>.*?</\1>")
_ANCHOR_RE = re.compile(r"(?is)<a[^>]*\shref=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>")
_BLOCK_RE = re.compile(r"(?i)</(p|div|li|ul|ol|h[1-6]|tr)\s*>|<br\s*/?>")


def _anchor_to_text(m: "re.Match[str]") -> str:
    """`<a href="X">label</a>` -> `label (X)`.

    125 of the 170 anchors in these answers have a prose label, so
    dropping the tag drops the destination -- and for a FAQ like "How do
    I renew books?" the destination IS the answer. Anchors whose label
    already spells out the URL are left alone so the text does not read
    "https://x (https://x)".
    """
    href = (m.group(1) or "").strip()
    label = _TAG_RE.sub("", m.group(2) or "").strip()
    if not href or href.startswith(("mailto:", "#", "javascript:")):
        return label
    if not label:
        return href
    if href.rstrip("/") in label:
        return label
    return f"{label} ({href})"


def html_to_text(raw: str) -> str:
    """Flatten LibAnswers' stored HTML into the prose the chunker wants.

    Block-level tags become newlines so that a list of loan periods does
    not collapse into one run-on sentence, which is what a naive tag
    strip produces and what the chunker would then have to cut blind.
    """
    if not raw:
        return ""
    s = _SCRIPT_RE.sub(" ", raw)
    s = _ANCHOR_RE.sub(_anchor_to_text, s)
    s = _BLOCK_RE.sub("\n", s)
    s = _TAG_RE.sub(" ", s)
    s = _html.unescape(s)
    s = s.replace("\xa0", " ")
    # collapse runs of spaces but keep paragraph breaks
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r" *\n[ \n]*", "\n", s)
    return s.strip()


# --- API --------------------------------------------------------------------


def _env(name: str) -> str:
    return (os.getenv(name) or "").strip()


def get_token(post: Optional[Callable[..., Any]] = None) -> str:
    """Client-credentials token for the LibAnswers API."""
    import httpx

    oauth_url = _env("LIBANS_OAUTH_URL")
    if not oauth_url:
        raise LibAnswersError("LIBANS_OAUTH_URL is not set")
    post = post or httpx.post
    r = post(oauth_url, data={
        "client_id": _env("LIBANS_CLIENT_ID"),
        "client_secret": _env("LIBANS_CLIENT_SECRET"),
        "grant_type": _env("LIBANS_GRANT_TYPE") or "client_credentials",
    }, timeout=20)
    if r.status_code != 200:
        raise LibAnswersError(f"token request returned HTTP {r.status_code}")
    tok = (r.json() or {}).get("access_token")
    if not tok:
        raise LibAnswersError("token response carried no access_token")
    return str(tok)


def api_base() -> str:
    return _env("LIBANS_OAUTH_URL").replace("/oauth/token", "").rstrip("/")


def fetch_faqs(get: Optional[Callable[..., Any]] = None,
               token: Optional[str] = None) -> list[dict]:
    """Every published FAQ, de-duplicated by faqid."""
    import httpx

    get = get or httpx.get
    token = token or get_token()
    base = api_base()
    headers = {"Authorization": f"Bearer {token}"}
    seen: dict[Any, dict] = {}
    for page in range(1, _MAX_PAGES + 1):
        r = get(f"{base}/faqs", headers=headers,
                params={"limit": _PAGE_LIMIT, "page": page}, timeout=30)
        if r.status_code != 200:
            raise LibAnswersError(f"/faqs page {page} returned HTTP {r.status_code}")
        rows = (r.json() or {}).get("faqs") or []
        fresh = [f for f in rows if f.get("faqid") not in seen]
        for f in rows:
            seen[f.get("faqid")] = f
        if not rows or not fresh:
            break
    logger.info("libanswers: %d FAQs", len(seen))
    return list(seen.values())


# --- FAQ -> corpus document -------------------------------------------------


def public_url(faq: dict) -> str:
    """The citable URL. `url` is a dict of {public, admin}; the admin one
    is a staff-only edit screen and must never reach the index."""
    u = faq.get("url")
    if isinstance(u, dict):
        pub = (u.get("public") or "").strip()
        if pub:
            return pub
    return f"https://{FAQ_HOST}/faq/{faq.get('faqid')}"


def topic_for(faq: dict) -> str:
    for t in (faq.get("topics") or []):
        name = (t.get("name") if isinstance(t, dict) else str(t)) or ""
        mapped = _TOPIC_MAP.get(name.strip().lower())
        if mapped:
            return mapped
    return "service"


def to_document(faq: dict) -> Optional[extract.ExtractedDoc]:
    """One FAQ -> one ExtractedDoc, or None if there is nothing to index."""
    question = html_to_text(faq.get("question") or "")
    answer = html_to_text(faq.get("answer") or faq.get("details") or "")
    if not question or not answer:
        return None

    # The question leads the body, not just the title: students phrase
    # their query the way the FAQ phrases the question, so it is the
    # strongest thing in the chunk for the embedding to match on.
    body = f"{question}\n\n{answer}"
    return extract.ExtractedDoc(
        url=public_url(faq),
        title=question,
        body_text=body,
        breadcrumbs=["Ask Us", "FAQ"],
        word_count=len(body.split()),
        schema_org_json=None,
        last_modified=(faq.get("updated") or None),
        rejection_reason=None,
        # A FAQ is authored as one unit, so the boilerplate floor that
        # protects the crawl does not apply -- it was silently dropping
        # ten of these, printing costs and library hours among them.
        # Empty answers are already refused above, which is the only
        # emptiness check this source needs.
        min_chunk_tokens=0,
    )


def to_documents(faqs: Iterable[dict]) -> list[extract.ExtractedDoc]:
    docs = []
    for f in faqs:
        d = to_document(f)
        if d is None:
            logger.info("libanswers: skipping faq %s (no question or answer)",
                        f.get("faqid"))
            continue
        docs.append(d)
    return docs


def to_classified(
    faqs: Iterable[dict],
) -> list[tuple[extract.ExtractedDoc, classify.DocMetadata]]:
    """FAQs -> the (document, metadata) pairs the orchestrator consumes.

    classify() is skipped rather than called: it infers topic from the
    URL path, and `/faq/<id>` matches no prefix, so every FAQ would land
    on its "about" fallback. LibAnswers labels its own answers, and
    those labels are better than a guess from a numeric URL.
    """
    out = []
    for f in faqs:
        doc = to_document(f)
        if doc is None:
            logger.info("libanswers: skipping faq %s (no question or answer)",
                        f.get("faqid"))
            continue
        out.append((doc, classify.DocMetadata(
            topic=topic_for(f),
            campus="oxford",
            library=None,
            audience=["student"],
            featured_service=None,
        )))
    return out


def load() -> list[tuple[extract.ExtractedDoc, classify.DocMetadata]]:
    """The Pipeline.extra_docs_fn entry point: fetch and convert."""
    return to_classified(fetch_faqs())


def discovered(docs: Iterable[extract.ExtractedDoc]) -> list[discover.DiscoveredUrl]:
    """DiscoveredUrl rows so these land in the citation allowlist.

    Campus is oxford: the FAQ is written for the whole system and is not
    a regional page, and oxford is what classify() infers for the host
    anyway.
    """
    return [discover.DiscoveredUrl(url=d.url, campus="oxford", source="seed")
            for d in docs]


__all__ = [
    "FAQ_HOST",
    "LibAnswersError",
    "api_base",
    "discovered",
    "fetch_faqs",
    "get_token",
    "html_to_text",
    "load",
    "public_url",
    "to_classified",
    "to_document",
    "to_documents",
    "topic_for",
]
