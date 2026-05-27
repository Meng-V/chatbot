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


def _libguide_lib_to_dict(lib_entry: dict) -> dict:
    """Map a LibGuides API librarian dict to the bot's lookup_librarian shape.

    The LibApps API returns librarians with `first_name`, `last_name`,
    `email`, `title`, `profile_url`, etc. Our synthesizer reads
    `name/email/title/department/phone/campus/profile_url`."""
    first = lib_entry.get("first_name") or ""
    last = lib_entry.get("last_name") or ""
    full = f"{first} {last}".strip() or lib_entry.get("name", "")
    return {
        "name": full,
        "email": lib_entry.get("email"),
        "title": lib_entry.get("title"),
        "department": lib_entry.get("department"),
        "phone": lib_entry.get("phone"),
        "campus": lib_entry.get("campus"),
        "profile_url": lib_entry.get("profile_url"),
    }


def _make_lookup_librarian() -> Callable[[dict], list[dict]]:
    """Subject/name librarian lookup.

    DESIGN (2026-05-23): use the LIVE LibGuides API via _bridge for
    SUBJECT lookups -- the same production-proven path the legacy
    SubjectLibrarianAgent uses. This avoids the per-call Prisma engine
    spawn that deadlocks the agent loop on librarian-by-subject
    questions (Issue #98). Name-only lookups still go through Prisma
    via _bridge (the prisma singleton on the bridge loop) because the
    LibGuides API is subject-indexed, not name-indexed.

    Subject path: LibGuideSubjectLookupTool.execute(subject_name=...)
    Name path:    prisma singleton via _bridge (NOT _db's per-call
                  fresh engine — that's what hung on case 33 every
                  time)."""
    from src.tools.libguide_comprehensive_tools import LibGuideSubjectLookupTool

    libguide_tool = LibGuideSubjectLookupTool()

    def _lookup_by_subject_via_libguides(subject_term: str, campus: Optional[str]) -> list[dict]:
        """Call the LibApps API. Returns a list of librarian dicts in our
        canonical shape."""
        try:
            res = _bridge(libguide_tool.execute(query=subject_term, subject_name=subject_term))
        except Exception as e:  # noqa: BLE001
            raise ToolError(
                f"lookup_librarian (LibGuides API): {e}. The bot should "
                f"hand off rather than guess a name."
            ) from e
        if not res or not res.get("success"):
            return []
        librarians = res.get("librarians") or []
        out: list[dict] = []
        for lib in librarians:
            d = _libguide_lib_to_dict(lib)
            # Optional campus filter (LibGuides API doesn't always tag
            # campus; if we can't tell, include the librarian).
            if campus and d.get("campus") and d["campus"] != campus:
                continue
            if d.get("email"):
                out.append(d)
        return out

    def lookup(filters: dict) -> list[dict]:
        name = (filters.get("name") or "").strip()
        subject = (filters.get("subject") or "").strip()
        campus_raw = (filters.get("campus") or "").strip().lower()
        campus = _CAMPUS_DB.get(campus_raw)
        resolved = _resolve_subject_terms(subject, name)

        # (1) Highest-precision subject path: every resolved canonical
        # subject is queried against the LIVE LibGuides API. First hit
        # with results wins (the API returns ALL librarians for that
        # subject, so we don't have to merge).
        if resolved:
            for s in resolved:
                rows = _lookup_by_subject_via_libguides(s, campus)
                if rows:
                    return rows

        # (2) Raw subject fallback (no alias resolution). Still goes
        # through the LibGuides API.
        if subject:
            rows = _lookup_by_subject_via_libguides(subject, campus)
            if rows:
                return rows

        # (3) Name / campus direct lookup via the bridge'd Prisma
        # singleton (NOT _db). Used for staff-directory cases
        # ("the dean of the libraries"). Subject is empty here.
        if not name and not campus:
            return []

        async def _q_by_name() -> list[dict]:
            from src.database.prisma_client import get_prisma_client
            client = await get_prisma_client()
            where: dict = {"isActive": True}
            if name:
                where["name"] = {"contains": name, "mode": "insensitive"}
            if campus:
                where["campus"] = campus
            rows = await client.librarian.find_many(where=where)
            return [_librarian_dict(r) for r in rows]

        try:
            return _bridge(_q_by_name())
        except Exception as e:  # noqa: BLE001
            raise ToolError(
                f"lookup_librarian (name/campus): {e}. The bot should "
                f"hand off rather than guess a name."
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
            # Operator-provided and WebFetch-verified 2026-05-16:
            # 200, title "Library Hours | Miami University Libraries",
            # canonical hours hub, no redirect. (Earlier guesses
            # /about/hours/ -> 404 and /about/locations/ -> 302 were
            # rejected; never ship an unverified deep link as a cited
            # URL.) The hours VALUE's authority is still the LibCal
            # live API (the [LIVE] trust tier); this URL is where a
            # user verifies it themselves.
            "source_url": "https://www.lib.miamioh.edu/about/locations/hours/",
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


# --- lookup_space --------------------------------------------------------
#
# Reads from the LibrarySpace_v2 Postgres table (canonical building data:
# canonical_id, name, campus, address, phone, libcal_id, capacity,
# equipment[], services_offered[]). Wiring this was the fix for the
# 2026-05-25 phone-number hallucination bug: without lookup_space, the
# agent had no structured source for "what is the library phone number?"
# and search_kb returned a chunk from the Dean's bio page with his
# personal office number (529-3934) instead of the main number
# (529-4141). Now the agent calls lookup_space("king") and gets the
# canonical phone from the truth table.

# Shared pool for lookup_space queries -- lazily created on first call
# inside the _bridge daemon-thread loop. asyncpg pools are bound to the
# loop that created them, and _bridge always uses the same loop for the
# eval's lifetime, so a single module-level reference is safe. max_size=5
# is plenty for sequential lookup_space calls and caps the connection
# count regardless of how many lookups fire during a long eval.
_LOOKUP_SPACE_POOL: Any = None


async def _get_lookup_space_pool() -> Any:
    global _LOOKUP_SPACE_POOL
    if _LOOKUP_SPACE_POOL is None:
        import asyncpg
        import os as _os
        _LOOKUP_SPACE_POOL = await asyncpg.create_pool(
            _os.environ["DATABASE_URL"],
            min_size=1,
            max_size=5,
            command_timeout=10.0,
        )
    return _LOOKUP_SPACE_POOL


def _make_lookup_space() -> Callable[[dict], Any]:
    """Look up a LibrarySpace_v2 row by canonical library id or by name.

    Returns a dict with the structured building info (address, phone,
    services_offered, equipment, capacity, libcal_id). Returns None if
    no matching row -- handler narrates that as `{found: false}`.
    """
    # Canonical-id direct map + alias resolution for the common phrasings
    # the agent / kNN classifier produces. R5 retest showed the agent often
    # passes the FULL building name ("King Library", "Wertz Art Library",
    # "Gardner-Harvey Library") rather than the short canonical id; missing
    # those compound forms made the bot refuse address questions when
    # lookup_space had the data right there. Aliases are matched lowercase.
    _ALIASES = {
        # king
        "king": "king",
        "king library": "king",
        "edward king": "king",
        "edward king library": "king",
        "main library": "king",
        "the library": "king",  # ambiguous default -> king (Oxford flagship)
        "miami university libraries": "king",
        # wertz
        "wertz": "wertz",
        "wertz library": "wertz",
        "wertz art": "wertz",
        "wertz art library": "wertz",
        "wertz art & architecture": "wertz",
        "wertz art & architecture library": "wertz",
        "wertz art and architecture library": "wertz",
        "art library": "wertz",
        "art and architecture": "wertz",
        "art and architecture library": "wertz",
        "art & architecture": "wertz",
        "art & architecture library": "wertz",
        "a&a": "wertz",
        "a&a library": "wertz",
        # special collections
        "special": "special",
        "special collections": "special",
        "special collections and university archives": "special",
        "special collections & university archives": "special",
        "walter havighurst": "special",
        "walter havighurst special collections": "special",
        "scua": "special",
        "archives": "special",
        "university archives": "special",
        # rentschler / hamilton
        "rentschler": "rentschler",
        "rentschler library": "rentschler",
        "hamilton": "rentschler",
        "hamilton library": "rentschler",
        "the hamilton library": "rentschler",
        # gardner-harvey / middletown
        "gardner-harvey": "gardner_harvey",
        "gardner harvey": "gardner_harvey",
        "gardner-harvey library": "gardner_harvey",
        "gardner harvey library": "gardner_harvey",
        "middletown": "gardner_harvey",
        "middletown library": "gardner_harvey",
        "the middletown library": "gardner_harvey",
        # sword
        "sword": "sword",
        "sword depository": "sword",
        "depository": "sword",
        "regional depository": "sword",
        "southwest ohio regional depository": "sword",
    }

    async def _q(canonical: str) -> Optional[dict]:
        # POOLED asyncpg query (vs the earlier per-call connect). Pool
        # is lazily created on first call inside the _bridge loop and
        # cached for the life of the eval. WHY POOLING: the merged-271
        # run on 2026-05-27 crashed 10 cases with RuntimeError /
        # AttributeError that had worked fine in R4 (smaller per-call
        # eval). Theory was connection exhaustion -- each lookup_space
        # call was opening a fresh socket; over 140 cases x N calls/case
        # we accumulated CLOSE_WAIT sockets faster than Postgres
        # released them, and downstream cases that hit *any* DB-touching
        # codepath (capability_scope check_account, account/loan/renew
        # short-circuits) failed because the bridge loop's connection
        # attempts errored. Pool with max_size=5 caps the concurrent
        # connection count regardless of how many lookups fire.
        pool = await _get_lookup_space_pool()
        async with pool.acquire() as conn:
            # Column names per prisma/schema.prisma model LibrarySpace_v2:
            #   library, campus, name, building_role, address, phone,
            #   libcal_id, capacity, equipment, services_offered,
            #   hours_source, source_url. All snake_case in SQL.
            row = await conn.fetchrow(
                'SELECT library, name, campus, address, phone, '
                'libcal_id, capacity, equipment, services_offered, '
                'building_role, source_url '
                'FROM "LibrarySpace_v2" WHERE library = $1',
                canonical,
            )
        if not row:
            return None
        return {
            "library": row["library"],
            "name": row["name"],
            "campus": row["campus"],
            "address": row["address"],
            "phone": row["phone"],
            "libcal_id": row["libcal_id"],
            "capacity": row["capacity"],
            "equipment": list(row["equipment"] or []),
            "services_offered": list(row["services_offered"] or []),
            "building_role": row["building_role"],
            # Provenance for synthesizer to cite. Prefer the row's own
            # source_url; fall back to the per-building map. Either way
            # the URL is in the allowlist so citation_invalid won't fire.
            "source_url": (
                row["source_url"]
                or _SPACE_SOURCE_URL.get(
                    row["library"] or "",
                    "https://www.lib.miamioh.edu/about/locations/",
                )
            ),
        }

    def handler(filters: dict) -> Optional[dict]:
        library = (filters.get("library") or "").strip().lower()
        name = (filters.get("name") or "").strip().lower()
        # Try direct canonical id first, then alias resolution from
        # either field (LLM may put a human name in either slot).
        candidates: list[str] = []
        if library:
            candidates.append(_ALIASES.get(library, library))
        if name:
            candidates.append(_ALIASES.get(name, name))
        for canon in candidates:
            if not canon:
                continue
            try:
                space = _bridge(_q(canon))
            except Exception as e:  # noqa: BLE001
                raise ToolError(
                    f"lookup_space: Postgres query failed ({e}). "
                    f"The bot should hand off rather than guess."
                ) from e
            if space:
                return space
        return None

    return handler


_SPACE_SOURCE_URL = {
    "king": "https://www.lib.miamioh.edu/about/locations/king-library/",
    "wertz": "https://www.lib.miamioh.edu/about/locations/art-arch/",
    "special": "https://www.lib.miamioh.edu/about/locations/special-collections-archives/",
    "rentschler": "https://www.ham.miamioh.edu/library/about/",
    "gardner_harvey": "https://www.mid.miamioh.edu/library/",
    "sword": "https://www.lib.miamioh.edu/about/locations/regional/sword/",
}


# --- assembly ------------------------------------------------------------


def build_eval_backends() -> ToolBackends:
    """ToolBackends for the eval: every READ-ONLY tool wired to its real
    backend (validate_url / lookup_librarian / lookup_space /
    point_to_url / get_hours / get_room_availability). Only write /
    handoff tools stay unset -> ToolBackends.__post_init__ installs the
    labeled unwired sentinel; `_build_real_deps` drops those from
    the eval surface anyway."""
    return ToolBackends(
        validate_url=_make_validate_url(),
        lookup_librarian=_make_lookup_librarian(),
        lookup_space=_make_lookup_space(),
        point_to_url=_make_point_to_url(),
        get_hours=_make_get_hours(),
        get_room_availability=_make_get_room_availability(),
        # search_kb is intentionally NOT set here: _build_real_deps
        # swaps in the eval's scope-aware, featured-boost search_kb
        # tool (src/tools/search_kb_tool.py), strictly better than the
        # generic tools_v2 one.
    )


__all__ = ["build_eval_backends"]
