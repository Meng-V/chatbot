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

        # Subject terms incl. campus variants -- shared by the DB
        # fallback AND the guide-attach wrapper below.
        _SUFFIX = {"hamilton": " - HC", "middletown": " - MC"}
        terms0 = list(resolved) if resolved else ([subject] if subject else [])
        expanded: list[str] = []
        for t in terms0:
            if campus in _SUFFIX:
                expanded.append(t + _SUFFIX[campus])
            expanded.append(t)

        def _with_guides(rows: list[dict]) -> list[dict]:
            """Attach the subject's LibGuide URL (Subject ->
            SubjectLibGuide -> LibGuide.url, operator data) to every
            row, REGARDLESS of which path produced them -- the
            LibGuides-API paths return before the DB block, which is
            why guide_url came back None for API-served subjects."""
            if not rows or not expanded:
                return rows

            async def _q(client):
                subs = await client.subject.find_many(
                    where={"name": {"in": expanded}})
                if not subs:
                    subs = await client.subject.find_many(where={"OR": [
                        {"name": {"contains": t, "mode": "insensitive"}}
                        for t in expanded
                    ]})
                sids = [s.id for s in subs]
                if not sids:
                    return None
                gl = await client.subjectlibguide.find_many(
                    where={"subjectId": {"in": sids}})
                gnames = list({g.libGuide for g in gl if g.libGuide})
                if not gnames:
                    return None
                lg = await client.libguide.find_many(
                    where={"name": {"in": gnames}})
                return (lg[0].name, lg[0].url) if lg else None

            try:
                got = _db(_q)
                if got:
                    for d in rows:
                        d.setdefault("guide_name", got[0])
                        d.setdefault("guide_url", got[1])
            except Exception as e:  # noqa: BLE001 -- guides are garnish, never break a lookup
                logger.warning("lookup_librarian guide attach failed: %s", e)
            return rows

        # (1) Highest-precision subject path: every resolved canonical
        # subject is queried against the LIVE LibGuides API. First hit
        # with results wins (the API returns ALL librarians for that
        # subject, so we don't have to merge).
        if resolved:
            for s in resolved:
                rows = _lookup_by_subject_via_libguides(s, campus)
                if rows:
                    return _with_guides(rows)

        # (2) Raw subject fallback (no alias resolution). Still goes
        # through the LibGuides API.
        if subject:
            rows = _lookup_by_subject_via_libguides(subject, campus)
            if rows:
                return _with_guides(rows)

        # (2.5) Postgres fallback: the operator's curated Subject /
        # LibrarianSubject / Librarian tables. Verified complete
        # 2026-06-10 (Marketing -> Erica Freed + Abigail Morgan; regional
        # " - HC"/" - MC" subject variants present) -- but the LibGuides
        # API misses some of these subjects, so until now this entire
        # dataset was DEAD: subject lookups never touched the DB and the
        # bot refused (audit case r1_librarian_marketing). Campus-aware:
        # hamilton/middletown asks also try the " - HC"/" - MC" variant
        # rows the operator created for exactly that purpose.
        if expanded:

            async def _q_by_subject_db(client) -> list[dict]:
                links = await client.librariansubject.find_many(
                    where={"subject": {"is": {"name": {"in": expanded}}}},
                    include={"librarian": True},
                )
                if not links:
                    # Variant fallback: the operator's Subject names are
                    # often qualified ("Undeclared - Business", "Business
                    # Management", "Marketing - HC"), so an exact IN on
                    # the canonical term ("Business") misses. Retry as a
                    # case-insensitive contains per term; the email
                    # dedupe + caller's 5-cap + the staff-privacy guard
                    # keep a broad match from becoming a roster dump.
                    links = await client.librariansubject.find_many(
                        where={"OR": [
                            {"subject": {"is": {"name": {
                                "contains": t, "mode": "insensitive"}}}}
                            for t in expanded
                        ]},
                        include={"librarian": True},
                    )
                seen: set[str] = set()
                out: list[dict] = []
                for l in links:
                    r = l.librarian
                    if r is None or not getattr(r, "email", None):
                        continue
                    if getattr(r, "isActive", True) is False:
                        continue
                    if campus and getattr(r, "campus", None) and r.campus != campus:
                        continue
                    if r.email in seen:
                        continue
                    seen.add(r.email)
                    out.append(_librarian_dict(r))
                # Attach the subject's LibGuide (operator data:
                # Subject -> SubjectLibGuide.libGuide name -> LibGuide.url)
                # so guide questions ("is there a guide for BUS217?")
                # get a citable URL. Emitted as its OWN evidence chunk
                # by the orchestrator -- a bare URL in answer text would
                # trip post-processor rule 3.
                if out:
                    # Query by the subjectIds that actually MATCHED above
                    # (works for variant names too), not by exact name.
                    _sids = list({l.subjectId for l in links if l.subjectId})
                    glinks = await client.subjectlibguide.find_many(
                        where={"subjectId": {"in": _sids}},
                    )
                    gnames = list({g.libGuide for g in glinks if g.libGuide})
                    if gnames:
                        guides = await client.libguide.find_many(
                            where={"name": {"in": gnames}},
                        )
                        if guides:
                            for d in out:
                                d["guide_name"] = guides[0].name
                                d["guide_url"] = guides[0].url
                return out

            try:
                rows = _db(_q_by_subject_db)
                if rows:
                    return rows
            except Exception as e:  # noqa: BLE001 -- DB fallback must not break the turn
                logger.warning("lookup_librarian DB-subject fallback failed: %s", e)

        # (3) Name / campus direct lookup via the bridge'd Prisma
        # singleton (NOT _db). Used for staff-directory cases
        # ("the dean of the libraries"). Subject is empty here.
        if not name and not campus:
            return []

        # Fresh-client _db pattern, NOT the bridge'd singleton:
        # `get_prisma_client()` is sync (the old `await` of it made this
        # path raise "'Prisma' object can't be awaited" on EVERY
        # name/campus lookup since it shipped -- found 2026-06-10).
        async def _q_by_name(client) -> list[dict]:
            where: dict = {"isActive": True}
            if name:
                where["name"] = {"contains": name, "mode": "insensitive"}
            if campus:
                where["campus"] = campus
            rows = await client.librarian.find_many(where=where)
            return [_librarian_dict(r) for r in rows]

        try:
            return _db(_q_by_name)
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
        # exact URL -> stays drift-guard-safe. (2026-06-09: both moved
        # from the bare homepage to Primo search -- the homepage doesn't
        # show how to place a hold; Primo's item page has the button.)
        "https://ohiolink-mu.primo.exlibrisgroup.com/discovery/search?vid=01OHIOLINK_MU:MU",
        "Search the item in Primo, click \"Place Hold\" on the title, "
        "and sign in. The bot can't place holds for you.",
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


