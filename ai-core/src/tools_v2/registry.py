"""
The 10-tool surface for the single tool-calling agent.

Tool list (per plan Layer 3):

    Read-only / lookup:
      search_kb              -- hybrid Weaviate search, scope-filtered
      lookup_librarian       -- Postgres lookup by subject / name
      lookup_space           -- Postgres lookup of LibrarySpace
                                (capacity, equipment, services_offered)
      get_hours              -- live LibCal hours for a library
      get_room_availability  -- live LibCal room availability
      validate_url           -- check a URL against UrlSeen allowlist

    Action / write:
      book_room              -- live LibCal booking (requires user confirm)
      create_ticket          -- LibAnswers ticket create (action)
      handoff_human          -- escalate to a librarian via Ask Us

    Pointer (no action -- returns a URL the user submits themselves):
      point_to_url           -- canonical URL for a service the bot
                                must NOT roleplay (ILL, account ops,
                                renewals, course reserves submission)

Why these and not the legacy 6-agent map: the agent picks a tool per
turn, not an agent up front. So we don't need 1 tool per agent -- we
need 1 tool per *atomic capability*. The list above is the union of
what the legacy agents collectively did, deduplicated.

All tool handlers receive `args: dict` (the LLM-emitted arguments) and
return JSON-serializable data. Expected failures raise `ToolError` so
the agent loop hands a structured error message back to the model
rather than a stack trace.

Implementation status: handler bodies are stubs / wrappers around
injectable backend callables (`ToolBackends`). The handlers know the
*shape* of every call; the *transport* (HTTP to LibCal, SQL to
Postgres, etc.) is the backend's job. Sandbox tests pass stub backends
that return canned data; prod startup wires real backends.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from src.agent.tool_registry import Tool, ToolError, ToolRegistry


# --- Backend seam ---------------------------------------------------------


@dataclass
class ToolBackends:
    """Injectable services the tool handlers depend on.

    Every backing service (Weaviate, Postgres, LibCal, LibAnswers) is
    a Callable on this dataclass. That gives us:
      - One place to see every external dependency the tool surface
        requires.
      - Tests pass `ToolBackends(search_kb=stub, lookup_librarian=stub, ...)`
        and never touch the real services.
      - Prod startup constructs `ToolBackends(search_kb=weaviate_search, ...)`
        in `main.py`.

    Fields default to a `_not_wired` sentinel that raises ToolError. So
    if prod startup forgets to wire a backend, the agent's first
    invocation surfaces it as a normal tool failure (which the LLM
    then narrates back to the user via the refusal flow), rather than
    as an obscure attribute error.

    Signatures match the handler contracts below. Each backend takes
    only the data it needs -- the handler does the JSON-schema-shape
    -> backend-arg mapping.
    """

    # search & validation
    search_kb: Callable[[str, dict], list[dict]] = None  # type: ignore
    """search_kb(query, scope_dict) -> list of evidence chunks."""
    validate_url: Callable[[str], bool] = None  # type: ignore
    """validate_url(url) -> True iff URL in UrlSeen and not blacklisted."""

    # entity lookups (Postgres)
    lookup_librarian: Callable[[dict], list[dict]] = None  # type: ignore
    """lookup_librarian({subject?, name?, campus?}) -> list of librarian dicts."""
    lookup_space: Callable[[dict], Optional[dict]] = None  # type: ignore
    """lookup_space({library?, name?}) -> LibrarySpace dict or None."""

    # live API calls
    get_hours: Callable[[str], dict] = None  # type: ignore
    """get_hours(library_id) -> {today: {open, close}, week: [...], source_url}."""
    get_room_availability: Callable[[dict], list[dict]] = None  # type: ignore
    """get_room_availability({library, date, capacity?, equipment?}) -> list of slots."""

    # actions (write)
    book_room: Callable[[dict], dict] = None  # type: ignore
    """book_room({room_id, start, end, user_email}) -> {confirmation_id, ...}."""
    create_ticket: Callable[[dict], dict] = None  # type: ignore
    """create_ticket({subject, body, user_email}) -> {ticket_id, ...}."""

    # handoff and pointer
    handoff_human: Callable[[dict], dict] = None  # type: ignore
    """handoff_human({reason, transcript_id?}) -> {handoff_url, queue_position?}."""
    point_to_url: Callable[[str, dict], dict] = None  # type: ignore
    """point_to_url(service_id, scope) -> {url, description}.

    `service_id` keys: ill / account / renewals / course_reserves.
    Returns the canonical URL plus a one-line description. The bot
    surfaces both; it does not perform the action. See plan §"Action
    vs guidance distinction"."""

    def __post_init__(self) -> None:
        # Replace any unset backend with a sentinel that raises a
        # ToolError when called. Prod that forgets to wire a backend
        # gets a clear "backend X not wired" message, not AttributeError.
        for name in (
            "search_kb",
            "validate_url",
            "lookup_librarian",
            "lookup_space",
            "get_hours",
            "get_room_availability",
            "book_room",
            "create_ticket",
            "handoff_human",
            "point_to_url",
        ):
            if getattr(self, name) is None:
                setattr(self, name, _make_unwired_sentinel(name))


