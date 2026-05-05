"""
Unit tests for the search_kb retrieval entrypoint.

Run: `python -m src.retrieval.test_search` from ai-core/.

Tests use a stub WeaviateLike that returns canned hits, so the
retrieval logic is fully testable without the real Weaviate client.

Tests:
  1. Happy path: hits translate to EvidenceChunks with all metadata.
  2. Malformed hit (missing required field) is dropped silently;
     raw_hit_count > len(chunks) signals the gap to debugger.
  3. Weaviate raises -> RetrievalResult with error set, chunks=[].
  4. Empty hits -> chunks=[], no error.
  5. Featured-service soft boost: matching hits move to the front,
     within-tier order preserved (stable sort).
  6. Featured-service unset -> chunks come back in Weaviate order.
  7. The where filter passed to Weaviate matches build_where_clause.
  8. used_filter is recorded on the result for forensic replay.
  9. used_filter is recorded EVEN when retrieval errored.
 10. score is coerced to float (defends against int/string from
     adapter bugs).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

# Allow running from ai-core/ as `python -m src.retrieval.test_search`.
_HERE = Path(__file__).resolve().parent
_AI_CORE = _HERE.parent.parent
sys.path.insert(0, str(_AI_CORE))

from src.retrieval.scope_filter import ScopeFilter  # noqa: E402
from src.retrieval.search import (  # noqa: E402
    RetrievalRequest,
    RetrievalResult,
    search_kb,
)


# --- Stub adapter --------------------------------------------------------


class StubWeaviate:
    """Records what was asked + returns the configured response."""

    def __init__(
        self,
        *,
        hits: Optional[list[dict]] = None,
        raises: Optional[Exception] = None,
    ):
        self.hits = hits or []
        self.raises = raises
        self.calls: list[dict] = []

    def hybrid_search(self, **kwargs):
        self.calls.append(kwargs)
        if self.raises is not None:
            raise self.raises
        return list(self.hits)


def _hit(
    chunk_id: str = "c1",
    source_url: str = "https://lib.miamioh.edu/king/",
    text: str = "King opens 7am.",
    campus: str = "oxford",
    library: str = "king",
    topic: Optional[str] = "hours",
    featured_service: Optional[str] = None,
    score: float = 0.9,
) -> dict:
    return {
        "chunk_id": chunk_id,
        "source_url": source_url,
        "text": text,
        "campus": campus,
        "library": library,
        "topic": topic,
        "featured_service": featured_service,
        "score": score,
    }


# --- Tests ---------------------------------------------------------------


def test_happy_path_translates_hits() -> None:
    stub = StubWeaviate(hits=[_hit()])
    req = RetrievalRequest(query="when does King close", scope=ScopeFilter(campus="oxford"))
    out = search_kb(req, weaviate=stub)
    assert out.error is None
    assert out.raw_hit_count == 1
    assert len(out.chunks) == 1
    c = out.chunks[0]
    assert c.chunk_id == "c1"
    assert c.source_url == "https://lib.miamioh.edu/king/"
    assert c.campus == "oxford"
    assert c.library == "king"
    assert c.score == 0.9


def test_malformed_hit_dropped_silently() -> None:
    """A hit missing chunk_id (or source_url, or text) is dropped, but
    raw_hit_count counts it. Lets us see in logs that 'we got 5 hits
    but only 3 became chunks' = 2 malformed -- adapter bug to chase."""
    stub = StubWeaviate(hits=[
        _hit(chunk_id="c1"),
        {"source_url": "https://x", "text": "..."},  # missing chunk_id
        _hit(chunk_id="c3"),
    ])
    req = RetrievalRequest(query="q", scope=ScopeFilter(campus="oxford"))
    out = search_kb(req, weaviate=stub)
    assert out.raw_hit_count == 3
    assert len(out.chunks) == 2
    assert [c.chunk_id for c in out.chunks] == ["c1", "c3"]


def test_weaviate_raises_returns_error_result() -> None:
    stub = StubWeaviate(raises=ConnectionError("Weaviate down"))
    req = RetrievalRequest(query="q", scope=ScopeFilter(campus="oxford"))
    out = search_kb(req, weaviate=stub)
    assert out.error is not None
    assert "ConnectionError" in out.error
    assert "Weaviate down" in out.error
    assert out.chunks == []
    assert out.raw_hit_count == 0


def test_empty_hits_no_error() -> None:
    stub = StubWeaviate(hits=[])
    req = RetrievalRequest(query="q", scope=ScopeFilter(campus="oxford"))
    out = search_kb(req, weaviate=stub)
    assert out.error is None
    assert out.chunks == []
    assert out.raw_hit_count == 0


