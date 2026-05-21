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
_module_load_attempted: bool = False


def _reset_module_cache_for_tests() -> None:
    """Test hook only. Clears the module-level cache so unit tests don't
    leak state between cases. Not exported in __all__; tests reach in
    by name."""
    global _module_cached, _module_load_attempted
    _module_cached = None
    _module_load_attempted = False


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
        if self.client is None:
            from src.database.prisma_client import get_prisma_client
            self.client = get_prisma_client()

    def load_active(self) -> list[ManualCorrection]:
        """Sync entry point matching `OrchestratorDeps.load_corrections`.

        Cached at module level: first successful call in the process
        queries Postgres, subsequent calls (including from different
        store instances) return the cached list. If the first call
        fails (Postgres down), we cache empty so the rest of the
        process doesn't keep retrying.
        """
        global _module_cached, _module_load_attempted
        if _module_load_attempted:
            return _module_cached or []
        _module_load_attempted = True
        try:
            _module_cached = _run_async(self._aload_active())
        except Exception:
            _module_cached = []
            raise  # caller decides whether to swallow
        return _module_cached

    def refresh(self) -> list[ManualCorrection]:
        """Force a re-read from Postgres. Use after a known correction
        insert if the process must pick it up without restart."""
        global _module_cached, _module_load_attempted
        _module_load_attempted = False
        _module_cached = None
        return self.load_active()

    async def _aload_active(self) -> list[ManualCorrection]:
        if not self.client.is_connected():
            await self.client.connect()
        now = dt.datetime.now(dt.timezone.utc)
        rows = await self.client.manualcorrection.find_many(
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
