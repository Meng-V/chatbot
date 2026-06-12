"""
Prisma-backed loader for ManualCorrection rows.

The orchestrator's OrchestratorDeps has a `load_corrections` callable
typed `list[ManualCorrection]`. Before this adapter, the production
(`v2_serving.py`) and eval (`run_eval.py`) paths both stubbed it as
`lambda: []` -- meaning the apply_corrections() layer in the
synthesizer had nothing to apply, even after librarians inserted
ManualCorrection rows. The schema and write-side (admin router) were
shipped without the read-side.

This module closes that gap. `PrismaCorrectionsStore.load_active()`
queries the Postgres ManualCorrection table filtered by
`active=true AND expiresAt > now()`, maps rows into the synthesis
dataclass, and returns the list ready for `apply_corrections()`.

Architecture mirrors `src/database/urlseen_adapter.py`:

  * Lazy Prisma client resolution via `get_prisma_client()`.
  * Sync surface (returns plain list) so the orchestrator doesn't need
    to be async-aware. Async bridge through a thread-pool when called
    from inside an event loop (the eval and v2 serving both call this
    from sync code paths or thread-bridged code paths).
  * Construct with `client=None` to auto-resolve; tests inject a stub.

ID handling: the Prisma model uses `String @id @default(uuid())`, but
`synthesis.corrections.ManualCorrection` types `id: int` and the
orchestrator's TurnResponse.fired_corrections is `list[int]`. We map
UUIDs to stable positive ints via zlib.adler32. The mapping is
deterministic, so a given UUID always hashes to the same int across
runs. Operators can join `_uuid_to_int(row.id)` to debug, and the
adapter logs both forms at INFO on first load. Changing the
TurnResponse type to str is a larger refactor deferred to a future
PR; the int approach unblocks Pattern C today without rippling.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
import zlib
from dataclasses import dataclass
from typing import Any, Optional

from src.synthesis.corrections import ManualCorrection

logger = logging.getLogger(__name__)


def _uuid_to_int(uuid_str: str) -> int:
    """Deterministic UUID-string -> positive 32-bit int.

    `adler32` is fast, has a wide enough output (~4B values) that
    collisions across N corrections (N is small, low tens) are
    effectively zero, and is stable across Python versions (unlike
    `hash()`). Mask to 31 bits for a positive signed int that
    serializes cleanly to JSON.
    """
    return zlib.adler32(uuid_str.encode()) & 0x7FFFFFFF


def _run_async(coro: Any) -> Any:
    """Run an awaitable from sync code without deadlocking inside an
    existing event loop.

    Python 3.14 + Prisma's query engine: stale event loops from
    `get_event_loop().run_until_complete()` leave the spawned query-
    engine subprocess in a state where subsequent reuse fails with
    `EngineConnectionError` even though the first call worked. The
    safe path is to always create a FRESH loop per call via
    `asyncio.run()` -- which closes the loop on exit and lets the next
    call start clean. When called from inside a running loop (rare:
    only if the orchestrator is itself async-aware in some future
    refactor), fall back to a thread executor.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        # No running loop -> fresh loop via asyncio.run. Recommended.
        return asyncio.run(coro)
    # Running loop -> can't asyncio.run from inside it; thread-bridge.
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


# --- Module-level cache --------------------------------------------------
#
# Why module-level (not instance-level): `run_eval._build_real_deps` builds
# a FRESH OrchestratorDeps per turn (intentional -- the canned-agent stub
# is stateful), which means a fresh `PrismaCorrectionsStore` per turn. An
# instance-level cache there is useless. Module-level state means all
# PrismaCorrectionsStore instances in a process share one cached load.
#
# Why CACHE AT ALL: Prisma's query engine is a Rust subprocess coupled to
# the asyncio event loop. Per-turn `asyncio.run()` closes the loop, killing
# the engine; subsequent calls fail with "Event loop is closed". Caching
# the first successful load avoids re-spawning. Verified in the 2026-05-21
# eval logs (26 successful loads, 23 "Event loop is closed" failures
# alternating; with cache: 1 successful load, all subsequent calls return
# the cached list).
#
# Trade-off: a librarian adding a correction mid-process won't see it
# until process restart. That matches the deploy cadence (librarian
# inserts row → operator restarts service) and is documented in Op 2's
# "audit and accountability" section.

_module_cached: Optional[list[ManualCorrection]] = None
_module_cached_at: Optional[float] = None  # time.monotonic()

CACHE_TTL_SECONDS = 60.0
"""Re-read corrections from Postgres at most once a minute. Short enough
that a librarian's correction is live within a minute even cross-process;
in-process it's IMMEDIATE because the admin router busts this cache on
every successful write.

2026-06-11 redesign: the old semantics ("cache the FIRST result forever;
on first FAILURE cache empty forever") combined with the loop-affinity
bug fixed below meant one bad first call silenced corrections for the
entire process lifetime -- exactly what prod did after the 06-11 deploy
(WARNING 'bound to a different event loop' ... continuing without
overrides, on every turn)."""


