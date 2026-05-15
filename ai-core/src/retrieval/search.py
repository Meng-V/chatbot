"""
Hybrid retrieval entrypoint: query Weaviate, return EvidenceChunks.

`search_kb()` is the single function the agent's `search_kb` tool calls.
Internally it:
  1. Builds the scope filter (scope_filter.py).
  2. Issues a Weaviate hybrid query (BM25 + vector).
  3. Applies the featured-service soft boost.
  4. Returns RetrievalResult containing EvidenceChunks ready for
     `apply_corrections` -> synthesizer.

The Weaviate client is injected via the `WeaviateLike` Protocol so this
module is testable without the real client. Tests pass a stub that
returns canned hits; prod injects the v4 client adapter.

See plan: Layer 2 (Retrieval and grounding) + Data preparation
playbook §8 (campus / library scope binding).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Protocol

from src.retrieval.scope_filter import (
    ScopeFilter,
    build_should_match,
    build_where_clause,
)
from src.synthesis.corrections import EvidenceChunk


# --- Public types --------------------------------------------------------


@dataclass(frozen=True)
class RetrievalRequest:
    """One retrieval call. Deliberately wide so the synthesizer's eval
    log can record the full request shape for forensic replay."""

    query: str
    scope: ScopeFilter
    k: int = 10
    """Hybrid top-k. 10 is a reasonable default; the agent may bump
    when the question phrasing suggests breadth (cross-campus
    comparisons, broad policy questions)."""

    alpha: float = 0.5
    """Weaviate hybrid alpha: 0.0 = pure BM25, 1.0 = pure vector. 0.5
    splits the difference. BM25 catches exact name matches ('Wertz',
    'King 110') that pure vectors miss; vector catches paraphrases
    ('art library' -> Wertz) that BM25 misses. Both matter."""


@dataclass(frozen=True)
class RetrievalResult:
    """Bundle returned to the agent. The synthesizer reads `chunks`
    after corrections are applied. The other fields are diagnostic.
    """

    chunks: list[EvidenceChunk] = field(default_factory=list)
    raw_hit_count: int = 0
    """How many hits Weaviate returned BEFORE our soft-boost reordering
    or any local filtering. Useful when debugging 'why did retrieval
    return nothing for this scope'."""

    used_filter: Optional[dict] = None
    """The where-clause we sent. Logged so eval-suite failures can be
    reproduced exactly."""

    error: Optional[str] = None
    """Set when retrieval failed (Weaviate down, malformed filter,
    etc.). When set, `chunks` is always empty and the agent should
    treat this as NO_RESULTS for refusal purposes."""


# --- Weaviate seam -------------------------------------------------------


class WeaviateLike(Protocol):
    """Minimal Weaviate interface the retrieval layer needs.

    Wraps either v3 or v4 of the Weaviate client. Prod imports the v4
    client and writes a thin adapter; tests pass a stub returning
    canned hits. Keeps this module's import surface zero-cost in the
    sandbox where Weaviate isn't installed.
    """

    def hybrid_search(
        self,
        *,
        collection: str,
        query: str,
        where: dict,
        alpha: float,
        limit: int,
        should_match: Optional[dict] = None,
    ) -> list[dict]:
        """Run a hybrid (BM25 + vector) query.

        Returns a list of hit dicts shaped:
            {
                "chunk_id": str,
                "source_url": str,
                "text": str,
                "campus": str | None,
                "library": str | None,
                "topic": str | None,
                "featured_service": str | None,
                "score": float,
            }

        Adapter is responsible for translating these back from the
        Weaviate response shape (which differs across client versions).
        """
        ...


# --- Entry point ---------------------------------------------------------


def _default_collection() -> str:
    """Resolve the Weaviate collection to query at request time.

    Default is `Chunk_current` -- the alias the ETL's `promote_collection`
    points at the latest approved version, on Weaviate v1.32+ servers
    that support aliases.

    On older servers (v1.27 / v1.28 / v1.31) where aliases don't exist
    yet, set `WEAVIATE_CHUNK_COLLECTION=Chunk_v<date>` in `.env` to
    select an explicit version. Restart the FastAPI worker after
    changing it.
    """
    import os
    return os.getenv("WEAVIATE_CHUNK_COLLECTION", "Chunk_current")


def search_kb(
    request: RetrievalRequest,
    *,
    weaviate: WeaviateLike,
    collection: Optional[str] = None,
) -> RetrievalResult:
    """Run a scope-filtered hybrid search and return EvidenceChunks.

    Args:
        request: Query + scope + k + alpha.
        weaviate: Injectable client (Protocol). Prod: real v4 adapter.
            Tests: a stub returning canned hits.
        collection: Weaviate collection alias to query. Default points
            at the live alias; ETL flips this between versions.

    Returns:
        RetrievalResult. On any error (network, malformed response),
        `chunks=[]` and `error` is set so the agent can refuse via
        the no_results / live_data_down trigger rather than crash.
    """
    where = build_where_clause(request.scope)
    should_match = build_should_match(request.scope)
    # Late-resolve the collection name so a `None` default falls
    # through to the env var (`WEAVIATE_CHUNK_COLLECTION`) without
    # forcing every caller to thread the env lookup themselves.
    if collection is None:
        collection = _default_collection()

    try:
        hits = weaviate.hybrid_search(
            collection=collection,
            query=request.query,
            where=where,
            alpha=request.alpha,
            limit=request.k,
            should_match=should_match,
        )
    except Exception as e:
        return RetrievalResult(
            chunks=[],
            raw_hit_count=0,
            used_filter=where,
            error=f"{type(e).__name__}: {e}",
        )

    # Translate hits -> EvidenceChunks. The adapter normalizes the
    # response shape so we don't sprinkle isinstance / .get-defaults
    # all over the codebase. Per-hit defensive default-handling here
    # is for the edge case of a malformed adapter (returns a hit
    # missing one of the required fields).
    chunks: list[EvidenceChunk] = []
    for h in hits:
        chunk_id = h.get("chunk_id")
        source_url = h.get("source_url")
        text = h.get("text")
        if not (chunk_id and source_url and text):
            # Skip malformed hits silently; the diagnostic path is
            # `raw_hit_count > len(chunks)` -- caller sees the gap.
            continue
        chunks.append(
            EvidenceChunk(
                chunk_id=chunk_id,
                source_url=source_url,
                text=text,
                campus=h.get("campus"),
                library=h.get("library"),
                topic=h.get("topic"),
                featured_service=h.get("featured_service"),
                score=float(h.get("score", 0.0)),
            )
        )

    # Featured-service soft-boost: the retriever returned hits in
    # Weaviate's hybrid order, but we want chunks tagged with the
    # matching featured_service to win ties. Stable sort by
    # (-is_match, -score) preserves the underlying hybrid order
    # within each tier.
    if request.scope.featured_service is not None:
        target = request.scope.featured_service
        chunks.sort(
            key=lambda c: (0 if c.featured_service == target else 1, -c.score),
        )

    return RetrievalResult(
        chunks=chunks,
        raw_hit_count=len(hits),
        used_filter=where,
        error=None,
    )


__all__ = [
    "RetrievalRequest",
    "RetrievalResult",
    "WeaviateLike",
    "search_kb",
]