def _make_unwired_sentinel(backend_name: str):
    def _unwired(*args, **kwargs):
        raise ToolError(
            f"Backend {backend_name!r} is not wired. "
            f"In prod, ToolBackends must be constructed with a real "
            f"{backend_name} callable in main.py at startup."
        )

    return _unwired


# --- Tool handlers --------------------------------------------------------
#
# Each handler:
#   1. Pulls args out of the LLM-emitted dict.
#   2. Validates argument presence / shape (raises ToolError on bad
#      input -- the LLM sometimes forgets a required arg).
#   3. Calls into the backend.
#   4. Shapes the result into the dict the LLM sees on the next turn.
#
# Keep handlers small. Heavy logic belongs in the backend.


def _make_search_kb(backends: ToolBackends) -> Callable[[dict], Any]:
    def handler(args: dict) -> Any:
        query = args.get("query")
        if not query or not isinstance(query, str):
            raise ToolError("search_kb requires a non-empty 'query' string.")

        # Scope is optional in the tool args; orchestrator may also
        # pass it through tool_dispatch context. For now, accept it
        # as an argument the LLM CAN provide but doesn't have to.
        scope = args.get("scope") or {}
        if not isinstance(scope, dict):
            raise ToolError("search_kb 'scope' must be an object if present.")

        chunks = backends.search_kb(query, scope)
        # Shape: a list of {chunk_id, source_url, snippet, campus,
        # library, topic} dicts. The LLM sees this verbatim.
        return {"chunks": chunks, "count": len(chunks)}

    return handler


def _make_validate_url(backends: ToolBackends) -> Callable[[dict], Any]:
    def handler(args: dict) -> Any:
        url = args.get("url")
        if not url or not isinstance(url, str):
            raise ToolError("validate_url requires a non-empty 'url' string.")
        ok = backends.validate_url(url)
        return {"url": url, "is_valid": bool(ok)}

    return handler


def _make_lookup_librarian(backends: ToolBackends) -> Callable[[dict], Any]:
    def handler(args: dict) -> Any:
        # Accept any of these as filters -- the LLM picks based on the
        # user's wording. At least ONE must be present; refusing to
        # search "all librarians" prevents accidental dumps.
        if not any(args.get(k) for k in ("subject", "name", "campus")):
            raise ToolError(
                "lookup_librarian requires at least one of "
                "'subject', 'name', or 'campus'."
            )
        rows = backends.lookup_librarian(
            {
                "subject": args.get("subject"),
                "name": args.get("name"),
                "campus": args.get("campus"),
            }
        )
        if not rows:
            # A no-match is a real outcome the LLM should narrate
            # ("I don't see a librarian for that subject"). Don't
            # raise -- raising would make it look like a bug.
            return {"librarians": [], "count": 0}
        return {"librarians": rows, "count": len(rows)}

    return handler


def _make_lookup_space(backends: ToolBackends) -> Callable[[dict], Any]:
    def handler(args: dict) -> Any:
        if not (args.get("library") or args.get("name")):
            raise ToolError(
                "lookup_space requires 'library' (canonical id) or 'name'."
            )
        space = backends.lookup_space(
            {"library": args.get("library"), "name": args.get("name")}
        )
        if space is None:
            return {"space": None, "found": False}
        return {"space": space, "found": True}

    return handler


def _make_get_hours(backends: ToolBackends) -> Callable[[dict], Any]:
    def handler(args: dict) -> Any:
        library_id = args.get("library")
        if not library_id:
            raise ToolError("get_hours requires 'library' (canonical id).")
        return backends.get_hours(library_id)

    return handler


