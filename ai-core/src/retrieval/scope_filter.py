"""
Build the Weaviate `where` filter from a Scope.

Pure logic. No Weaviate client, no I/O. Tests inject scope objects and
assert on the resulting filter dict, then prod sends that same dict to
the real client.

Filter rules (from playbook §8):
  - Campus: ALWAYS hard-filter to `scope.campus`. Cross-campus chunks
    are excluded unless the chunk is tagged `campus="all"` (university-
    wide content like Adobe licensing). The post-processor's cross-
    campus guard is a defense-in-depth check; this filter is the first
    line of defense.
  - Library: HARD filter when scope.library is set. Otherwise leave
    library unconstrained -- "what time does the library open" with
    no library named should return campus-wide content and let
    ranking surface the right building.
  - Featured-service boost: when the user's intent maps to a featured
    service (adobe_checkout, ill, makerspace, etc.), `featured_service`
    is added as a "should match" hint. This is a SOFT filter --
    chunks tagged with the matching service rank higher, but other
    chunks can still appear if they're a strong text match.
  - Deleted/tombstoned chunks always excluded.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ScopeFilter:
    """The resolved scope as the retriever needs it.

    Slimmer than the full Scope dataclass -- the retriever only cares
    about campus/library/featured_service. Build with from_scope() if
    you have a real Scope; build directly in tests.
    """

    campus: str
    library: Optional[str] = None
    featured_service: Optional[str] = None
    """Optional intent->service mapping (filled by the agent before
    calling search_kb). When set, retrieval boosts chunks tagged with
    this featured_service value."""


# --- Where-clause builders -----------------------------------------------
#
# We emit the v4-Python-client `Filter`-style dict so callers can pass
# it directly. The shape is:
#
#   {
#     "operator": "And",
#     "operands": [
#       {"path": ["campus"], "operator": "Equal", "valueText": "oxford"},
#       {"path": ["deleted"], "operator": "Equal", "valueBoolean": False},
#       ...
#     ]
#   }
#
# This nested dict shape is what `weaviate.classes.query.Filter` (v4)
# serializes to. The adapter in search.py calls the real client and is
# free to translate the dict into typed Filter objects -- the contract
# here is just "what filter do we want", not "how to talk to Weaviate".


def _eq_text(field: str, value: str) -> dict:
    return {"path": [field], "operator": "Equal", "valueText": value}


def _eq_bool(field: str, value: bool) -> dict:
    return {"path": [field], "operator": "Equal", "valueBoolean": value}


def _or(*operands: dict) -> dict:
    return {"operator": "Or", "operands": list(operands)}


def _and(*operands: dict) -> dict:
    if len(operands) == 1:
        return operands[0]
    return {"operator": "And", "operands": list(operands)}


def build_where_clause(scope: ScopeFilter) -> dict:
    """Build the hard-filter portion of a retrieval query.

    The result is what gets passed to Weaviate's `.with_where()` (v3)
    or `Filter.all_of(...)` (v4). Soft signals like featured_service
    boosting are NOT in here -- they go through `build_should_match()`
    so the retriever can apply them as a separate ranking nudge.

    Returns:
        Filter dict. Always non-empty (deleted=false at minimum).
    """
    clauses: list[dict] = [
        # Tombstoned / deleted chunks are never returned.
        _eq_bool("deleted", False),
        # Campus: chunk must be on the user's campus OR be tagged "all"
        # (university-wide content -- Adobe, NYT subscription, etc.).
        _or(
            _eq_text("campus", scope.campus),
            _eq_text("campus", "all"),
        ),
    ]

    # Library: hard-filter only if the user explicitly named one. A
    # null library means "any building on this campus" -- ranking
    # decides which surfaces. Same "all" escape hatch as campus.
    if scope.library is not None:
        clauses.append(
            _or(
                _eq_text("library", scope.library),
                _eq_text("library", "all"),
            )
        )

    return _and(*clauses)


def build_should_match(scope: ScopeFilter) -> Optional[dict]:
    """Build a soft "should match" filter that boosts chunks matching
    the user's resolved featured_service intent.

    The retriever applies this as a rank nudge, NOT a hard filter. A
    chunk that doesn't carry `featured_service=adobe_checkout` can
    still appear if its text is a strong match -- but a chunk that
    DOES carry that tag wins the tie.

    Returns None when the scope has no featured_service set; callers
    skip the should-match step entirely.
    """
    if scope.featured_service is None:
        return None
    return _eq_text("featured_service", scope.featured_service)


__all__ = [
    "ScopeFilter",
    "build_should_match",
    "build_where_clause",
]
