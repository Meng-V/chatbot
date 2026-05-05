"""
Unit tests for the Weaviate where-clause builder.

Run: `python -m src.retrieval.test_scope_filter` from ai-core/.

The where-clause is the FIRST line of defense against cross-campus
leaks. The post-processor's cross-campus check is defense-in-depth;
this filter is what stops Hamilton chunks from being seen by an Oxford
query at all. Every clause must be load-bearing-tested.

Tests:
  1. Default Oxford scope: filters deleted=false AND (campus=oxford OR campus=all).
  2. Hamilton scope: same shape, campus=hamilton.
  3. Library set: adds (library=X OR library=all) clause.
  4. Library unset: no library clause.
  5. featured_service: build_should_match returns the hint dict.
  6. featured_service unset: build_should_match returns None.
  7. ScopeFilter dataclass shape preserved.
  8. campus=all alternative path: a chunk tagged "all" passes both
     the campus filter (via OR) and any library filter (via OR).
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running from ai-core/ as `python -m src.retrieval.test_scope_filter`.
_HERE = Path(__file__).resolve().parent
_AI_CORE = _HERE.parent.parent
sys.path.insert(0, str(_AI_CORE))

from src.retrieval.scope_filter import (  # noqa: E402
    ScopeFilter,
    build_should_match,
    build_where_clause,
)


def _operands(clause: dict) -> list[dict]:
    return clause.get("operands", [])


def _flatten_clauses(clause: dict) -> list[dict]:
    """Walk the And/Or tree and yield leaf {path, operator, valueX} dicts."""
    if "operator" in clause and clause["operator"] in ("And", "Or"):
        out = []
        for c in clause["operands"]:
            out.extend(_flatten_clauses(c))
        return out
    return [clause]


def test_default_oxford_scope_filters_campus_and_deleted() -> None:
    scope = ScopeFilter(campus="oxford")
    clause = build_where_clause(scope)
    assert clause["operator"] == "And"
    leaves = _flatten_clauses(clause)
    # Must include deleted=false.
    assert any(
        l.get("path") == ["deleted"] and l.get("valueBoolean") is False
        for l in leaves
    )
    # Must include campus=oxford.
    assert any(
        l.get("path") == ["campus"] and l.get("valueText") == "oxford"
        for l in leaves
    )
    # Must allow campus=all (university-wide chunks).
    assert any(
        l.get("path") == ["campus"] and l.get("valueText") == "all"
        for l in leaves
    )


def test_hamilton_scope_swaps_campus() -> None:
    scope = ScopeFilter(campus="hamilton")
    clause = build_where_clause(scope)
    leaves = _flatten_clauses(clause)
    assert any(l.get("valueText") == "hamilton" for l in leaves)
    assert not any(l.get("valueText") == "oxford" for l in leaves)


def test_library_set_adds_library_clause() -> None:
    scope = ScopeFilter(campus="oxford", library="king")
    clause = build_where_clause(scope)
    leaves = _flatten_clauses(clause)
    library_leaves = [l for l in leaves if l.get("path") == ["library"]]
    # Both library=king and library=all must be present (OR).
    values = {l["valueText"] for l in library_leaves}
    assert values == {"king", "all"}


def test_library_unset_omits_library_clause() -> None:
    scope = ScopeFilter(campus="oxford", library=None)
    clause = build_where_clause(scope)
    leaves = _flatten_clauses(clause)
    assert not any(l.get("path") == ["library"] for l in leaves)


def test_should_match_returns_featured_service_when_set() -> None:
    scope = ScopeFilter(campus="oxford", featured_service="adobe_checkout")
    sm = build_should_match(scope)
    assert sm is not None
    assert sm["path"] == ["featured_service"]
    assert sm["valueText"] == "adobe_checkout"


def test_should_match_returns_none_when_unset() -> None:
    scope = ScopeFilter(campus="oxford", featured_service=None)
    assert build_should_match(scope) is None


def test_scope_filter_immutable() -> None:
    """ScopeFilter is frozen; mutating raises. Prevents bugs where
    a downstream caller modifies the scope mid-request."""
    scope = ScopeFilter(campus="oxford")
    try:
        scope.campus = "hamilton"  # type: ignore[misc]
    except Exception:
        return
    raise AssertionError("expected frozen dataclass to refuse mutation")


def test_filter_structure_is_and_or_nested() -> None:
    """The output is an And node whose operands include Or nodes for
    campus (and library when set). Sanity-check the structural shape
    so downstream adapter translation has stable input."""
    scope = ScopeFilter(campus="oxford", library="king")
    clause = build_where_clause(scope)
    assert clause["operator"] == "And"
    # Look for at least two Or sub-clauses (one per text-field
    # OR-with-all): campus and library.
    or_nodes = [op for op in clause["operands"] if op.get("operator") == "Or"]
    assert len(or_nodes) >= 2


def main() -> int:
    tests = [
        test_default_oxford_scope_filters_campus_and_deleted,
        test_hamilton_scope_swaps_campus,
        test_library_set_adds_library_clause,
        test_library_unset_omits_library_clause,
        test_should_match_returns_featured_service_when_set,
        test_should_match_returns_none_when_unset,
        test_scope_filter_immutable,
        test_filter_structure_is_and_or_nested,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
        except Exception as e:
            failed += 1
            print(f"ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