def _make_search_kb() -> Callable[[str, dict], list[dict]]:
    """Generic search_kb backend for the v2 SERVING path.

    CRITICAL (2026-06-08): without this, `ToolBackends.search_kb` was the
    unwired sentinel in production v2 -- every search_kb call raised
    "Backend 'search_kb' is not wired", so the agent got zero evidence and
    the bot refused (or, pre-A3, fabricated a URL from the synth prompt's
    reference list -> the Adobe-404 incident). The eval path swaps in the
    scope-aware tool in `run_eval._build_real_deps`, but the serving path
    (`build_v2_deps`) never did the equivalent swap. This wires the real
    Weaviate hybrid retrieval so prose questions (printing, special
    collections, room-booking how-to, policies, service descriptions) can
    actually be answered.

    Signature matches `tools_v2.registry._make_search_kb`'s backend call:
    `search_kb(query, scope_dict) -> list[{chunk_id, source_url, snippet,
    campus, library, topic}]`.

    Fault-tolerance: the WeaviateSearchAdapter is built LAZILY on first use,
    not here. Building it touches Weaviate, and `build_eval_backends()` runs
    at deps-construction time -- if we built it eagerly, a Weaviate outage
    (or a dropped SSH tunnel on a dev laptop) would raise and crash the
    ENTIRE deps build, taking down every intent (hours, librarians, etc.),
    not just search. Lazy + try/except means a Weaviate hiccup degrades
    search_kb to "no results" (the agent refuses that one prose turn) while
    the rest of the bot keeps working. The adapter is cached after the first
    successful build.
    """
    from src.retrieval.search import RetrievalRequest, search_kb as _retrieval
    from src.retrieval.scope_filter import ScopeFilter

    _holder: dict = {}

    def _adapter():
        a = _holder.get("a")
        if a is None:
            from src.weaviate_adapters.search_adapter import WeaviateSearchAdapter
            a = WeaviateSearchAdapter()
            _holder["a"] = a
        return a

    def search_kb(query: str, scope: dict) -> list[dict]:
        try:
            adapter = _adapter()
        except Exception as e:  # noqa: BLE001 -- Weaviate down must not crash the turn
            logger.warning(
                "search_kb: Weaviate adapter unavailable (%s: %s); returning "
                "no results (this prose turn will refuse, rest of bot is fine)",
                type(e).__name__, e,
            )
            return []
        scope = scope or {}
        sf = ScopeFilter(
            campus=scope.get("campus") or "oxford",
            # NOTE: the agent sometimes over-specifies library (e.g. passes
            # library="king" for a generic "how do I print" query). Many
            # service chunks carry library="" and would be hard-filtered
            # out by a library clause. The orchestrator's resolved scope is
            # the authority on whether a building was actually named; the
            # agent's guess is not, so we drop library here and let campus
            # + ranking decide. (Building-specific facts go through
            # lookup_space / get_hours, not prose search.)
            library=None,
            featured_service=scope.get("featured_service"),
        )
        result = _retrieval(RetrievalRequest(query=query, scope=sf), weaviate=adapter)
        out: list[dict] = []
        for c in result.chunks:
            out.append({
                "chunk_id": getattr(c, "chunk_id", None),
                "source_url": getattr(c, "source_url", ""),
                "snippet": getattr(c, "text", ""),
                "campus": getattr(c, "campus", None),
                "library": getattr(c, "library", None),
                "topic": getattr(c, "topic", None),
            })
        return out

    return search_kb