def _invalidate_module_cache() -> None:
    """Bust the cache. The admin corrections router calls this after
    every successful write so 'takes effect on the next turn' is
    literally true in-process."""
    global _module_cached, _module_cached_at
    _module_cached = None
    _module_cached_at = None


def _reset_module_cache_for_tests() -> None:
    """Test hook only. Clears the module-level cache so unit tests don't
    leak state between cases. Not exported in __all__; tests reach in
    by name."""
    _invalidate_module_cache()


@dataclass
class PrismaCorrectionsStore:
    """Reads ManualCorrection rows from Postgres for apply_corrections().

    Usage:
        store = PrismaCorrectionsStore()
        deps = OrchestratorDeps(
            ...,
            load_corrections=store.load_active,
            ...,
        )

    Multi-instance behavior: instances are cheap; the actual DB load
    is shared across instances via module-level cache (see comment
    block above). Constructing a new store mid-process does NOT trigger
    a re-query -- call `refresh()` to force one.
    """

    client: Optional[Any] = None

    def __post_init__(self) -> None:
        # `client` stays None in production -> fresh-client-per-load
        # (see _aload_active). Tests inject a stub and we use it as-is.
        #
        # The old code resolved the process SINGLETON here. That
        # singleton's query engine binds its httpx session to the loop
        # that connected it (the app's MAIN loop at startup), but
        # load_active runs from run_turn's executor THREAD inside its
        # own asyncio.run() loop -> "Event ... is bound to a different
        # event loop" on real serving turns (prod error.log 2026-06-11).
        self._injected = self.client is not None

    def load_active(self) -> list[ManualCorrection]:
        """Sync entry point matching `OrchestratorDeps.load_corrections`.

        TTL-cached at module level (CACHE_TTL_SECONDS; the admin router
        additionally invalidates on every write, so an in-process
        correction is live on the next turn). On a refresh FAILURE with
        a previous good value, serves the stale value and warns -- a
        transient pg blip must not strip the override layer. A
        first-ever failure raises (callers' safe-degradation treats it
        as "no overrides this turn") and the NEXT call retries instead
        of poisoning the process.
        """
        global _module_cached, _module_cached_at
        import time
        now = time.monotonic()
        if (
            _module_cached is not None
            and _module_cached_at is not None
            and now - _module_cached_at < CACHE_TTL_SECONDS
        ):
            return _module_cached
        try:
            fresh = _run_async(self._aload_active())
        except Exception:
            if _module_cached is not None:
                logger.warning(
                    "ManualCorrection refresh failed; serving %d stale "
                    "cached rows", len(_module_cached),
                )
                return _module_cached
            raise  # caller decides whether to swallow
        _module_cached = fresh
        _module_cached_at = now
        return fresh

    def refresh(self) -> list[ManualCorrection]:
        """Force a re-read from Postgres. Use after a known correction
        insert if the process must pick it up without restart."""
        _invalidate_module_cache()
        return self.load_active()

    async def _aload_active(self) -> list[ManualCorrection]:
        if self._injected:
            client = self.client
            if hasattr(client, "is_connected") and not client.is_connected():
                await client.connect()
            return await self._aquery(client)
        # Fresh client per load, connected and disconnected INSIDE this
        # coroutine's own event loop -- immune to both failure modes the
        # singleton path had: cross-loop affinity, and "Event loop is
        # closed" when a loop-bound engine is reused after asyncio.run
        # tears its loop down.
        from prisma import Prisma
        client = Prisma()
        await client.connect()
        try:
            return await self._aquery(client)
        finally:
            await client.disconnect()

    async def _aquery(self, client: Any) -> list[ManualCorrection]:
        now = dt.datetime.now(dt.timezone.utc)
        rows = await client.manualcorrection.find_many(
            where={
                "active": True,
                "expiresAt": {"gt": now},
            }
        )
        out: list[ManualCorrection] = []
        for r in rows:
            out.append(
                ManualCorrection(
                    id=_uuid_to_int(r.id),
                    scope=r.scope,  # type: ignore[arg-type]
                    target=r.target,
                    action=r.action,  # type: ignore[arg-type]
                    replacement=r.replacement,
                    query_pattern=r.queryPattern,
                    reason=r.reason,
                    created_by=r.createdBy,
                )
            )
        if out:
            # Debug breadcrumb so operators can map int IDs back to UUIDs.
            logger.info(
                "loaded %d active ManualCorrection rows; uuid->int sample: %s",
                len(out),
                [(r.id, _uuid_to_int(r.id)) for r in rows[:3]],
            )
        return out


__all__ = ["PrismaCorrectionsStore", "_uuid_to_int"]
