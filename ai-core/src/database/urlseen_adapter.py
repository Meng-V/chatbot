"""
PrismaUrlSeenStore: Prisma-backed implementation of the ETL's
`UrlSeenStore` Protocol (scripts/etl/upsert.py).

The Protocol surface is one method:

    upsert_many(rows, *, featured_urls) -> int

Returns the count of NEW (previously-unseen) URL rows so the diff
report can show "5 new URLs added to allowlist" rather than
"1273 URLs upserted" (the latter is misleading -- most are the same
URLs every weekly refresh).

Invariants per playbook §6:

- Updates `httpStatus`, `lastSeen`, `contentType`, `source`, and
  conditionally `priority='high'` for featured URLs.
- NEVER touches `isBlacklisted` or `isActive` -- those are librarian-
  controlled. `isActive` flips elsewhere (the legacy tool keeps it
  as part of the per-URL freshness audit).
- Idempotent on `url` PK.

Async bridge:

Prisma's Python client is async-only. The ETL is sync. We bridge via
the same `_run_async` thread-pool pattern that the existing
`src/tools/url_allowlist.py::make_prisma_store` uses, so this isn't
a new shape.

Construct via `PrismaUrlSeenStore()` -- the adapter resolves the
Prisma client lazily from `src.database.prisma_client.get_prisma_client`.
Tests can inject a stub via the `client` constructor arg.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)


def _run_async(coro: Any) -> Any:
    """Run an awaitable from sync code without deadlocking inside an
    existing event loop. Mirrors src/tools/url_allowlist.py's helper."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(asyncio.run, coro).result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


@dataclass
class PrismaUrlSeenStore:
    """Implements `UrlSeenStore` against a real Prisma client.

    Construct with `client=None` to auto-resolve the singleton via
    `src.database.prisma_client.get_prisma_client()`. The adapter
    connects on first use and leaves the connection open for the
    ETL run's duration (~1 min); the Prisma singleton's
    `disconnect_database()` is responsible for tear-down at process
    exit.
    """

    client: Optional[Any] = None

    def __post_init__(self) -> None:
        if self.client is None:
            from src.database.prisma_client import get_prisma_client
            self.client = get_prisma_client()

    def upsert_many(
        self,
        rows: list[dict],
        *,
        featured_urls: set[str],
    ) -> int:
        """Upsert each row by `url` PK. Returns count of NEW URLs.

        Each row dict has the keys the ETL produces (see
        scripts/etl/upsert.py::make_allowlist_step):

            url           str
            http_status   int
            source        str   ("sitemap" | "manual" | "libguide")
            content_type  Optional[str]
            last_seen     datetime

        Featured URLs get `priority="high"`; everything else
        unchanged from its current value (or `"normal"` on insert).
        We never touch `isBlacklisted` or `isActive`.
        """
        if not rows:
            return 0
        return _run_async(self._upsert_many_async(rows, featured_urls))

    async def _upsert_many_async(
        self,
        rows: list[dict],
        featured_urls: set[str],
    ) -> int:
        """Async core. Connects if not connected, upserts row-by-row.

        Per-row upsert is slower than a batch insert, but Prisma's
        upsert primitive doesn't support batch with where-clauses.
        For ~400 URLs/run this is fine (a few seconds); if the corpus
        grows past ~5K we should switch to raw SQL `INSERT ... ON
        CONFLICT DO UPDATE`.
        """
        await self._ensure_connected()
        new_count = 0
        for row in rows:
            url = row["url"]
            priority_set = (
                {"priority": "high"} if url in featured_urls else {}
            )
            update_data = {
                "httpStatus": row["http_status"],
                "lastSeen": _ensure_datetime(row["last_seen"]),
                "contentType": row.get("content_type"),
                "source": row.get("source", "sitemap"),
                **priority_set,
            }
            create_data = {
                "url": url,
                **update_data,
                # priority defaults to "normal" in the schema; only
                # set "high" on insert if this is a featured URL.
                "priority": "high" if url in featured_urls else "normal",
            }
            try:
                existing = await self.client.urlseen.find_unique(
                    where={"url": url}
                )
                if existing is None:
                    await self.client.urlseen.create(data=create_data)
                    new_count += 1
                else:
                    await self.client.urlseen.update(
                        where={"url": url},
                        data=update_data,
                    )
            except Exception as e:  # noqa: BLE001
                logger.warning(
                    "urlseen upsert failed for url",
                    extra={"url": url, "error": str(e)},
                )
        return new_count

    async def _ensure_connected(self) -> None:
        """Lazy-connect on first call. The Prisma singleton tolerates
        repeated `connect()` calls but does I/O on each, so we guard
        with `is_connected()`."""
        if not self.client.is_connected():
            await self.client.connect()


def _ensure_datetime(value: Any) -> dt.datetime:
    """Coerce a value into a timezone-naive UTC datetime.

    The ETL passes `dt.datetime.utcnow()` -- naive UTC. If a caller
    passes an aware datetime, strip the tzinfo so Prisma sees a
    consistent type. (Mismatched aware/naive datetimes are a common
    Prisma client gotcha.)
    """
    if isinstance(value, dt.datetime):
        if value.tzinfo is not None:
            return value.astimezone(dt.timezone.utc).replace(tzinfo=None)
        return value
    raise TypeError(
        f"last_seen must be datetime; got {type(value).__name__}"
    )


__all__ = ["PrismaUrlSeenStore"]