def _make_get_room_availability(backends: ToolBackends) -> Callable[[dict], Any]:
    def handler(args: dict) -> Any:
        if not args.get("library"):
            raise ToolError("get_room_availability requires 'library'.")
        if not args.get("date"):
            raise ToolError(
                "get_room_availability requires 'date' (ISO YYYY-MM-DD)."
            )
        slots = backends.get_room_availability(
            {
                "library": args["library"],
                "date": args["date"],
                "capacity": args.get("capacity"),
                "equipment": args.get("equipment"),
            }
        )
        return {"slots": slots, "count": len(slots)}

    return handler


def _make_book_room(backends: ToolBackends) -> Callable[[dict], Any]:
    def handler(args: dict) -> Any:
        # The agent loop is responsible for surfacing user confirmation
        # before invoking a non-read-only tool. That's enforced at the
        # registry level via Tool.is_read_only=False, not here -- the
        # handler trusts that confirmation already happened.
        for required in ("room_id", "start", "end", "user_email"):
            if not args.get(required):
                raise ToolError(
                    f"book_room requires '{required}'. Got args: "
                    f"{sorted(args.keys())}"
                )
        return backends.book_room(args)

    return handler


def _make_create_ticket(backends: ToolBackends) -> Callable[[dict], Any]:
    def handler(args: dict) -> Any:
        for required in ("subject", "body", "user_email"):
            if not args.get(required):
                raise ToolError(
                    f"create_ticket requires '{required}'."
                )
        return backends.create_ticket(args)

    return handler


def _make_handoff_human(backends: ToolBackends) -> Callable[[dict], Any]:
    def handler(args: dict) -> Any:
        # `reason` is required so the handoff card shows the librarian
        # WHY the bot escalated, not a context-free "user wants help".
        if not args.get("reason"):
            raise ToolError(
                "handoff_human requires 'reason' (one short sentence)."
            )
        return backends.handoff_human(args)

    return handler


def _make_point_to_url(backends: ToolBackends) -> Callable[[dict], Any]:
    def handler(args: dict) -> Any:
        service = args.get("service")
        if not service:
            raise ToolError(
                "point_to_url requires 'service' (e.g. 'ill', 'account', "
                "'renewals', 'course_reserves')."
            )
        scope = args.get("scope") or {}
        if not isinstance(scope, dict):
            raise ToolError("point_to_url 'scope' must be an object.")
        return backends.point_to_url(service, scope)

    return handler


# --- JSON schemas ---------------------------------------------------------
#
# Each tool's schema is the OpenAI tools= "parameters" object: a JSON
# Schema object describing the args. We keep these inline (not in YAML)
# so the schema and the handler live next to each other -- whoever
# changes one sees the other.

_SEARCH_KB_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": (
                "The user's information need, paraphrased into a search "
                "query. Keep concrete nouns ('Wertz hours', 'MakerSpace "
                "3D printer'); strip filler ('please', 'can you tell me')."
            ),
        },
        "scope": {
            "type": "object",
            "description": (
                "Optional campus/library filter. Set ONLY if the user "
                "explicitly named one. Defaults are handled upstream."
            ),
            "properties": {
                "campus": {
                    "type": "string",
                    "enum": ["oxford", "hamilton", "middletown"],
                },
                "library": {
                    "type": "string",
                    "enum": [
                        "king",
                        "wertz",
                        "special",
                        "rentschler",
                        "gardner_harvey",
                        "sword",
                    ],
                },
            },
        },
    },
    "required": ["query"],
}

_VALIDATE_URL_SCHEMA = {
    "type": "object",
    "properties": {
        "url": {
            "type": "string",
            "description": "Full URL (with scheme) to verify exists in the corpus.",
        },
    },
    "required": ["url"],
}

_LOOKUP_LIBRARIAN_SCHEMA = {
    "type": "object",
    "properties": {
        "subject": {
            "type": "string",
            "description": "Subject area name (e.g. 'Biology', 'History').",
        },
        "name": {
            "type": "string",
            "description": "Librarian first or last name.",
        },
        "campus": {
            "type": "string",
            "enum": ["oxford", "hamilton", "middletown"],
        },
    },
    # Schema doesn't require any field, but the handler validates that
    # at least one is present. JSON Schema can't express "at least one
    # of" easily and the LLM is more forgiving when we tell it in prose
    # via the description.
    "description": (
        "Look up a subject librarian. Supply at least one filter; "
        "the bot does not return all librarians at once."
    ),
}

