"""
Wraps `src.retrieval.search.search_kb` as an agent Tool.

The agent registers this tool at startup. When the LLM emits a
`search_kb` tool call with arguments `{"query": str}`, the registry
dispatches here. We:

  1. Pull the resolved scope from the per-request context (campus,
     library, intent->featured_service mapping).
  2. Call the retrieval entrypoint.
  3. Return a JSON-serializable result the LLM can read AND the
     synthesizer's evidence-bundle path can consume.

The scope context is passed in at tool-construction time
(`make_search_kb_tool(weaviate, scope, intent)`) so the Tool's
handler closes over it. This avoids threading scope through every
LLM tool-call argument and keeps the LLM-visible schema minimal --
the model only picks the QUERY; the system supplies the scope.

See plan: Layer 2 (Retrieval and grounding) -> "Provenance bundle".
"""

from __future__ import annotations

from typing import Any, Optional

from src.agent.tool_registry import Tool, ToolError
from src.retrieval.scope_filter import ScopeFilter
from src.retrieval.search import (
    RetrievalRequest,
    RetrievalResult,
    WeaviateLike,
    search_kb,
)


# --- Intent -> featured_service mapping ----------------------------------
#
# When the kNN classifier picked one of the featured-service intents,
# we map it to the chunk's `featured_service` tag for the soft boost.
# Non-featured intents (`hours`, `room_booking`, `policy_question`,
# `librarian_lookup`, `service_howto`, `cross_campus_comparison`,
# `human_handoff`, `out_of_scope`) get no boost -- ranking decides.

_INTENT_TO_FEATURED: dict[str, str] = {
    "adobe_access": "adobe_checkout",
    "interlibrary_loan": "ill",
    "makerspace_3d": "makerspace",
    "special_collections": "special_collections",
    "digital_collections": "digital_collections",
    "newspapers": "newspapers",
}


def _intent_to_featured(intent: Optional[str]) -> Optional[str]:
    if intent is None:
        return None
    return _INTENT_TO_FEATURED.get(intent)


# --- Tool description (the LLM reads this) -------------------------------
#
# The description and parameters are what the LLM uses to decide WHEN
# to call the tool. Keep it short, concrete, and unambiguous about
# what the tool DOES and DOES NOT do (e.g., it doesn't make decisions,
# it returns evidence).

_DESCRIPTION = (
    "Search the library knowledge base for evidence relevant to the "
    "user's question. Returns a list of {chunk_id, source_url, "
    "snippet, library, campus, score} items. Call this whenever the "
    "answer requires information about library services, policies, "
    "spaces, or other content that lives on the library website. The "
    "scope (campus + library) is determined by the system from the "
    "user's resolved scope -- you only choose the search QUERY."
)

_PARAMETERS = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": (
                "Natural-language search query. Use the user's exact "
                "phrasing when possible -- BM25 catches name matches "
                "the embedding misses ('Wertz', 'King 110')."
            ),
        },
        "k": {
            "type": "integer",
            "description": (
                "Number of evidence chunks to return. Default 10. Bump "
                "to 20 for broad/comparative questions; drop to 5 for "
                "narrow lookups."
            ),
            "default": 10,
        },
    },
    "required": ["query"],
    "additionalProperties": False,
}


# --- Result shape (what the LLM reads back) ------------------------------
#
# When the LLM calls search_kb, it gets back a tool-result message
# whose content is the JSON of `_result_to_dict(result)`. We strip
# fields the model doesn't need (e.g. used_filter is for forensic
# logs, not the LLM) and present a clean evidence list with 1-indexed
# numbering matching what citations[] will use.


def _result_to_dict(result: RetrievalResult) -> dict:
    if result.error is not None:
        return {
            "error": result.error,
            "evidence": [],
            "raw_hit_count": result.raw_hit_count,
        }
    return {
        "evidence": [
            {
                "n": i + 1,  # 1-indexed; matches synthesizer citation numbering
                "chunk_id": c.chunk_id,
                "source_url": c.source_url,
                "snippet": c.text,
                "library": c.library,
                "campus": c.campus,
                "topic": c.topic,
                "featured_service": c.featured_service,
                "score": c.score,
            }
            for i, c in enumerate(result.chunks)
        ],
        "raw_hit_count": result.raw_hit_count,
    }


# --- Tool factory --------------------------------------------------------


def make_search_kb_tool(
    *,
    weaviate: WeaviateLike,
    scope: ScopeFilter,
    intent: Optional[str] = None,
    collection: Optional[str] = None,
) -> Tool:
    """Build the agent Tool wrapping search_kb for one request.

    Args:
        weaviate: Real or stub WeaviateLike adapter.
        scope: Resolved (campus, library) for THIS request. Closes
            over the handler so the LLM-visible schema stays minimal.
        intent: kNN classifier's chosen intent. Used to map to the
            chunk's featured_service tag for soft boosting.
        collection: Weaviate collection name to query. Default `None`
            falls through to `WEAVIATE_CHUNK_COLLECTION` env var
            (or `Chunk_current` if unset) at request time, so the
            ETL's promote step can update the env var instead of
            requiring a restart of every component holding a closure.

    Returns:
        A Tool ready to register with ToolRegistry.
    """
    # Build the per-request scope-with-featured_service once. Reused
    # on every tool call within this request (LLM may call search_kb
    # multiple times with different queries).
    scope_with_feature = ScopeFilter(
        campus=scope.campus,
        library=scope.library,
        featured_service=_intent_to_featured(intent),
    )

    def handler(args: dict) -> Any:
        query = args.get("query")
        if not isinstance(query, str) or not query.strip():
            raise ToolError("search_kb requires a non-empty `query` string.")
        # Strict-mode tools force `k` into `required` as an int|null
        # union, so the model emits null (not absence) to mean
        # "default". `default` in the schema is ignored under strict
        # decoding -- the handler owns the default. (See
        # tool_registry._strictify_schema.)
        k_raw = args.get("k")
        k = 10 if k_raw is None else int(k_raw)
        if k < 1 or k > 50:
            # Bound the requested k -- defends against the LLM passing
            # k=10000 because of a bad chain-of-thought.
            raise ToolError(f"search_kb k={k} out of range (1..50).")

        result = search_kb(
            RetrievalRequest(query=query.strip(), scope=scope_with_feature, k=k),
            weaviate=weaviate,
            collection=collection,
        )

        # Empty + no error == NO_RESULTS (the agent / synthesizer
        # decides what to do with that). We don't raise here; the LLM
        # may still want to try a different query before refusing.
        return _result_to_dict(result)

    return Tool(
        name="search_kb",
        description=_DESCRIPTION,
        parameters=_PARAMETERS,
        handler=handler,
        is_read_only=True,
    )


__all__ = [
    "make_search_kb_tool",
]
