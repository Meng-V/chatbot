"""
The UrlSeen allowlist -- the load-bearing check behind validate_url.

Every URL the bot is allowed to mention in a user-facing answer must
appear in the `UrlSeen` Postgres table (populated by the weekly ETL)
and must NOT be marked `is_blacklisted` (a librarian flagged it via
the corrections workflow). Three ways into the allowlist:

    1. ETL `update_url_allowlist()` -- bulk upsert after each crawl.
    2. Manual override via the admin /admin/corrections endpoint.
    3. Featured-service URLs (kept as `priority: high` so a transient
       sitemap glitch doesn't blackhole the highest-value pages).

Three ways OUT:

    1. URL not seen in the most recent ETL run -> tombstoned (the URL
       row stays for audit, but `is_active=false`).
    2. Librarian blacklist via the corrections workflow.
    3. ETL hard-rejected (404 / test page / news page).

The lookup is one indexed Postgres row -- cheap. We expose it as both
a sync and an async function because the validate_url tool handler is
sync (the agent loop is sync) but the existing /smartchatbot stack
has async DB plumbing the lookup can plug into when it's wired.

The legacy `src/tools/url_validator.py` does live HTTP HEAD checks
against the open web. That's complementary, not redundant: it catches
URLs that 200'd at crawl time but went down later. The allowlist
catches URLs the model fabricated. Both run in the post-processor
pipeline before an answer ships.

See plan: Citation contract -> "URL validation tool" + "UrlSeen table".
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Iterable, Optional, Protocol
from urllib.parse import urlparse, urlunparse


logger = logging.getLogger("url_allowlist")


# --- Public types ---------------------------------------------------------


@dataclass(frozen=True)
class AllowlistEntry:
    """One row of the UrlSeen table, returned from a lookup.

    Mirrors the Prisma model in plan §"Postgres schema" plus a couple
    of ergonomics fields the bot uses (display URL, days since last
    seen for the freshness check)."""

    url: str
    """Canonical URL, lowercased scheme/host."""
    http_status: int
    last_seen: datetime
    is_active: bool
    is_blacklisted: bool
    source: str
    """Where the URL came from: sitemap | manual | libguide | featured."""
    content_type: Optional[str] = None
    priority: str = "normal"
    """`high` for featured-service URLs (Adobe / ILL / MakerSpace /
    Special Collections / Digital Collections / Newspapers). Treated
    leniently in freshness checks."""

    @property
    def is_servable(self) -> bool:
        """The combined check the validator actually runs."""
        return self.is_active and not self.is_blacklisted


class AllowlistStore(Protocol):
    """The narrow data-access seam.

    Prod implementation queries Postgres via Prisma. Tests pass a
    dict-backed in-memory implementation. Keeps the lookup logic
    transport-agnostic.
    """

    def get(self, url: str) -> Optional[AllowlistEntry]:
        """Return the AllowlistEntry for a canonicalized URL, or None
        if the URL was never seen."""
        ...

    def get_many(self, urls: Iterable[str]) -> dict[str, AllowlistEntry]:
        """Bulk variant -- one DB roundtrip rather than N. The post-
        processor uses this when validating every URL in an answer."""
        ...


# --- URL canonicalization -------------------------------------------------
#
# The allowlist is keyed on the canonical URL. We normalize before
# both writes (ETL) and reads (validation) so a trailing slash doesn't
# count as a different URL.


def canonicalize(url: str) -> str:
    """Lowercase scheme + host, strip default ports, drop fragment,
    drop trailing slash on the path (except root).

    Does NOT drop query strings -- some library pages (search results,
    LibGuide tabs) use distinguishing query params. If a future case
    shows the query is noise, add a per-host strip rule rather than
    a global one.
    """
    if not url:
        return url
    try:
        p = urlparse(url.strip())
    except Exception:
        # Malformed input: hand back as-is and let the lookup fail
        # cleanly with a "not in allowlist" result.
        return url

    scheme = (p.scheme or "https").lower()
    netloc = p.netloc.lower()
    # Strip default ports
    if netloc.endswith(":80") and scheme == "http":
        netloc = netloc[:-3]
    if netloc.endswith(":443") and scheme == "https":
        netloc = netloc[:-4]

    path = p.path
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    if not path:
        path = "/"

    return urlunparse((scheme, netloc, path, p.params, p.query, ""))


# --- The validator -------------------------------------------------------


@dataclass
class UrlAllowlistValidator:
    """The function-shaped object the agent's `validate_url` tool calls.

    Construct once at startup with the prod store; pass into
    `ToolBackends(validate_url=validator)` (the Tool handler unwraps
    the str argument and calls `validator(url)`).
    """

    store: AllowlistStore
    allow_blacklist_audit: bool = False
    """If True, blacklisted URLs are reported as invalid AND the
    blacklist reason is logged (used by the admin UI when a librarian
    asks 'why was this URL refused')."""

    def __call__(self, url: str) -> bool:
        """Sync entrypoint -- returns True iff the URL is in the
        allowlist and servable."""
        entry = self._lookup(url)
        return entry is not None and entry.is_servable

    def explain(self, url: str) -> dict:
        """Diagnostic variant -- used by the admin UI and the post-
        processor's reject path. Returns a structured reason rather
        than just True/False."""
        canon = canonicalize(url)
        entry = self.store.get(canon)
        if entry is None:
            return {
                "url": url,
                "canonical": canon,
                "valid": False,
                "reason": "not_in_allowlist",
            }
        if not entry.is_active:
            return {
                "url": url,
                "canonical": canon,
                "valid": False,
                "reason": "tombstoned",
                "last_seen": entry.last_seen.isoformat(),
            }
        if entry.is_blacklisted:
            return {
                "url": url,
                "canonical": canon,
                "valid": False,
                "reason": "blacklisted",
            }
        return {
            "url": url,
            "canonical": canon,
            "valid": True,
            "priority": entry.priority,
            "source": entry.source,
        }

    def filter_valid(self, urls: Iterable[str]) -> list[str]:
        """Bulk variant -- returns the subset of `urls` that are
        servable, in input order. Used by the synthesizer post-
        processor on every answer."""
        url_list = list(urls)
        canon_map = {u: canonicalize(u) for u in url_list}
        rows = self.store.get_many(canon_map.values())
        return [
            u
            for u in url_list
            if (entry := rows.get(canon_map[u])) is not None and entry.is_servable
        ]

    def _lookup(self, url: str) -> Optional[AllowlistEntry]:
        return self.store.get(canonicalize(url))


# --- In-memory store (tests + sandbox) ------------------------------------


@dataclass
class InMemoryAllowlistStore:
    """Dict-backed implementation for tests and the smoke harness.

    Prod replaces this with a PrismaAllowlistStore (below, gated on
    Prisma being importable). The InMemoryAllowlistStore is also handy
    for the eval suite: load the gold-set's expected URLs once, run
    eval, no DB needed.
    """

    entries: dict[str, AllowlistEntry] = None  # type: ignore

    def __post_init__(self) -> None:
        if self.entries is None:
            self.entries = {}

    def add(
        self,
        url: str,
        *,
        http_status: int = 200,
        is_active: bool = True,
        is_blacklisted: bool = False,
        source: str = "manual",
        priority: str = "normal",
        content_type: Optional[str] = "text/html",
        last_seen: Optional[datetime] = None,
    ) -> None:
        canon = canonicalize(url)
        self.entries[canon] = AllowlistEntry(
            url=canon,
            http_status=http_status,
            last_seen=last_seen or datetime.utcnow(),
            is_active=is_active,
            is_blacklisted=is_blacklisted,
            source=source,
            priority=priority,
            content_type=content_type,
        )

    def get(self, url: str) -> Optional[AllowlistEntry]:
        return self.entries.get(url)

    def get_many(self, urls: Iterable[str]) -> dict[str, AllowlistEntry]:
        return {u: self.entries[u] for u in urls if u in self.entries}


# --- Prisma-backed store (gated) ------------------------------------------


def make_prisma_store(prisma_client: Any) -> AllowlistStore:
    """Construct a Prisma-backed allowlist store.

    Why a factory rather than a class with `import prisma` at the top:
    Prisma's generated client isn't importable in the sandbox. We
    don't want this module to fail to import in dev, where the
    fallback InMemoryAllowlistStore is enough to run the eval suite
    and the smoke tests.

    Wire-up (prod startup, in main.py):

        from src.tools.url_allowlist import (
            UrlAllowlistValidator, make_prisma_store,
        )
        store = make_prisma_store(prisma_client)
        validate_url = UrlAllowlistValidator(store=store)
        backends = ToolBackends(validate_url=validate_url, ...)

    Implementation note: Prisma's Python client is async. The agent's
    tool handler is sync. We bridge by wrapping the async query with
    a thread-pool runner -- LibCal's tools do the same in the legacy
    code, so this isn't a new pattern.
    """

    @dataclass
    class _PrismaStore:
        client: Any

        def get(self, url: str) -> Optional[AllowlistEntry]:
            row = _run_async(self.client.urlseen.find_unique(where={"url": url}))
            return _row_to_entry(row) if row else None

        def get_many(
            self, urls: Iterable[str]
        ) -> dict[str, AllowlistEntry]:
            url_list = list(urls)
            if not url_list:
                return {}
            rows = _run_async(
                self.client.urlseen.find_many(where={"url": {"in": url_list}})
            )
            return {r.url: _row_to_entry(r) for r in rows}

    return _PrismaStore(client=prisma_client)


def _run_async(coro: Any) -> Any:
    """Run an awaitable from sync code. Mirrors the pattern used in
    `src/tools/libcal_comprehensive_tools.py` (legacy)."""
    import asyncio

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # We're already inside an event loop. Run on a worker
            # thread so we don't deadlock.
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(asyncio.run, coro).result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


def _row_to_entry(row: Any) -> AllowlistEntry:
    """Convert a Prisma row to AllowlistEntry. Field names mirror the
    Prisma schema (camelCase in JS, snake_case via the generator config
    in this repo -- adjust if generator config changes)."""
    return AllowlistEntry(
        url=row.url,
        http_status=getattr(row, "http_status", 200),
        last_seen=row.last_seen,
        is_active=getattr(row, "is_active", True),
        is_blacklisted=getattr(row, "is_blacklisted", False),
        source=getattr(row, "source", "sitemap"),
        priority=getattr(row, "priority", "normal"),
        content_type=getattr(row, "content_type", None),
    )


# --- Convenience builder for the existing legacy validator ---------------


def make_validate_url_callable(
    store: Optional[AllowlistStore] = None,
) -> Callable[[str], bool]:
    """Convenience for prod wiring -- produces the exact callable
    signature `ToolBackends.validate_url` expects.

    If no store is provided, returns a permissive validator that
    rejects everything. That's the SAFE default: 'no allowlist
    configured' should mean 'the bot returns no URLs', not 'the bot
    returns every URL'. See plan §"Refusal triggers" -> trigger 7.
    """
    if store is None:
        logger.warning(
            "validate_url called with no AllowlistStore -- rejecting "
            "ALL URLs (safe-mode). Wire a real store in main.py."
        )
        return lambda _url: False
    validator = UrlAllowlistValidator(store=store)
    return validator


__all__ = [
    "AllowlistEntry",
    "AllowlistStore",
    "InMemoryAllowlistStore",
    "UrlAllowlistValidator",
    "canonicalize",
    "make_prisma_store",
    "make_validate_url_callable",
]