_LOOKUP_SPACE_SCHEMA = {
    "type": "object",
    "properties": {
        "library": {
            "type": "string",
            "enum": [
                "king",
                "wertz",
                "special",
                "rentschler",
                "gardner_harvey",
                "sword",
            ],
            "description": "Canonical library id.",
        },
        "name": {
            "type": "string",
            "description": (
                "Specific space name (e.g. 'MakerSpace', 'Group Study "
                "Room A', 'King 110')."
            ),
        },
    },
}

_GET_HOURS_SCHEMA = {
    "type": "object",
    "properties": {
        "library": {
            "type": "string",
            "enum": [
                "king",
                "wertz",
                "special",
                "rentschler",
                "gardner_harvey",
                "sword",
            ],
        },
    },
    "required": ["library"],
}

_GET_ROOM_AVAILABILITY_SCHEMA = {
    "type": "object",
    "properties": {
        "library": {
            "type": "string",
            "enum": [
                "king",
                "wertz",
                "rentschler",
                "gardner_harvey",
            ],
        },
        "date": {
            "type": "string",
            "description": "ISO date YYYY-MM-DD (in the library's local timezone).",
        },
        "capacity": {
            "type": "integer",
            "description": "Minimum capacity required.",
        },
        "equipment": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "Required equipment tags (e.g. ['whiteboard', 'monitor']). "
                "Match LibrarySpace.equipment[]."
            ),
        },
    },
    "required": ["library", "date"],
}

_BOOK_ROOM_SCHEMA = {
    "type": "object",
    "properties": {
        "room_id": {"type": "string"},
        "start": {
            "type": "string",
            "description": "ISO 8601 datetime in the library's local timezone.",
        },
        "end": {
            "type": "string",
            "description": "ISO 8601 datetime, after start.",
        },
        "user_email": {
            "type": "string",
            "description": "User's @miamioh.edu email for the booking.",
        },
    },
    "required": ["room_id", "start", "end", "user_email"],
}

_CREATE_TICKET_SCHEMA = {
    "type": "object",
    "properties": {
        "subject": {"type": "string"},
        "body": {
            "type": "string",
            "description": (
                "Question text plus relevant context. The librarian "
                "reads this verbatim -- include the conversation gist."
            ),
        },
        "user_email": {"type": "string"},
    },
    "required": ["subject", "body", "user_email"],
}

_HANDOFF_HUMAN_SCHEMA = {
    "type": "object",
    "properties": {
        "reason": {
            "type": "string",
            "description": (
                "One short sentence: why is the bot escalating? "
                "(e.g. 'Question requires account access', "
                "'No reliable answer in the corpus')."
            ),
        },
        "transcript_id": {
            "type": "string",
            "description": "Conversation id, if known.",
        },
    },
    "required": ["reason"],
}

_POINT_TO_URL_SCHEMA = {
    "type": "object",
    "properties": {
        "service": {
            "type": "string",
            "enum": ["ill", "account", "renewals", "course_reserves"],
            "description": (
                "Service the user must complete on the official system. "
                "The bot returns the URL; the bot does NOT perform the "
                "action."
            ),
        },
        "scope": {
            "type": "object",
            "description": (
                "Optional campus filter so ILL points to the right "
                "pickup-location form."
            ),
            "properties": {
                "campus": {
                    "type": "string",
                    "enum": ["oxford", "hamilton", "middletown"],
                },
            },
        },
    },
    "required": ["service"],
}


# --- Tool descriptions ----------------------------------------------------
#
# These go into the system prompt. Keep short -- every tool description
# is paid for once per turn (via the cached prefix, but still). Aim for
# under ~30 tokens each.

