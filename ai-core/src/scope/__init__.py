"""Scope resolution: map a user message + session origin to a (campus, library) tuple.

See `Data preparation playbook §8` in the rebuild plan for the full spec.
"""

from src.scope.aliases import (
    CAMPUSES,
    LIBRARIES,
    CAMPUS_DISPLAY,
    LIBRARY_DISPLAY,
    LIBRARY_ALIASES,
    CAMPUS_ALIASES,
    Campus,
    Library,
)
from src.scope.resolver import (
    Scope,
    ScopeSource,
    resolve_scope,
    resolve_session_origin,
)

__all__ = [
    "CAMPUSES",
    "LIBRARIES",
    "CAMPUS_DISPLAY",
    "LIBRARY_DISPLAY",
    "LIBRARY_ALIASES",
    "CAMPUS_ALIASES",
    "Campus",
    "Library",
    "Scope",
    "ScopeSource",
    "resolve_scope",
    "resolve_session_origin",
]
