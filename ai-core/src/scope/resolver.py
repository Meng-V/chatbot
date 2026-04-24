"""
Resolve a user message + session origin into a Scope object.

A Scope is the (campus, library) tuple every retrieval call carries.
Without a scope, retrieval cannot enforce the cross-campus refusal that
prevents King's hours being served as Hamilton's hours.

See plan: Data preparation playbook §8 -- Campus and library scope resolution.

================================================================================
ALGORITHM (one pass per user message)
================================================================================

1. Substring-match the lowercased user message against LIBRARY_ALIASES.
   Use longest-match-wins so "Art and Architecture Library" beats "Art".
2. If a library matched -> set scope.library + derive scope.campus from it.
3. Otherwise, substring-match against CAMPUS_ALIASES. If matched, set
   scope.campus only (library stays null -- "all libraries on this campus").
4. Otherwise, fall back to the session_origin campus (regional widget user).
5. Otherwise, default to ("oxford", None).

The matcher is intentionally simple. We do NOT use the LLM for scope
detection -- it would add latency and cost on every turn, and the failure
mode (LLM picks the wrong campus) is exactly the failure mode we're trying
to engineer out. Keep it deterministic.
"""

from dataclasses import dataclass
from typing import Literal, Optional
from urllib.parse import urlparse

from src.scope.aliases import (
    CAMPUS_ALIASES,
    CAMPUS_DISPLAY,
    Campus,
    DOMAIN_TO_CAMPUS,
    LIBRARY_ALIASES,
    LIBRARY_DISPLAY,
    LIBRARY_TO_CAMPUS,
    Library,
)


ScopeSource = Literal["library_alias", "campus_alias", "session_origin", "default"]
"""Where the resolved scope came from -- logged so we can audit how often
defaults fire vs explicit signals."""


@dataclass(frozen=True)
class Scope:
    """The resolved retrieval scope for a single user turn.

    Every retrieval call (`search_kb(query, scope)`) carries this. The
    Weaviate query gets `where: {campus: scope.campus}` always, plus
    `library: scope.library OR "all"` when `scope.library` is set.
    """

    campus: Campus
    library: Optional[Library]
    source: ScopeSource

    @property
    def campus_display(self) -> str:
        return CAMPUS_DISPLAY[self.campus]

    @property
    def library_display(self) -> Optional[str]:
        return LIBRARY_DISPLAY[self.library] if self.library else None

    @property
    def is_explicit(self) -> bool:
        """True if the user gave a clear scope signal (vs default fallback)."""
        return self.source in ("library_alias", "campus_alias")

    def as_filter(self) -> dict:
        """Serialize to the dict shape the retriever expects."""
        return {
            "campus": self.campus,
            "library": self.library,
            "source": self.source,
        }


def _longest_alias_match(haystack: str, alias_table: dict[str, object]) -> Optional[str]:
    """Return the longest alias that appears as a substring of haystack, or None.

    Both `haystack` and table keys must already be lowercased.

    O(n*m) scan -- fine for our ~50 aliases. Premature optimization here
    (Aho-Corasick, trie) hurts readability and has no measurable effect.
    """
    best: Optional[str] = None
    for alias in alias_table:
        if alias in haystack and (best is None or len(alias) > len(best)):
            best = alias
    return best


def resolve_session_origin(origin_url: Optional[str]) -> Optional[Campus]:
    """Extract a campus from a Socket.IO/HTTP `Origin` header URL.

    Returns None if the origin is unknown or malformed -- caller falls
    back to the Oxford default.
    """
    if not origin_url:
        return None
    try:
        host = urlparse(origin_url).hostname
    except (ValueError, AttributeError):
        return None
    if host is None:
        return None
    return DOMAIN_TO_CAMPUS.get(host.lower())


def resolve_scope(
    user_message: str,
    session_origin_campus: Optional[Campus] = None,
) -> Scope:
    """Resolve a user message + session origin into a Scope.

    Args:
        user_message: Raw user text. Empty string is allowed (defaults fire).
        session_origin_campus: Campus inferred from the chat widget's host
            at connect time. Pre-resolve via `resolve_session_origin()` so
            this function doesn't need to know about URLs.

    Returns:
        A Scope. Never None.

    Examples:
        >>> resolve_scope("when does Wertz close tonight?")
        Scope(campus='oxford', library='wertz', source='library_alias')

        >>> resolve_scope("hours at the hamilton campus library")
        Scope(campus='hamilton', library='rentschler', source='library_alias')

        >>> resolve_scope("can I print here?")
        Scope(campus='oxford', library=None, source='default')

        >>> resolve_scope("can I print here?", session_origin_campus="middletown")
        Scope(campus='middletown', library=None, source='session_origin')
    """
    haystack = (user_message or "").lower()

    # 1. Library alias (most specific)
    lib_match = _longest_alias_match(haystack, LIBRARY_ALIASES)
    if lib_match is not None:
        library: Library = LIBRARY_ALIASES[lib_match]
        lib_campus = LIBRARY_TO_CAMPUS[library]

        # Cross-check: if the user ALSO named a different campus
        # explicitly ("Where are special collections at Hamilton?"),
        # the campus signal wins. The library name is then a service
        # mention, not a building selection -- the synthesizer's
        # services_offered truth table will refuse appropriately.
        campus_match = _longest_alias_match(haystack, CAMPUS_ALIASES)
        if campus_match is not None:
            campus_from_alias = CAMPUS_ALIASES[campus_match]
            if campus_from_alias != lib_campus:
                return Scope(
                    campus=campus_from_alias,
                    library=None,
                    source="campus_alias",
                )

        return Scope(
            campus=lib_campus,
            library=library,
            source="library_alias",
        )

    # 2. Campus alias (no library narrow-down)
    campus_match = _longest_alias_match(haystack, CAMPUS_ALIASES)
    if campus_match is not None:
        return Scope(
            campus=CAMPUS_ALIASES[campus_match],
            library=None,
            source="campus_alias",
        )

    # 3. Session origin (regional-campus widget user)
    if session_origin_campus is not None:
        return Scope(
            campus=session_origin_campus,
            library=None,
            source="session_origin",
        )

    # 4. Default: Oxford, no specific library
    return Scope(campus="oxford", library=None, source="default")
