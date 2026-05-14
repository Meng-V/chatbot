"""
Unit tests for PrismaUrlSeenStore.

Run: `python -m src.database.test_urlseen_adapter` from ai-core/.

The adapter wraps Prisma's async client. Tests inject a stub client
that mimics the async surface (find_unique / create / update) without
needing a database or the prisma client library.

Coverage:

  1. upsert_many returns 0 for empty input
  2. New URLs increment new_count
  3. Existing URLs DON'T increment new_count
  4. Featured URLs get priority='high' set on update
  5. Featured URLs get priority='high' set on insert
  6. Non-featured URLs default to priority='normal' on insert
  7. Non-featured URLs DON'T get priority touched on update
  8. isBlacklisted and isActive are NEVER written
  9. Timezone-aware datetimes are coerced to naive UTC
 10. _ensure_connected lazily connects only when not connected
 11. Per-row exceptions are logged but don't stop the batch
"""

from __future__ import annotations

import asyncio
import datetime as dt
import sys
from pathlib import Path
from typing import Any, Optional

# Allow `python -m src.database.test_urlseen_adapter` from ai-core/.
_HERE = Path(__file__).resolve().parent
_AI_CORE = _HERE.parent.parent
sys.path.insert(0, str(_AI_CORE))

from src.database.urlseen_adapter import (  # noqa: E402
    PrismaUrlSeenStore,
    _ensure_datetime,
)


# --- Async stub Prisma client ------------------------------------------


class _StubUrlSeen:
    """Mimics `client.urlseen.find_unique / create / update`."""
    def __init__(self):
        self.rows: dict[str, dict] = {}
        self.create_calls: list[dict] = []
        self.update_calls: list[dict] = []
        self.raise_on_url: Optional[str] = None

    async def find_unique(self, *, where):
        if self.raise_on_url == where["url"]:
            raise RuntimeError("simulated DB failure")
        row = self.rows.get(where["url"])
        if row is None:
            return None
        # Return a small object with attribute access matching Prisma.
        class _R:
            pass
        r = _R()
        for k, v in row.items():
            setattr(r, k, v)
        r.url = row["url"]
        return r

    async def create(self, *, data):
        self.create_calls.append(dict(data))
        self.rows[data["url"]] = dict(data)

    async def update(self, *, where, data):
        self.update_calls.append({"where": dict(where), "data": dict(data)})
        existing = self.rows[where["url"]]
        existing.update(data)


class _StubPrismaClient:
    def __init__(self):
        self.urlseen = _StubUrlSeen()
        self._connected = False
        self.connect_calls = 0

    def is_connected(self) -> bool:
        return self._connected

    async def connect(self):
        self.connect_calls += 1
        self._connected = True


def _row(url: str, *, status: int = 200, ct: str = "text/html",
         source: str = "sitemap",
         last_seen: Optional[dt.datetime] = None) -> dict:
    return {
        "url": url,
        "http_status": status,
        "content_type": ct,
        "source": source,
        "last_seen": last_seen or dt.datetime(2026, 5, 14, 12, 0, 0),
    }


# --- Tests --------------------------------------------------------------


def test_upsert_many_empty_input_returns_zero() -> None:
    store = PrismaUrlSeenStore(client=_StubPrismaClient())
    assert store.upsert_many([], featured_urls=set()) == 0


def test_new_urls_increment_new_count() -> None:
    client = _StubPrismaClient()
    store = PrismaUrlSeenStore(client=client)
    rows = [_row("https://lib.example/a"), _row("https://lib.example/b")]
    n = store.upsert_many(rows, featured_urls=set())
    assert n == 2
    assert len(client.urlseen.create_calls) == 2
    assert len(client.urlseen.update_calls) == 0


def test_existing_urls_update_not_create_and_dont_count_as_new() -> None:
    client = _StubPrismaClient()
    # Pre-seed an existing row.
    client.urlseen.rows["https://lib.example/a"] = {
        "url": "https://lib.example/a", "httpStatus": 200, "priority": "normal",
    }
    store = PrismaUrlSeenStore(client=client)
    rows = [_row("https://lib.example/a")]
    n = store.upsert_many(rows, featured_urls=set())
    assert n == 0
    assert len(client.urlseen.create_calls) == 0
    assert len(client.urlseen.update_calls) == 1


def test_featured_url_gets_priority_high_on_insert() -> None:
    client = _StubPrismaClient()
    store = PrismaUrlSeenStore(client=client)
    url = "https://lib.example/use/spaces/makerspace/"
    store.upsert_many(
        [_row(url)],
        featured_urls={url},
    )
    assert client.urlseen.create_calls[0]["priority"] == "high"


def test_non_featured_url_gets_priority_normal_on_insert() -> None:
    client = _StubPrismaClient()
    store = PrismaUrlSeenStore(client=client)
    store.upsert_many(
        [_row("https://lib.example/other/")],
        featured_urls=set(),
    )
    assert client.urlseen.create_calls[0]["priority"] == "normal"


