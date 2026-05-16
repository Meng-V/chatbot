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
from src.tools.subject_aliases import (
    find_subject_by_alias,
    find_subject_by_course_code,
    find_subjects_by_librarian_name,
)
from src.tools.enhanced_subject_search import extract_course_codes
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


def _resolve_subject_terms(subject: str, name: str) -> list[str]:
    """Map the user's wording to CANONICAL subject names using the
    project's OWN curated maps (src/tools/subject_aliases +
    enhanced_subject_search) -- the exact resolution the hand-rolled
    lookup lacked. Pure/static: 212 aliases, 64 course-code prefixes,
    17 librarian-name->subjects entries; no DB, no network. Order:
    course code (highest precision) -> alias -> librarian-name.
    Deduped, original order preserved."""
    out: list[str] = []
    blob = f"{subject} {name}".strip()

    # Course codes anywhere in the text ("ENG 111", "BIO 161").
    for code in extract_course_codes(blob):
        s = find_subject_by_course_code(code)
        if s:
            out.append(s)

    # Alias on the subject phrase ("bio" -> "Biology").
    if subject:
        a = find_subject_by_alias(subject)
        if a:
            out.append(a)

    # "the <name> librarian" / a liaison's own name -> their subjects.
    if name:
        out.extend(find_subjects_by_librarian_name(name))

    seen: set[str] = set()
    deduped: list[str] = []
    for s in out:
        if s not in seen:
            seen.add(s)
            deduped.append(s)
    return deduped


def _make_lookup_librarian() -> Callable[[dict], list[dict]]:
    def lookup(filters: dict) -> list[dict]:
        name = (filters.get("name") or "").strip()
        subject = (filters.get("subject") or "").strip()
        campus_raw = (filters.get("campus") or "").strip().lower()
        campus = _CAMPUS_DB.get(campus_raw)
        resolved = _resolve_subject_terms(subject, name)

        def _collect(links: list, acc: dict) -> None:
            for link in links:
                lib = getattr(link, "librarian", None)
                if lib is None or not getattr(lib, "isActive", True):
                    continue
                if campus and getattr(lib, "campus", None) != campus:
                    continue
                acc[lib.email] = _librarian_dict(lib)

        async def _q(client: Any) -> list[dict]:
            seen: dict[str, dict] = {}

            # (1) Highest precision: resolved canonical subject names
            # (exact, case-insensitive) via the curated alias/code maps.
            if resolved:
                links = await client.librariansubject.find_many(
                    where={
                        "subject": {
                            "is": {
                                "OR": [
                                    {"name": {"equals": s, "mode": "insensitive"}}
                                    for s in resolved
                                ]
                            }
                        }
                    },
                    include={"librarian": True},
                )
                _collect(links, seen)

            # (2) Fallback: raw subject contains-match (the original
            # proven path -- preserved so we cannot regress).
            if subject and not seen:
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
                _collect(links, seen)

            if seen:
                return list(seen.values())

            # (3) Name / campus direct Librarian lookup (unchanged).
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
    "holds": (
        # capability_scope LIMITATIONS["place_holds"].response uses this
        # exact URL -> stays drift-guard-safe.
        "https://www.lib.miamioh.edu/",
        "Place and manage holds through your library account "
        "(start from the Libraries homepage). The bot can't place "
        "holds for you.",
    ),
}

# scope.campus (lowercase canonical) -> ILL_URLS key.
_CAMPUS_TO_ILL_KEY = {
    "oxford": "main",
    "hamilton": "hamilton",
    "middletown": "middletown",
}
_ILL_SERVICES = {"ill", "interlibrary_loan", "interlibrary loan"}

# Phrasing the LLM actually emits -> a canonical key (above, or "ill").
# This is the gap the failing `circulation` cases hit: the URLs were
# already correct + verified, but point_to_url only keyed on the exact
# canonical tokens, so "renew my books" / "reserves" / "place a hold"
# fell through to a refusal. Synonyms add ZERO new URLs (drift guard
# stays green) -- they only widen the door to the same verified links.
_SERVICE_SYNONYMS: dict[str, str] = {
    "renew": "renewals", "renewal": "renewals", "renew book": "renewals",
    "renew books": "renewals", "renew my books": "renewals",
    "extend": "renewals", "extend loan": "renewals",
    "extend my loan": "renewals", "reborrow": "renewals",
    "reserve": "course_reserves", "reserves": "course_reserves",
    "course reserve": "course_reserves",
    "course reserves": "course_reserves",
    "e-reserves": "course_reserves", "ereserves": "course_reserves",
    "textbook": "course_reserves", "textbooks": "course_reserves",
    "reserve reading": "course_reserves",
    "fine": "fines", "fee": "fines", "fees": "fines",
    "overdue": "fines", "pay fine": "fines", "pay fines": "fines",
    "late fee": "fines",
    "my account": "account", "library account": "account",
    "patron account": "account", "ohiolink": "account",
    "ohiolink account": "account", "primo": "account",
    "check account": "account", "checkouts": "account",
    "my checkouts": "account",
    "hold": "holds", "place hold": "holds", "place a hold": "holds",
    "place holds": "holds", "request item": "holds",
    "request a book": "holds",
    "interlibrary": "ill", "ill request": "ill",
    "document delivery": "ill",
    "borrow from another library": "ill",
}


def _canonical_service(raw: str) -> str:
    """Normalize an LLM-emitted service token to a canonical key.
    Exact synonym first, then longest substring match so free-text
    like 'how do I renew my books' still resolves."""
    key = (raw or "").strip().lower()
    if key in _SERVICE_SYNONYMS:
        return _SERVICE_SYNONYMS[key]
    if key in _POINT_TO_URL or key in _ILL_SERVICES:
        return key
    for phrase in sorted(_SERVICE_SYNONYMS, key=len, reverse=True):
        if phrase in key:
            return _SERVICE_SYNONYMS[phrase]
    return key


def _make_point_to_url() -> Callable[[str, dict], dict]:
    def point(service: str, scope: dict) -> dict:
        key = _canonical_service(service)

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