_DESCRIPTIONS = {
    "search_kb": (
        "Search the library knowledge base. Use for any question about "
        "policies, services, hours-overview, or location info. Returns "
        "passages with source URLs and metadata."
    ),
    "validate_url": (
        "Verify a URL exists in the live corpus before mentioning it. "
        "Use whenever you're about to cite a URL you didn't get from a "
        "tool result this turn."
    ),
    "lookup_librarian": (
        "Look up a subject librarian by subject area, name, or campus. "
        "Returns name, email, phone, photo URL."
    ),
    "lookup_space": (
        "Look up a library space (e.g. MakerSpace, Group Study Room A) "
        "for capacity, equipment, services_offered. Use for 'does X have "
        "Y' questions where Y is structured."
    ),
    "get_hours": (
        "Fetch live hours for a specific library building. Always live "
        "-- do NOT use search_kb for hours."
    ),
    "get_room_availability": (
        "Fetch live room booking availability for a library on a date. "
        "Optional capacity / equipment filters."
    ),
    "book_room": (
        "Book a room. ACTION TOOL: confirm with the user (room, time, "
        "email) before calling."
    ),
    "create_ticket": (
        "Open a LibAnswers ticket for the user's question. ACTION TOOL: "
        "confirm before calling."
    ),
    "handoff_human": (
        "Escalate to a human librarian via Ask Us. Use when the corpus "
        "has no reliable answer or the user explicitly asks for a person."
    ),
    "point_to_url": (
        "Return the canonical URL for a service the user must complete "
        "themselves on the official system (ILL, account ops, renewals, "
        "course reserves submission). DO NOT roleplay these systems."
    ),
}


# --- Build the registry --------------------------------------------------


def build_tool_registry(backends: ToolBackends) -> ToolRegistry:
    """Construct the full 10-tool registry for the agent.

    Caller (prod startup or test) provides the backends; this function
    wires every Tool with the right handler-factory and ships them
    back as a single registry.

    Pattern for adding a new tool: add a backend field to
    ToolBackends, write a `_make_<name>` handler factory, declare a
    `_<NAME>_SCHEMA`, add a `_DESCRIPTIONS[<name>]` entry, and one
    `registry.register(...)` line below. Five edits in one file.
    """
    registry = ToolRegistry()

    registry.register(
        Tool(
            name="search_kb",
            description=_DESCRIPTIONS["search_kb"],
            parameters=_SEARCH_KB_SCHEMA,
            handler=_make_search_kb(backends),
            is_read_only=True,
        )
    )
    registry.register(
        Tool(
            name="validate_url",
            description=_DESCRIPTIONS["validate_url"],
            parameters=_VALIDATE_URL_SCHEMA,
            handler=_make_validate_url(backends),
            is_read_only=True,
        )
    )
    registry.register(
        Tool(
            name="lookup_librarian",
            description=_DESCRIPTIONS["lookup_librarian"],
            parameters=_LOOKUP_LIBRARIAN_SCHEMA,
            handler=_make_lookup_librarian(backends),
            is_read_only=True,
        )
    )
    registry.register(
        Tool(
            name="lookup_space",
            description=_DESCRIPTIONS["lookup_space"],
            parameters=_LOOKUP_SPACE_SCHEMA,
            handler=_make_lookup_space(backends),
            is_read_only=True,
        )
    )
    registry.register(
        Tool(
            name="get_hours",
            description=_DESCRIPTIONS["get_hours"],
            parameters=_GET_HOURS_SCHEMA,
            handler=_make_get_hours(backends),
            is_read_only=True,
        )
    )
    registry.register(
        Tool(
            name="get_room_availability",
            description=_DESCRIPTIONS["get_room_availability"],
            parameters=_GET_ROOM_AVAILABILITY_SCHEMA,
            handler=_make_get_room_availability(backends),
            is_read_only=True,
        )
    )
    registry.register(
        Tool(
            name="book_room",
            description=_DESCRIPTIONS["book_room"],
            parameters=_BOOK_ROOM_SCHEMA,
            handler=_make_book_room(backends),
            is_read_only=False,
        )
    )
    registry.register(
        Tool(
            name="create_ticket",
            description=_DESCRIPTIONS["create_ticket"],
            parameters=_CREATE_TICKET_SCHEMA,
            handler=_make_create_ticket(backends),
            is_read_only=False,
        )
    )
    registry.register(
        Tool(
            name="handoff_human",
            description=_DESCRIPTIONS["handoff_human"],
            parameters=_HANDOFF_HUMAN_SCHEMA,
            handler=_make_handoff_human(backends),
            is_read_only=True,
        )
    )
    registry.register(
        Tool(
            name="point_to_url",
            description=_DESCRIPTIONS["point_to_url"],
            parameters=_POINT_TO_URL_SCHEMA,
            handler=_make_point_to_url(backends),
            is_read_only=True,
        )
    )

    return registry


__all__ = [
    "ToolBackends",
    "build_tool_registry",
]