def test_featured_service_boost_reorders() -> None:
    """A non-matching chunk with higher hybrid score gets BEHIND a
    matching chunk with lower score -- that's the soft-boost design."""
    stub = StubWeaviate(hits=[
        # Higher hybrid score, but not adobe_checkout -> should drop behind.
        _hit(chunk_id="c1", featured_service=None, score=0.95),
        # Lower hybrid score but matching service -> should win.
        _hit(chunk_id="c2", featured_service="adobe_checkout", score=0.7),
        _hit(chunk_id="c3", featured_service=None, score=0.6),
    ])
    req = RetrievalRequest(
        query="how do I get Photoshop",
        scope=ScopeFilter(campus="oxford", featured_service="adobe_checkout"),
    )
    out = search_kb(req, weaviate=stub)
    assert [c.chunk_id for c in out.chunks] == ["c2", "c1", "c3"]


def test_featured_service_boost_stable_within_tier() -> None:
    """Within the matching tier, original hybrid order is preserved.
    Within the non-matching tier, same."""
    stub = StubWeaviate(hits=[
        _hit(chunk_id="c1", featured_service=None, score=0.9),
        _hit(chunk_id="c2", featured_service="adobe_checkout", score=0.8),
        _hit(chunk_id="c3", featured_service="adobe_checkout", score=0.6),
        _hit(chunk_id="c4", featured_service=None, score=0.5),
    ])
    req = RetrievalRequest(
        query="q", scope=ScopeFilter(campus="oxford", featured_service="adobe_checkout"),
    )
    out = search_kb(req, weaviate=stub)
    # Matching tier (c2, c3) by score desc; non-matching (c1, c4) by score desc.
    assert [c.chunk_id for c in out.chunks] == ["c2", "c3", "c1", "c4"]


def test_no_featured_service_preserves_hybrid_order() -> None:
    stub = StubWeaviate(hits=[
        _hit(chunk_id="c1", score=0.9),
        _hit(chunk_id="c2", score=0.8),
        _hit(chunk_id="c3", score=0.7),
    ])
    req = RetrievalRequest(query="q", scope=ScopeFilter(campus="oxford"))
    out = search_kb(req, weaviate=stub)
    assert [c.chunk_id for c in out.chunks] == ["c1", "c2", "c3"]


def test_where_filter_passed_to_weaviate() -> None:
    stub = StubWeaviate(hits=[])
    req = RetrievalRequest(
        query="q", scope=ScopeFilter(campus="hamilton", library="rentschler"),
    )
    search_kb(req, weaviate=stub)
    assert len(stub.calls) == 1
    where = stub.calls[0]["where"]
    # Walk to find campus=hamilton.
    text = repr(where)
    assert "hamilton" in text
    assert "rentschler" in text
    assert "deleted" in text


def test_used_filter_recorded_on_success() -> None:
    stub = StubWeaviate(hits=[_hit()])
    req = RetrievalRequest(query="q", scope=ScopeFilter(campus="oxford"))
    out = search_kb(req, weaviate=stub)
    assert out.used_filter is not None
    assert "operator" in out.used_filter


def test_used_filter_recorded_even_on_error() -> None:
    """When Weaviate errors, the filter we WOULD have used is still
    recorded -- helps debug 'why did this query fail'."""
    stub = StubWeaviate(raises=RuntimeError("boom"))
    req = RetrievalRequest(query="q", scope=ScopeFilter(campus="oxford"))
    out = search_kb(req, weaviate=stub)
    assert out.error is not None
    assert out.used_filter is not None


def test_score_coerced_to_float() -> None:
    """If the adapter returns int (or string), we coerce to float so
    downstream sorting/eval doesn't blow up on type mismatch."""
    stub = StubWeaviate(hits=[
        {**_hit(chunk_id="c1"), "score": 1},  # int
        {**_hit(chunk_id="c2"), "score": "0.5"},  # string (defensive)
    ])
    req = RetrievalRequest(query="q", scope=ScopeFilter(campus="oxford"))
    out = search_kb(req, weaviate=stub)
    for c in out.chunks:
        assert isinstance(c.score, float)


def test_alpha_passed_through() -> None:
    """alpha (BM25 vs vector blend) reaches the adapter unchanged."""
    stub = StubWeaviate(hits=[])
    req = RetrievalRequest(query="q", scope=ScopeFilter(campus="oxford"), alpha=0.75)
    search_kb(req, weaviate=stub)
    assert stub.calls[0]["alpha"] == 0.75


def test_k_passed_through_as_limit() -> None:
    stub = StubWeaviate(hits=[])
    req = RetrievalRequest(query="q", scope=ScopeFilter(campus="oxford"), k=20)
    search_kb(req, weaviate=stub)
    assert stub.calls[0]["limit"] == 20


def main() -> int:
    tests = [
        test_happy_path_translates_hits,
        test_malformed_hit_dropped_silently,
        test_weaviate_raises_returns_error_result,
        test_empty_hits_no_error,
        test_featured_service_boost_reorders,
        test_featured_service_boost_stable_within_tier,
        test_no_featured_service_preserves_hybrid_order,
        test_where_filter_passed_to_weaviate,
        test_used_filter_recorded_on_success,
        test_used_filter_recorded_even_on_error,
        test_score_coerced_to_float,
        test_alpha_passed_through,
        test_k_passed_through_as_limit,
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