def _make_book_room() -> Callable[[dict], dict]:
    """REAL LibCal room booking -- revives v1's
    LibCalComprehensiveReservationTool (operator-written: building/email/
    date/time validation, ≤2h cap, building-hours check, availability
    query + capacity best-fit, POST /space/reserve) as the v2 `book_room`
    backend, with one addition v1 never had: a CONFIRM gate. The write
    cannot fire unless `confirm=true`, which the agent may only set after
    the user explicitly confirms the summary.

    Protocol per call (the tool's text IS the bot's next conversational
    move -- the orchestrator maps it to [LIVE] evidence either way):
      1. building invalid ("OSU", "Farmer")   -> we-don't-book-there text
         listing the real bookable libraries (operator requirement #1).
      2. slots missing                        -> v1's friendly
         "I still need: ..." list (no side effects possible).
      3. slots complete, confirm absent       -> deterministic summary +
         "reply 'confirm'" (does NOT call the v1 tool; no side effects).
      4. confirm=true                         -> v1 tool end-to-end:
         re-validates everything, checks availability (operator
         requirement #2), books, returns the confirmation number.
    """
    from src.tools.libcal_comprehensive_tools import (
        LibCalComprehensiveReservationTool,
        _validate_library_for_rooms,
    )

    tool = LibCalComprehensiveReservationTool()
    _REQUIRED = ("date", "start_time", "end_time",
                 "first_name", "last_name", "email")

    def book_room(args: dict) -> dict:
        building = str(args.get("building") or "").strip()
        ok, err_text, display = _bridge(
            _validate_library_for_rooms(building), timeout=20.0
        )
        if not ok:
            return {"success": False, "stage": "invalid_building",
                    "text": err_text}

        missing = [k for k in _REQUIRED if not args.get(k)]
        if not missing and not args.get("confirm"):
            cap = args.get("room_capacity") or 2
            return {
                "success": False,
                "stage": "needs_confirmation",
                "text": (
                    f"Ready to book: a study room at {display} on "
                    f"{args['date']}, {args['start_time']} to "
                    f"{args['end_time']}, for {args['first_name']} "
                    f"{args['last_name']} ({args['email']}), party of "
                    f"{cap}. Reply 'confirm' to book it, or tell me what "
                    f"to change. Nothing is booked yet."
                ),
            }

        # Missing slots -> v1 returns its "I still need ..." text and
        # cannot book. confirm=true -> v1 validates everything
        # (email domain, date/time parsing, 2h cap, building hours,
        # live availability + capacity fit) and POSTs the reservation.
        res = _bridge(
            tool.execute(
                query="v2 booking flow",
                first_name=args.get("first_name"),
                last_name=args.get("last_name"),
                email=args.get("email"),
                date=args.get("date"),
                start_time=args.get("start_time"),
                end_time=args.get("end_time"),
                room_capacity=args.get("room_capacity"),
                room_code_name=args.get("room_code_name"),
                building=building,
            ),
            timeout=60.0,
        )
        return {
            "success": bool(res.get("success")),
            "stage": "booked" if res.get("success") else "tool_response",
            "text": res.get("text", ""),
        }

    return book_room


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
        # search_kb: wired here so the v2 SERVING path (build_v2_deps,
        # which calls build_eval_backends) gets real prose retrieval --
        # previously it was the unwired sentinel in production. The EVAL
        # path (run_eval._build_real_deps) still pops this and swaps in
        # its scope-aware, featured-boost tool, so eval behavior is
        # unchanged; only serving gains a working search_kb.
        search_kb=_make_search_kb(),
        # book_room: REAL LibCal booking (v1 tool + confirm gate). The
        # EVAL path pops it (write tool, never fired during eval); only
        # serving exposes it to the agent.
        book_room=_make_book_room(),
    )


__all__ = ["build_eval_backends"]
