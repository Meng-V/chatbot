"""
Unit tests for WeaviateSearchAdapter.

Run: `python -m src.weaviate_adapters.test_search_adapter` from ai-core/.

The risky logic is the recursive scope-filter-dict -> v4 Filter
translation and the response-shape mapping. Both are tested with
fakes so no live Weaviate is needed.

Coverage:
  1. Translate a flat Equal(text) clause
  2. Translate a flat Equal(bool) clause
  3. Translate a nested And/Or tree (the real build_where_clause shape)
  4. Reject an Equal clause with no value
  5. Reject an unknown operator
  6. hybrid_search maps v4 response objects to the documented hit shape
  7. hybrid_search prefers the chunk_id PROPERTY over the object uuid
  8. hybrid_search returns [] on client error (never crashes the turn)
  9. hybrid_search tolerates missing metadata / missing properties
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
_AI_CORE = _HERE.parent.parent
sys.path.insert(0, str(_AI_CORE))

from src.weaviate_adapters.search_adapter import (  # noqa: E402
    WeaviateSearchAdapter,
    _translate_filter_with,
)
from src.retrieval.scope_filter import (  # noqa: E402
    ScopeFilter,
    build_where_clause,
)


# --- Fake v4 Filter -----------------------------------------------------


class _FakeFilterExpr:
    """Records what filter expression got built so tests can assert."""
    def __init__(self, kind: str, **kw: Any):
        self.kind = kind
        self.kw = kw

    def __repr__(self) -> str:
        return f"Filter({self.kind}, {self.kw})"


class _FakeProp:
    def __init__(self, name: str):
        self.name = name

    def equal(self, value: Any) -> _FakeFilterExpr:
        return _FakeFilterExpr("equal", path=self.name, value=value)


class FakeFilter:
    @staticmethod
    def by_property(name: str) -> _FakeProp:
        return _FakeProp(name)

    @staticmethod
    def all_of(operands: list) -> _FakeFilterExpr:
        return _FakeFilterExpr("all_of", operands=operands)

    @staticmethod
    def any_of(operands: list) -> _FakeFilterExpr:
        return _FakeFilterExpr("any_of", operands=operands)


# --- Fake v4 query client -----------------------------------------------


class _FakeMeta:
    def __init__(self, score: Any):
        self.score = score


class _FakeObj:
    def __init__(self, uuid: str, properties: dict, score: Any = 0.5):
        self.uuid = uuid
        self.properties = properties
        self.metadata = _FakeMeta(score)


class _FakeResp:
    def __init__(self, objects: list):
        self.objects = objects


class _FakeQuery:
    def __init__(self, resp: _FakeResp, raises: bool = False):
        self._resp = resp
        self._raises = raises
        self.last_call: dict = {}

    def hybrid(self, **kw: Any) -> _FakeResp:
        self.last_call = kw
        if self._raises:
            raise RuntimeError("simulated weaviate error")
        return self._resp


class _FakeCollection:
    def __init__(self, query: _FakeQuery):
        self.query = query


class _FakeCollections:
    def __init__(self, collection: _FakeCollection):
        self._c = collection

    def get(self, name: str) -> _FakeCollection:
        return self._c


class _FakeClient:
    def __init__(self, resp: _FakeResp, raises: bool = False):
        q = _FakeQuery(resp, raises=raises)
        self._q = q
        self.collections = _FakeCollections(_FakeCollection(q))


# --- Filter translation tests -------------------------------------------


def test_translate_equal_text() -> None:
    out = _translate_filter_with(
        {"path": ["campus"], "operator": "Equal", "valueText": "oxford"},
        FakeFilter,
    )
    assert out.kind == "equal"
    assert out.kw == {"path": "campus", "value": "oxford"}


def test_translate_equal_bool() -> None:
    out = _translate_filter_with(
        {"path": ["deleted"], "operator": "Equal", "valueBoolean": False},
        FakeFilter,
    )
    assert out.kind == "equal"
    assert out.kw == {"path": "deleted", "value": False}


def test_translate_real_where_clause_shape() -> None:
    """The actual build_where_clause output for a scoped query:
    And(deleted=false, Or(campus=oxford, campus=all),
        Or(library=king, library=all))."""
    where = build_where_clause(
        ScopeFilter(campus="oxford", library="king")
    )
    out = _translate_filter_with(where, FakeFilter)
    # Top level is an And (all_of).
    assert out.kind == "all_of"
    operands = out.kw["operands"]
    # deleted=false + 2 Or-groups (campus, library)
    assert len(operands) == 3
    assert operands[0].kind == "equal"
    assert operands[0].kw == {"path": "deleted", "value": False}
    assert operands[1].kind == "any_of"  # campus Or
    assert operands[2].kind == "any_of"  # library Or


def test_translate_no_library_clause_when_library_none() -> None:
    where = build_where_clause(ScopeFilter(campus="hamilton"))
    out = _translate_filter_with(where, FakeFilter)
    assert out.kind == "all_of"
    # deleted + campus-Or only; no library clause
    assert len(out.kw["operands"]) == 2


def test_translate_rejects_equal_without_value() -> None:
    try:
        _translate_filter_with(
            {"path": ["x"], "operator": "Equal"}, FakeFilter,
        )
    except ValueError as e:
        assert "value" in str(e).lower()
        return
    raise AssertionError("expected ValueError")


def test_translate_rejects_unknown_operator() -> None:
    try:
        _translate_filter_with(
            {"operator": "NotARealOp", "operands": []}, FakeFilter,
        )
    except ValueError as e:
        assert "unsupported" in str(e).lower()
        return
    raise AssertionError("expected ValueError")


# --- hybrid_search response mapping -------------------------------------


def _adapter_with(objects: list, raises: bool = False) -> WeaviateSearchAdapter:
    return WeaviateSearchAdapter(client=_FakeClient(_FakeResp(objects), raises=raises))


def test_hybrid_search_maps_documented_shape() -> None:
    obj = _FakeObj(
        uuid="00000000-0000-0000-0000-000000000001",
        properties={
            "chunk_id": "c-abc123",
            "source_url": "https://lib.miamioh.edu/use/technology/printing/",
            "text": "Printing how-to.",
            "campus": "oxford",
            "library": "king",
            "topic": "technology",
            "featured_service": "",
        },
        score=0.87,
    )
    a = _adapter_with([obj])
    hits = a.hybrid_search(
        collection="Chunk_v1", query="how do I print",
        where=build_where_clause(ScopeFilter(campus="oxford")),
        alpha=0.5, limit=5,
    )
    assert len(hits) == 1
    h = hits[0]
    assert h["chunk_id"] == "c-abc123"
    assert h["source_url"].endswith("/printing/")
    assert h["text"] == "Printing how-to."
    assert h["campus"] == "oxford"
    assert h["library"] == "king"
    assert h["topic"] == "technology"
    assert h["featured_service"] is None  # "" coerced to None
    assert h["score"] == 0.87


def test_hybrid_search_prefers_chunk_id_property_over_uuid() -> None:
    """The ETL stores the real chunk_id as a property; the object uuid
    is a uuid5 hash. Retrieval must surface the property so citations
    join back to ChunkProvenance."""
    obj = _FakeObj(
        uuid="ffffffff-1111-2222-3333-444444444444",
        properties={"chunk_id": "c-real-id", "source_url": "u", "text": "t"},
    )
    hits = _adapter_with([obj]).hybrid_search(
        collection="C", query="q", where={}, alpha=0.5, limit=1,
    )
    assert hits[0]["chunk_id"] == "c-real-id"


def test_hybrid_search_falls_back_to_uuid_if_no_chunk_id_prop() -> None:
    obj = _FakeObj(uuid="the-uuid", properties={"source_url": "u", "text": "t"})
    hits = _adapter_with([obj]).hybrid_search(
        collection="C", query="q", where={}, alpha=0.5, limit=1,
    )
    assert hits[0]["chunk_id"] == "the-uuid"


def test_hybrid_search_returns_empty_on_client_error() -> None:
    """Retrieval hiccup must NOT crash the turn -- empty list, the
    agent refuses via NO_RESULTS."""
    hits = _adapter_with([], raises=True).hybrid_search(
        collection="C", query="q", where={}, alpha=0.5, limit=5,
    )
    assert hits == []


def test_hybrid_search_tolerates_missing_metadata_and_props() -> None:
    class _Bare:
        uuid = "u1"
        properties = {}
        metadata = None
    hits = _adapter_with([_Bare()]).hybrid_search(
        collection="C", query="q", where={}, alpha=0.5, limit=1,
    )
    assert hits[0]["chunk_id"] == "u1"
    assert hits[0]["score"] == 0.0
    assert hits[0]["source_url"] == ""


def test_hybrid_search_passes_alpha_and_limit_through() -> None:
    a = _adapter_with([])
    a.hybrid_search(
        collection="C", query="q", where={}, alpha=0.25, limit=7,
    )
    call = a.client._q.last_call
    assert call["alpha"] == 0.25
    assert call["limit"] == 7
    assert call["query"] == "q"


def main() -> int:
    tests = [
        test_translate_equal_text,
        test_translate_equal_bool,
        test_translate_real_where_clause_shape,
        test_translate_no_library_clause_when_library_none,
        test_translate_rejects_equal_without_value,
        test_translate_rejects_unknown_operator,
        test_hybrid_search_maps_documented_shape,
        test_hybrid_search_prefers_chunk_id_property_over_uuid,
        test_hybrid_search_falls_back_to_uuid_if_no_chunk_id_prop,
        test_hybrid_search_returns_empty_on_client_error,
        test_hybrid_search_tolerates_missing_metadata_and_props,
        test_hybrid_search_passes_alpha_and_limit_through,
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
