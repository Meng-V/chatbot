"""
Retrieval layer: pulls evidence chunks from Weaviate with scope-aware
filtering, returns an EvidenceChunk bundle the synthesizer can cite.

The agent calls this via the `search_kb` tool. The synthesizer never
calls the retriever directly -- that boundary keeps the synthesizer's
grounding contract enforceable (the synthesizer only sees an evidence
bundle, never the search query).

Public API:
    search_kb(query, scope, *, weaviate, k=10) -> RetrievalResult

See plan: Layer 2 (Retrieval and grounding).
"""

from src.retrieval.scope_filter import build_where_clause
from src.retrieval.search import (
    RetrievalRequest,
    RetrievalResult,
    WeaviateLike,
    search_kb,
)

__all__ = [
    "RetrievalRequest",
    "RetrievalResult",
    "WeaviateLike",
    "build_where_clause",
    "search_kb",
]
