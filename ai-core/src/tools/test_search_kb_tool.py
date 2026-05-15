"""
Unit tests for the search_kb tool wrapper.

Run: `python -m src.tools.test_search_kb_tool` from ai-core/.

The wrapper is what the LLM calls; it converts the raw RetrievalResult
into the shape the LLM and synthesizer expect, and binds the per-
request scope so the LLM doesn't have to (or can't) override it.

Tests:
  1. Tool factory returns a Tool with correct name + read_only=True.
  2. Calling with a valid query dispatches to search_kb and returns
     evidence in the documented shape.
  3. evidence[].n is 1-indexed and matches the citation numbering
     the synthesizer will emit.
  4. Empty query raises ToolError (LLM forgot to fill the field).
  5. k out of range raises ToolError (LLM passed k=10000).
  6. intent -> featured_service mapping fires the soft boost.
  7. intent=None or unknown intent skips the boost.
  8. WeaviateLike adapter receives the right collection name.
  9. error result from search_kb passes through to the tool result
     with `error` field set.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

# Allow running from ai-core/ as `python -m src.tools.test_search_kb_tool`.
_HERE = Path(__file__).resolve().parent
_AI_CORE = _HERE.parent.parent
sys.path.insert(0, str(_AI_CORE))

from src.agent.tool_registry import ToolError  # noqa: E402
from src.retrieval.scope_filter import ScopeFilter  # noqa: E402
from src.tools.search_kb_tool import make_search_kb_tool  # noqa: E402


class StubWeaviate:
    def __init__(self, hits=None, raises=None):
        self.hits = hits or []
        self.raises = raises
        self.calls = []

    def hybrid_search(self, **kwargs):
        self.calls.append(kwargs)
        if self.raises is not None:
            raise self.raises
        return list(self.hits)


def _hit(chunk_id="c1", source_url="https://lib/", text="snip", **kw):
    return {
        "chunk_id": chunk_id, "source_url": source_url, "text": text,
        "campus": kw.get("campus", "oxford"),
        "library": kw.get("library", "king"),
        "topic": kw.get("topic"),
        "featured_service": kw.get("featured_service"),
        "score": kw.get("score", 0.5),
    }


# --- Tests ---------------------------------------------------------------


def test_factory_returns_correct_tool_metadata() -> None:
    tool = make_search_kb_tool(
        weaviate=StubWeaviate(), scope=ScopeFilter(campus="oxford"),
    )
    assert tool.name == "search_kb"
    assert tool.is_read_only is True
    assert "query" in tool.parameters["properties"]
    assert "k" in tool.parameters["properties"]
    assert tool.parameters["required"] == ["query"]


def test_handler_dispatches_and_shapes_result() -> None:
    stub = StubWeaviate(hits=[_hit("c1"), _hit("c2", score=0.4)])
    tool = make_search_kb_tool(
        weaviate=stub, scope=ScopeFilter(campus="oxford"),
    )
    result = tool.handler({"query": "when does king close"})
    assert "evidence" in result
    assert "error" not in result
    assert len(result["evidence"]) == 2
    e = result["evidence"][0]
    # 1-indexed numbering matches synthesizer citation [n] convention.
    assert e["n"] == 1
    assert result["evidence"][1]["n"] == 2
    # Each evidence row carries provenance + scope metadata.
    assert e["chunk_id"] == "c1"
    assert e["source_url"] == "https://lib/"
    assert e["library"] == "king"
    assert e["campus"] == "oxford"


def test_empty_query_raises_tool_error() -> None:
    tool = make_search_kb_tool(
        weaviate=StubWeaviate(), scope=ScopeFilter(campus="oxford"),
    )
    for bad in [{"query": ""}, {"query": "   "}, {}]:
        try:
            tool.handler(bad)
        except ToolError as e:
            assert "query" in str(e).lower()
            continue
        raise AssertionError(f"expected ToolError for {bad!r}")


def test_k_out_of_range_raises() -> None:
    tool = make_search_kb_tool(
        weaviate=StubWeaviate(), scope=ScopeFilter(campus="oxford"),
    )
    for bad_k in [0, -1, 51, 10000]:
        try:
            tool.handler({"query": "q", "k": bad_k})
        except ToolError as e:
            assert "out of range" in str(e)
            continue
        raise AssertionError(f"expected ToolError for k={bad_k}")


def test_k_in_range_accepted() -> None:
    stub = StubWeaviate(hits=[_hit()])
    tool = make_search_kb_tool(
        weaviate=stub, scope=ScopeFilter(campus="oxford"),
    )
    tool.handler({"query": "q", "k": 25})
    assert stub.calls[0]["limit"] == 25


def test_intent_maps_to_featured_service_boost() -> None:
    """When intent='adobe_access', a chunk tagged adobe_checkout
    should win against an unflagged chunk with higher hybrid score.
    Verifies the intent->service mapping is wired correctly."""
    stub = StubWeaviate(hits=[
        _hit("c1", featured_service=None, score=0.9),
        _hit("c2", featured_service="adobe_checkout", score=0.6),
    ])
    tool = make_search_kb_tool(
        weaviate=stub,
        scope=ScopeFilter(campus="oxford"),
        intent="adobe_access",
    )
    result = tool.handler({"query": "where is photoshop"})
    assert result["evidence"][0]["chunk_id"] == "c2"
    assert result["evidence"][1]["chunk_id"] == "c1"


def test_unknown_intent_skips_boost() -> None:
    """An intent that has no featured_service mapping ('hours',
    'human_handoff') means no soft boost -- chunks come back in
    Weaviate hybrid order."""
    stub = StubWeaviate(hits=[
        _hit("c1", featured_service=None, score=0.9),
        _hit("c2", featured_service="adobe_checkout", score=0.6),
    ])
    tool = make_search_kb_tool(
        weaviate=stub,
        scope=ScopeFilter(campus="oxford"),
        intent="hours",  # no mapping
    )
    result = tool.handler({"query": "q"})
    assert result["evidence"][0]["chunk_id"] == "c1"


def test_intent_none_skips_boost() -> None:
    stub = StubWeaviate(hits=[
        _hit("c1", featured_service=None, score=0.9),
        _hit("c2", featured_service="adobe_checkout", score=0.6),
    ])
    tool = make_search_kb_tool(
        weaviate=stub,
        scope=ScopeFilter(campus="oxford"),
        intent=None,
    )
    result = tool.handler({"query": "q"})
    assert result["evidence"][0]["chunk_id"] == "c1"


def test_collection_name_passed_through() -> None:
    """ETL atomic-swap rollouts pass a different collection alias
    (e.g. Chunk_pending). The tool factory must respect it."""
    stub = StubWeaviate(hits=[_hit()])
    tool = make_search_kb_tool(
        weaviate=stub, scope=ScopeFilter(campus="oxford"),
        collection="Chunk_v2",
    )
    tool.handler({"query": "q"})
    assert stub.calls[0]["collection"] == "Chunk_v2"


def test_collection_resolves_from_env_when_none() -> None:
    """When `collection=None`, the retrieval layer reads
    WEAVIATE_CHUNK_COLLECTION at request time. This is the env-var
    fallback for Weaviate servers older than v1.32 (which don't
    support server-side aliases). Bot operators set the env var
    instead of running an alias swap."""
    import os
    stub = StubWeaviate(hits=[_hit()])
    # Build with collection=None (the new default)
    tool = make_search_kb_tool(
        weaviate=stub, scope=ScopeFilter(campus="oxford"),
        collection=None,
    )
    prev = os.environ.get("WEAVIATE_CHUNK_COLLECTION")
    try:
        os.environ["WEAVIATE_CHUNK_COLLECTION"] = "Chunk_vv20260514_1929"
        tool.handler({"query": "q"})
        assert stub.calls[0]["collection"] == "Chunk_vv20260514_1929"
    finally:
        # Restore prior env state so test ordering doesn't matter
        if prev is None:
            os.environ.pop("WEAVIATE_CHUNK_COLLECTION", None)
        else:
            os.environ["WEAVIATE_CHUNK_COLLECTION"] = prev


def test_collection_defaults_to_chunk_current_when_no_env_no_arg() -> None:
    """The env-var fallback's own fallback: if neither caller-arg nor
    env var is set, default to `Chunk_current` (the alias name for
    Weaviate v1.32+ deployments). Locks in the documented contract."""
    import os
    stub = StubWeaviate(hits=[_hit()])
    tool = make_search_kb_tool(
        weaviate=stub, scope=ScopeFilter(campus="oxford"),
        collection=None,
    )
    prev = os.environ.pop("WEAVIATE_CHUNK_COLLECTION", None)
    try:
        tool.handler({"query": "q"})
        assert stub.calls[0]["collection"] == "Chunk_current"
    finally:
        if prev is not None:
            os.environ["WEAVIATE_CHUNK_COLLECTION"] = prev


def test_search_kb_error_passes_through_to_tool_result() -> None:
    """When Weaviate raises, the tool's result dict carries `error`
    instead of `evidence`. The LLM reads this and may try a different
    query (or give up and let the synthesizer refuse)."""
    stub = StubWeaviate(raises=ConnectionError("Weaviate down"))
    tool = make_search_kb_tool(
        weaviate=stub, scope=ScopeFilter(campus="oxford"),
    )
    result = tool.handler({"query": "q"})
    assert "error" in result
    assert "ConnectionError" in result["error"]
    assert result["evidence"] == []


def test_result_is_json_serializable() -> None:
    """The agent loop wraps tool results in JSON before sending them
    to the LLM. If the dict contains non-JSON types this would crash."""
    stub = StubWeaviate(hits=[_hit()])
    tool = make_search_kb_tool(
        weaviate=stub, scope=ScopeFilter(campus="oxford"),
    )
    result = tool.handler({"query": "q"})
    json.dumps(result)  # raises if any field isn't serializable


def main() -> int:
    tests = [
        test_factory_returns_correct_tool_metadata,
        test_handler_dispatches_and_shapes_result,
        test_empty_query_raises_tool_error,
        test_k_out_of_range_raises,
        test_k_in_range_accepted,
        test_intent_maps_to_featured_service_boost,
        test_unknown_intent_skips_boost,
        test_intent_none_skips_boost,
        test_collection_name_passed_through,
        test_collection_resolves_from_env_when_none,
        test_collection_defaults_to_chunk_current_when_no_env_no_arg,
        test_search_kb_error_passes_through_to_tool_result,
        test_result_is_json_serializable,
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