def test_featured_url_gets_priority_high_on_update() -> None:
    """Existing URL becoming featured (e.g., librarian added it to the
    featured-service config) should have its priority bumped."""
    client = _StubPrismaClient()
    url = "https://lib.example/use/spaces/makerspace/"
    client.urlseen.rows[url] = {"url": url, "priority": "normal"}
    store = PrismaUrlSeenStore(client=client)
    store.upsert_many([_row(url)], featured_urls={url})
    update = client.urlseen.update_calls[0]
    assert update["data"].get("priority") == "high"


def test_non_featured_url_priority_untouched_on_update() -> None:
    """Conversely, non-featured updates don't pin priority -- a
    librarian-set priority via the admin path shouldn't get clobbered
    by the ETL."""
    client = _StubPrismaClient()
    url = "https://lib.example/regular/"
    client.urlseen.rows[url] = {"url": url, "priority": "normal"}
    store = PrismaUrlSeenStore(client=client)
    store.upsert_many([_row(url)], featured_urls=set())
    update = client.urlseen.update_calls[0]
    assert "priority" not in update["data"]


def test_isBlacklisted_and_isActive_never_written() -> None:
    """Load-bearing invariant per playbook §6: the ETL writes
    technical metadata. Operator-controlled flags (blacklist, active)
    are touched only via the admin / librarian flow."""
    client = _StubPrismaClient()
    store = PrismaUrlSeenStore(client=client)
    store.upsert_many(
        [_row("https://lib.example/a")],
        featured_urls=set(),
    )
    create = client.urlseen.create_calls[0]
    assert "isBlacklisted" not in create
    assert "isActive" not in create
    # And on update.
    client.urlseen.rows["https://lib.example/a"] = {"url": "https://lib.example/a"}
    store.upsert_many([_row("https://lib.example/a")], featured_urls=set())
    update = client.urlseen.update_calls[0]
    assert "isBlacklisted" not in update["data"]
    assert "isActive" not in update["data"]


def test_timezone_aware_datetime_coerced_to_naive_utc() -> None:
    aware = dt.datetime(2026, 5, 14, 12, 0, 0, tzinfo=dt.timezone(dt.timedelta(hours=-5)))
    naive = _ensure_datetime(aware)
    assert naive.tzinfo is None
    # Should be converted to UTC (which is 5 hours ahead).
    assert naive == dt.datetime(2026, 5, 14, 17, 0, 0)


def test_naive_datetime_passed_through_unchanged() -> None:
    naive = dt.datetime(2026, 5, 14, 12, 0, 0)
    assert _ensure_datetime(naive) is naive


def test_ensure_datetime_rejects_non_datetime() -> None:
    try:
        _ensure_datetime("2026-05-14")  # type: ignore[arg-type]
    except TypeError:
        return
    raise AssertionError("expected TypeError on string input")


def test_lazy_connect_only_when_not_connected() -> None:
    """Don't reconnect on every upsert -- Prisma's connect() does I/O."""
    client = _StubPrismaClient()
    store = PrismaUrlSeenStore(client=client)
    store.upsert_many([_row("u1")], featured_urls=set())
    store.upsert_many([_row("u2")], featured_urls=set())
    assert client.connect_calls == 1


def test_per_row_exception_logged_but_doesnt_stop_batch() -> None:
    """A single failing row shouldn't poison the whole batch -- the
    next refresh would recover the missing rows, but the rest of the
    batch should still apply this run."""
    client = _StubPrismaClient()
    client.urlseen.raise_on_url = "https://lib.example/bad"
    store = PrismaUrlSeenStore(client=client)
    n = store.upsert_many(
        [
            _row("https://lib.example/good-a"),
            _row("https://lib.example/bad"),
            _row("https://lib.example/good-b"),
        ],
        featured_urls=set(),
    )
    # Two succeeded -> two new.
    assert n == 2
    assert len(client.urlseen.create_calls) == 2


# --- Runner -------------------------------------------------------------


def main() -> int:
    tests = [
        test_upsert_many_empty_input_returns_zero,
        test_new_urls_increment_new_count,
        test_existing_urls_update_not_create_and_dont_count_as_new,
        test_featured_url_gets_priority_high_on_insert,
        test_non_featured_url_gets_priority_normal_on_insert,
        test_featured_url_gets_priority_high_on_update,
        test_non_featured_url_priority_untouched_on_update,
        test_isBlacklisted_and_isActive_never_written,
        test_timezone_aware_datetime_coerced_to_naive_utc,
        test_naive_datetime_passed_through_unchanged,
        test_ensure_datetime_rejects_non_datetime,
        test_lazy_connect_only_when_not_connected,
        test_per_row_exception_logged_but_doesnt_stop_batch,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
        except Exception as e:
            failed += 1
            print(f"ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
