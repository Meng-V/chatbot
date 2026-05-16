"""Real `ToolBackends` for the eval — the honest-baseline subset.

Context: `tools_v2.build_tool_registry(backends)` wires 10 tools, but
`ToolBackends` had never been constructed with REAL backends anywhere
(only docstring examples). So the eval could only ever register
`search_kb`; every other category was measured with the tool absent.
That's not a bot failure, it's a measurement gap.

This module wires EVERY read-only tool to its real backend:

  * validate_url     -> real Postgres `UrlSeen` (the 396-row allowlist
                        we verified on 3.14), reusing the production
                        `UrlAllowlistValidator` policy (canonicalize +
                        is_active + not is_blacklisted + parent-URL
                        fallback). Only the connection model is swapped
                        (connect-per-call, see `_db`).
  * lookup_librarian -> real Postgres `Librarian` / `LibrarianSubject`
                        (by name / campus / subject).
  * point_to_url     -> the team's OWN curated, verified URLs from
                        `src.config.capability_scope` (NOT a hand-typed
                        map -- fabricating URLs is the exact failure
                        this whole project fights). Unknown service ->
                        a no-URL result the agent narrates as a
                        handoff, never a guessed link.
  * get_hours        -> live LibCal via the LEGACY, production-proven
                        `LibCalWeekHoursTool` (LibCal OAuth + DB
                        building->location-id map already exist in
                        src/tools + the shared Postgres). It was a
                        mistake to call this "Gap 10" -- the
                        implementation was sitting in src/tools the
                        whole time; this is reuse, not multi-day work.
  * get_room_availability -> live LibCal via the legacy
                        `LibCalEnhancedAvailabilityTool`.

Only the WRITE/handoff tools (book_room, create_ticket,
handoff_human) and lookup_space stay unset -> tools_v2's
`_make_unwired_sentinel`. `_build_real_deps` drops those four from
the eval surface anyway, so they never reach the agent.

Two connection models, each matched to its constraint:

  * `_db` (connect-per-call, one fresh client inside one `asyncio.run`)
    for validate_url / lookup_librarian. Self-contained, cross-loop
    safe, verified on 3.14.5.
  * `_bridge` (one persistent background event loop on a daemon
    thread) for the LibCal tools. They reach the legacy code via the
    `get_prisma_client()` SINGLETON + a singleton `LocationService`
    with its own cache; that singleton binds to whatever loop first
    connected it, so every LibCal call MUST run on one stable loop.
    `_db`'s per-call fresh loop would bind-then-orphan the singleton.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable, Iterable, Optional

from src.config.capability_scope import ILL_URLS
from src.tools.url_allowlist import (
    AllowlistEntry,
    UrlAllowlistValidator,
    _row_to_entry,
)
from src.tools_v2.registry import ToolBackends
from src.agent.tool_registry import ToolError

logger = logging.getLogger(__name__)


# --- Prisma connect-per-call bridge --------------------------------------


def _db(coro_fn: Callable[[Any], Awaitable[Any]]) -> Any:
    """Run `coro_fn(client)` against a freshly connected Prisma client
    and disconnect, all inside one event loop. See module docstring for
    why connect-per-call rather than a shared pool."""

    async def _run() -> Any:
        from prisma import Prisma

        client = Prisma()
        await client.connect()
        try:
            return await coro_fn(client)
        finally:
            await client.disconnect()

    return asyncio.run(_run())


# --- Persistent loop for the legacy LibCal tools -------------------------


class _AsyncBridge:
    """One asyncio loop on a daemon thread, alive for the whole eval.

    The legacy LibCal tools reach Postgres through the
    `get_prisma_client()` singleton and a singleton `LocationService`
    (with an in-process cache). A prisma client binds to the loop that
    connected it; `_db`'s connect-per-call pattern would bind the
    SINGLETON to a loop that then closes, orphaning it on the next
    call. So every LibCal coroutine runs on this single stable loop --
    the singleton connects once (lazily, by LocationService itself) and
    stays valid for the eval's lifetime.

    Lazy + daemon: nothing starts until the first hours/availability
    question; the thread dies with the process (no shutdown hook to
    forget).
    """

    _loop: Optional[asyncio.AbstractEventLoop] = None
    _thread: Optional[Any] = None

    @classmethod
    def submit(cls, coro: Awaitable[Any], timeout: float = 30.0) -> Any:
        if cls._loop is None:
            import threading

            cls._loop = asyncio.new_event_loop()
            cls._thread = threading.Thread(
                target=cls._loop.run_forever,
                name="eval-libcal-loop",
                daemon=True,
            )
            cls._thread.start()
        fut = asyncio.run_coroutine_threadsafe(coro, cls._loop)
        return fut.result(timeout=timeout)


def _bridge(coro: Awaitable[Any], timeout: float = 30.0) -> Any:
    return _AsyncBridge.submit(coro, timeout=timeout)


# --- validate_url --------------------------------------------------------


class _ConnectPerCallUrlSeenStore:
    """`AllowlistStore` (Protocol: get / get_many) backed by Postgres
    `UrlSeen`, one short-lived connection per lookup. Reuses the
    production `_row_to_entry` so the entry shape / policy matches
    exactly; only the transport differs from `make_prisma_store`."""

    def get(self, url: str) -> Optional[AllowlistEntry]:
        async def _q(client: Any) -> Any:
            return await client.urlseen.find_unique(where={"url": url})

        try:
            row = _db(_q)
        except Exception as e:  # noqa: BLE001
            # A DB hiccup must not crash the turn. Treat as "unknown"
            # -> validator returns False -> bot omits the URL (the
            # safe direction per the plan's refusal-trigger 7).
            logger.warning("validate_url store.get failed for %s: %s", url, e)
            return None
        return _row_to_entry(row) if row else None

    def get_many(
        self, urls: Iterable[str]
    ) -> dict[str, AllowlistEntry]:
        url_list = list(urls)
        if not url_list:
            return {}

        async def _q(client: Any) -> Any:
            return await client.urlseen.find_many(
                where={"url": {"in": url_list}}
            )

        try:
            rows = _db(_q)
        except Exception as e:  # noqa: BLE001
            logger.warning("validate_url store.get_many failed: %s", e)
            return {}
        return {r.url: _row_to_entry(r) for r in rows}


def _make_validate_url() -> Callable[[str], bool]:
    return UrlAllowlistValidator(store=_ConnectPerCallUrlSeenStore())


# --- lookup_librarian ----------------------------------------------------

# Gold/scope campuses are lowercase canonical ids; the Librarian table
# stores display-cased values (schema default "Oxford").
_CAMPUS_DB = {
    "oxford": "Oxford",
    "hamilton": "Hamilton",
    "middletown": "Middletown",
}


def _librarian_dict(row: Any) -> dict:
    """Shape a Librarian row into the dict the LLM reads. Exact contact
    fields (email/phone) must survive verbatim -- the plan requires the
    bot to return the real email, not a paraphrase."""
    return {
        "name": getattr(row, "name", None),
        "email": getattr(row, "email", None),
        "title": getattr(row, "title", None),
        "department": getattr(row, "department", None),
        "phone": getattr(row, "phone", None),
        "campus": getattr(row, "campus", None),
        "profile_url": getattr(row, "profileUrl", None),
    }


def _make_lookup_librarian() -> Callable[[dict], list[dict]]:
    def lookup(filters: dict) -> list[dict]:
        name = (filters.get("name") or "").strip()
        subject = (filters.get("subject") or "").strip()
        campus_raw = (filters.get("campus") or "").strip().lower()
        campus = _CAMPUS_DB.get(campus_raw)

        async def _q(client: Any) -> list[dict]:
            # Subject takes priority: it's the highest-signal filter and
            # joins via LibrarianSubject -> Librarian.
            if subject:
                links = await client.librariansubject.find_many(
                    where={
                        "subject": {
                            "is": {
                                "name": {
                                    "contains": subject,
                                    "mode": "insensitive",
                                }
                            }
                        }
                    },
                    include={"librarian": True},
                )
                seen: dict[str, dict] = {}
                for link in links:
                    lib = getattr(link, "librarian", None)
                    if lib is None or not getattr(lib, "isActive", True):
                        continue
                    if campus and getattr(lib, "campus", None) != campus:
                        continue
                    seen[lib.email] = _librarian_dict(lib)
                return list(seen.values())

            where: dict = {"isActive": True}
            if name:
                where["name"] = {"contains": name, "mode": "insensitive"}
            if campus:
                where["campus"] = campus
            rows = await client.librarian.find_many(where=where)
            return [_librarian_dict(r) for r in rows]

        try:
            return _db(_q)
        except Exception as e:  # noqa: BLE001
            raise ToolError(
                f"lookup_librarian: directory query failed ({e}). "
                f"The bot should hand off rather than guess a name."
            ) from e

    return lookup


# --- point_to_url --------------------------------------------------------
#
# Two sources of truth, BOTH in src.config.capability_scope -- no URL
# here is invented:
#
#   * ILL  -> `ILL_URLS` is imported LIVE and resolved by campus, so
#     it cannot drift and a Hamilton user never gets the Oxford ILL
#     link (plan §"Action vs guidance": "Do not give the Oxford pickup
#     location to a Hamilton user").
#   * account / renewals / fines / course_reserves -> MIRRORED from the
#     URLs inside `LIMITATIONS[*].response`. Those live in prose
#     strings, so a regex-extract would be fragile; instead they are an
#     explicit map AND `test_real_backends` asserts every one is still
#     literally present in a capability_scope response string (the
#     drift guard).

_PRIMO_ACCOUNT = (
    "https://ohiolink-mu.primo.exlibrisgroup.com/discovery/account"
    "?vid=01OHIOLINK_MU:MU&section=overview&lang=en"
)

# Non-ILL services: service-id -> (url, one-line description). URLs
# mirrored from capability_scope.LIMITATIONS responses (drift-tested).
_POINT_TO_URL: dict[str, tuple[str, str]] = {
    "account": (
        _PRIMO_ACCOUNT,
        "Your library account (checkouts, holds, fines) in OhioLINK "
        "Primo. The bot has no access to patron accounts.",
    ),
    "renewals": (
        _PRIMO_ACCOUNT,
        "Renew books in your OhioLINK Primo account.",
    ),
    "renew_books": (
        _PRIMO_ACCOUNT,
        "Renew books in your OhioLINK Primo account.",
    ),
    "fines": (
        _PRIMO_ACCOUNT,
        "Pay fines via your OhioLINK Primo account or at a service "
        "desk.",
    ),
    "course_reserves": (
        "https://libguides.lib.miamioh.edu/reserves-textbooks/",
        "Course reserves & textbooks guide.",
    ),
}

# scope.campus (lowercase canonical) -> ILL_URLS key.
_CAMPUS_TO_ILL_KEY = {
    "oxford": "main",
    "hamilton": "hamilton",
    "middletown": "middletown",
}
_ILL_SERVICES = {"ill", "interlibrary_loan", "interlibrary loan"}


def _make_point_to_url() -> Callable[[str, dict], dict]:
    def point(service: str, scope: dict) -> dict:
        key = (service or "").strip().lower()

        if key in _ILL_SERVICES:
            campus = str((scope or {}).get("campus") or "oxford").lower()
            ill = ILL_URLS[_CAMPUS_TO_ILL_KEY.get(campus, "main")]
            return {
                "service": service,
                "url": ill["url"],
                "found": True,
                "description": (
                    f"Interlibrary Loan for {ill['name']}. Submit the "
                    f"request yourself; the bot does not place ILL "
                    f"requests."
                ),
            }

        hit = _POINT_TO_URL.get(key)
        if hit is None:
            # No verified URL -> DO NOT guess. Return a no-URL result
            # the synthesizer narrates as a librarian handoff.
            return {
                "service": service,
                "url": None,
                "found": False,
                "description": (
                    f"No verified self-service URL is configured for "
                    f"'{service}'. Refer the user to a librarian rather "
                    f"than guessing a link."
                ),
            }
        url, desc = hit
        return {
            "service": service,
            "url": url,
            "found": True,
            "description": desc,
        }

    return point


# --- get_hours / get_room_availability (live LibCal, legacy reuse) -------
#
# canonical library id (Weaviate/scope) -> the building NAME the legacy
# LocationService.get_location_id() resolves (it `contains`-matches
# Library/LibrarySpace.shortName|name in the shared Postgres -- the
# same names the production bot has used successfully for years, per
# the legacy tool descriptions). `sword` (closed regional depository)
# has no public LibCal hours and is handled before any LibCal call.

_CANON_TO_LIBCAL_NAME = {
    "king": "king",
    "wertz": "art",                 # Wertz Art & Architecture
    "rentschler": "rentschler",
    "gardner_harvey": "gardner-harvey",
    "special": "special collections",
}


def _make_get_hours() -> Callable[[str], dict]:
    from src.tools.libcal_comprehensive_tools import LibCalWeekHoursTool

    tool = LibCalWeekHoursTool()

    def get_hours(library_id: str) -> dict:
        canon = (library_id or "king").strip().lower()
        if canon == "sword":
            return {
                "success": False,
                "library": "sword",
                "hours": (
                    "SWORD (Southwest Ohio Regional Depository) is a "
                    "closed-stacks depository with no public walk-in "
                    "hours. Materials are requested, not browsed."
                ),
            }
        name = _CANON_TO_LIBCAL_NAME.get(canon, canon)
        try:
            res = _bridge(tool.execute(query=name, building=name))
        except Exception as e:  # noqa: BLE001
            raise ToolError(
                f"get_hours: LibCal lookup failed for {library_id!r} "
                f"({e}). The bot should say live hours are unavailable, "
                f"not guess."
            ) from e
        return {
            "success": bool(res.get("success")),
            "library": library_id,
            "hours": res.get("text", ""),
            "source_url": "https://www.lib.miamioh.edu/about/hours/",
        }

    return get_hours


def _make_get_room_availability() -> Callable[[dict], list]:
    from src.tools.libcal_comprehensive_tools import (
        LibCalEnhancedAvailabilityTool,
    )

    tool = LibCalEnhancedAvailabilityTool()

    def get_room_availability(args: dict) -> list:
        canon = str(args.get("library") or "king").strip().lower()
        if canon == "sword":
            return [{
                "success": False,
                "note": "SWORD is a closed depository -- no bookable rooms.",
            }]
        name = _CANON_TO_LIBCAL_NAME.get(canon, canon)
        try:
            res = _bridge(tool.execute(
                query=name,
                building=name,
                date=args.get("date"),
                start_time=args.get("start_time"),
                end_time=args.get("end_time"),
                capacity=args.get("capacity"),
            ))
        except Exception as e:  # noqa: BLE001
            raise ToolError(
                f"get_room_availability: LibCal lookup failed "
                f"({e}). The bot should say live availability is "
                f"unavailable, not guess."
            ) from e
        # Handler does len() on this -> always a list. The legacy tool
        # returns one formatted block; wrap it as a single "slot" the
        # LLM narrates (incl. its own missing-params / no-rooms text).
        return [{
            "success": bool(res.get("success")),
            "text": res.get("text", ""),
        }]

    return get_room_availability


# --- assembly ------------------------------------------------------------


def build_eval_backends() -> ToolBackends:
    """ToolBackends for the eval: every READ-ONLY tool wired to its real
    backend (validate_url / lookup_librarian / point_to_url /
    get_hours / get_room_availability). Only write/handoff tools and
    lookup_space stay unset -> ToolBackends.__post_init__ installs the
    labeled unwired sentinel; `_build_real_deps` drops those four from
    the eval surface anyway."""
    return ToolBackends(
        validate_url=_make_validate_url(),
        lookup_librarian=_make_lookup_librarian(),
        point_to_url=_make_point_to_url(),
        get_hours=_make_get_hours(),
        get_room_availability=_make_get_room_availability(),
        # search_kb is intentionally NOT set here: _build_real_deps
        # swaps in the eval's scope-aware, featured-boost search_kb
        # tool (src/tools/search_kb_tool.py), strictly better than the
        # generic tools_v2 one.
    )


__all__ = ["build_eval_backends"]
