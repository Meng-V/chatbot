"""
WeaviateSearchAdapter: read-side v4 client wrapper for retrieval.

Implements `src/retrieval/search.py::WeaviateLike` (the `hybrid_search`
Protocol). This is the production wire that lets `search_kb` query the
real indexed corpus instead of the hand-written `_REALISTIC_EVIDENCE`
map the eval used as a stopgap.

Separate module from `etl_adapter.py` on purpose:
  - ETL adapter = WRITE side (upsert / tombstone / gc). Destructive.
  - Search adapter = READ side (hybrid query). Idempotent, hot path.
Different consistency + performance concerns; keeping them apart keeps
each adapter's surface minimal and auditable.

The scope-filter dict shape (`build_where_clause` /
`build_should_match` in `src/retrieval/scope_filter.py`) is a nested
{operator, operands, path, valueText/valueBoolean} structure. This
adapter recursively translates it into v4 typed `Filter` objects.

See plan: Layer 2 (Retrieval and grounding).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)


def _translate_filter(clause: dict) -> Any:
    """Recursively convert a scope_filter dict into a v4 `Filter`.

    Input shapes (from src/retrieval/scope_filter.py):
        {"operator": "And", "operands": [ ... ]}
        {"operator": "Or",  "operands": [ ... ]}
        {"path": ["campus"], "operator": "Equal", "valueText": "oxford"}
        {"path": ["deleted"], "operator": "Equal", "valueBoolean": False}

    Lazy-imports `weaviate.classes.query.Filter` so this module is
    importable in environments without the SDK (the translator itself
    is unit-tested with a fake Filter; see test_search_adapter.py).
    """
    from weaviate.classes.query import Filter

    op = clause.get("operator")

    if op == "And":
        operands = [_translate_filter(o) for o in clause["operands"]]
        return Filter.all_of(operands)
    if op == "Or":
        operands = [_translate_filter(o) for o in clause["operands"]]
        return Filter.any_of(operands)
    if op == "Equal":
        path = clause["path"][0]
        if "valueText" in clause:
            return Filter.by_property(path).equal(clause["valueText"])
        if "valueBoolean" in clause:
            return Filter.by_property(path).equal(clause["valueBoolean"])
        raise ValueError(
            f"Equal clause for path={path!r} has no valueText/valueBoolean: "
            f"{clause!r}"
        )
    raise ValueError(f"unsupported filter clause: {clause!r}")


# Exposed for unit testing with an injected fake `Filter` so the
# recursive translation can be exercised without the weaviate SDK.
def _translate_filter_with(clause: dict, filter_cls: Any) -> Any:
    """Same as _translate_filter but uses an injected Filter class.
    Used by tests; prod calls _translate_filter (lazy real import)."""
    op = clause.get("operator")
    if op == "And":
        return filter_cls.all_of(
            [_translate_filter_with(o, filter_cls) for o in clause["operands"]]
        )
    if op == "Or":
        return filter_cls.any_of(
            [_translate_filter_with(o, filter_cls) for o in clause["operands"]]
        )
    if op == "Equal":
        path = clause["path"][0]
        if "valueText" in clause:
            return filter_cls.by_property(path).equal(clause["valueText"])
        if "valueBoolean" in clause:
            return filter_cls.by_property(path).equal(clause["valueBoolean"])
        raise ValueError(f"Equal clause missing value: {clause!r}")
    raise ValueError(f"unsupported filter clause: {clause!r}")


@dataclass
class WeaviateSearchAdapter:
    """Implements `WeaviateLike.hybrid_search` against a real v4 client.

    Construct with `client=None` to auto-resolve from
    `src.utils.weaviate_client.get_weaviate_client()`. Tests inject a
    fake client exposing `.collections.get(name).query.hybrid(...)`.
    """

    client: Any = None

    def __post_init__(self) -> None:
        if self.client is None:
            from src.utils.weaviate_client import get_weaviate_client
            c = get_weaviate_client()
            if c is None:
                raise RuntimeError(
                    "Weaviate client unavailable. Check WEAVIATE_HOST/PORT "
                    "in .env and that the server's Weaviate is reachable "
                    "(SSH tunnel if running the eval from a laptop). See "
                    "src/utils/weaviate_client.py."
                )
            self.client = c

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
        """Run a v4 hybrid (BM25 + vector) query.

        `should_match` is accepted for Protocol conformance but NOT
        applied here -- src/retrieval/search.py does featured-service
        soft-boost reordering on the returned hits AFTER this call, so
        applying it again here would double-count. The contract is:
        this method does the hard-filtered hybrid query; the caller
        does the soft rank-nudge.

        Returns hit dicts in the shape WeaviateLike documents:
            {chunk_id, source_url, text, campus, library, topic,
             featured_service, score}

        On any error returns [] (the caller treats empty as NO_RESULTS
        and the agent refuses via that trigger -- never crash the turn
        on a retrieval hiccup).
        """
        # Build optional v4 query helpers. If the SDK isn't importable
        # (sandbox / unit tests with a fake client), degrade: no typed
        # filter, no metadata request. A fake client ignores both; a
        # real Weaviate server always has the SDK. Only an actual query
        # EXECUTION error returns [] -- an SDK-absent environment is a
        # test path, not a turn failure.
        filters = None
        return_metadata = None
        try:
            from weaviate.classes.query import Filter as _F  # noqa: F401
            from weaviate.classes.query import MetadataQuery

            return_metadata = MetadataQuery(score=True)
            if where:
                filters = _translate_filter(where)
        except ImportError:
            logger.debug(
                "weaviate SDK not importable; querying without typed "
                "filter / metadata (test or sandbox path)"
            )

        try:
            coll = self.client.collections.get(collection)
            resp = coll.query.hybrid(
                query=query,
                alpha=alpha,
                limit=limit,
                filters=filters,
                return_metadata=return_metadata,
            )
        except Exception as e:  # noqa: BLE001 -- never crash the turn
            logger.warning(
                "hybrid_search failed for collection=%s query=%r: %s",
                collection, query[:80], e,
            )
            return []

        hits: list[dict] = []
        for obj in getattr(resp, "objects", []) or []:
            props = dict(getattr(obj, "properties", {}) or {})
            meta = getattr(obj, "metadata", None)
            score = 0.0
            if meta is not None and getattr(meta, "score", None) is not None:
                try:
                    score = float(meta.score)
                except (TypeError, ValueError):
                    score = 0.0
            hits.append({
                # The ETL stored the original chunk_id as a property
                # (the Weaviate object id is a uuid5 of it -- see
                # etl_adapter._chunk_uuid). Prefer the property; fall
                # back to the object uuid if somehow absent.
                "chunk_id": props.get("chunk_id") or str(getattr(obj, "uuid", "")),
                "source_url": props.get("source_url", ""),
                "text": props.get("text", ""),
                "campus": props.get("campus"),
                "library": props.get("library") or None,
                "topic": props.get("topic"),
                "featured_service": props.get("featured_service") or None,
                "score": score,
            })
        return hits


__all__ = ["WeaviateSearchAdapter", "_translate_filter", "_translate_filter_with"]
