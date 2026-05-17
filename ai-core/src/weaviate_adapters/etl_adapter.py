"""
WeaviateETLAdapter: wraps the v4 Weaviate client for the ETL pipeline.

Implements `scripts/etl/upsert.py::WeaviateLike` (Protocol). The ETL
uses a NARROW Weaviate surface:

  upsert_chunk      idempotent insert-or-replace by chunk_id (UUID)
  get_chunk         read properties by chunk_id (for content-hash dedup)
  soft_delete_by_url  set deleted=true on chunks whose source_url isn't in
                       the current crawl's seen-set (tombstoning)
  gc_tombstones     hard-delete chunks tombstoned > N days ago
  count             collection size (diff report)

Schema (matches plan §3 Data preparation playbook):

    Chunk_v{version}
      chunk_id          (UUID, the v4 object's id)
      document_id       text
      source_url        text   - denormalized from Document for fast retrieval
      text              text   - the chunk body (~400 tokens)
      position          int    - 0,1,2... within document
      topic             text   - borrow / spaces / technology / ...
      campus            text   - oxford / hamilton / middletown / all
      library           text   - king / wertz / rentschler / ... / all / ""
      audience          text[] - ["student", "faculty", ...]
      featured_service  text   - adobe_checkout / ill / makerspace / "" / ...
      content_hash      text   - SHA-256 of cleaned text (dedup key)
      deleted           bool   - tombstone flag
      ingested_at       text   - ISO timestamp, set on write

Vectorizer config:
    Set to "none" because the ETL provides vectors directly from
    OpenAI's text-embedding-3-large. Letting Weaviate vectorize would
    fork the embedding model from src/config/models.py.

See plan: Layer 1 (Data pipeline), Data preparation playbook §3, §4.
"""

from __future__ import annotations

import datetime as dt
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

logger = logging.getLogger(__name__)


# Fixed namespace for converting the ETL's chunk_id (a short hex string
# like "c-d8cb85a69c92d7ef") into a deterministic UUID5. Weaviate v4
# strictly validates that an object's id field is a UUID; the chunker
# emits arbitrary strings, so we hash them through uuid5 at this boundary.
# Same chunk_id -> same UUID across runs, preserving idempotency.
_CHUNK_NS = uuid.UUID("c0000000-0000-0000-c0c0-c0c0c0c0c0c0")


def _chunk_uuid(chunk_id: str) -> str:
    """Convert the ETL's chunk_id (arbitrary string) to a stable UUID
    for use as a Weaviate object id.

    Deterministic: `_chunk_uuid("c-abc") == _chunk_uuid("c-abc")` on every
    call, so dedup / upsert by chunk_id still works.
    """
    return str(uuid.uuid5(_CHUNK_NS, chunk_id))


# ----------------------------------------------------------------------------
# Schema definition (re-applied idempotently on first write to a collection).
# Kept in code (not Weaviate's persisted schema as source of truth) so the
# class layout is reviewable in PRs.
# ----------------------------------------------------------------------------

# Field names match what scripts/etl/upsert.py::make_upsert_step writes.
# Keep them in lockstep -- a schema/code mismatch produces silent prop drops.
_CHUNK_PROPERTIES: tuple[tuple[str, str], ...] = (
    # (name, weaviate v4 DataType enum name)
    # The Weaviate object's UUID is derived from `chunk_id` via uuid5
    # (see `_chunk_uuid`). The original chunk_id string is ALSO stored
    # as a property so callers can:
    #   * Look up by chunk_id (filter on this property)
    #   * Join back to ChunkProvenance.chunkId (Postgres uses the
    #     original 'c-...' format, not the UUID5).
    ("chunk_id", "TEXT"),
    ("document_id", "TEXT"),
    ("source_url", "TEXT"),
    ("text", "TEXT"),
    ("position", "INT"),
    ("topic", "TEXT"),
    ("campus", "TEXT"),
    ("library", "TEXT"),
    ("audience", "TEXT_ARRAY"),
    ("featured_service", "TEXT"),
    ("content_hash", "TEXT"),
    ("deleted", "BOOL"),
    ("ingested_at", "TEXT"),
    # Set when soft_delete_by_url tombstones a chunk; used by gc_tombstones
    # to find chunks older than the GC window.
    ("tombstoned_at", "TEXT"),
)


@dataclass
class WeaviateETLAdapter:
    """Implements `WeaviateLike` against a real Weaviate v4 client.

    Construct with `client=None` to auto-resolve from
    `src.utils.weaviate_client.get_weaviate_client()`. Tests inject
    their own (mock) client.

    Collection-creation policy: collections are created on first
    `upsert_chunk` call. Idempotent -- if the collection exists with
    the same schema, this is a no-op. If the schema differs (a future
    field added), `Weaviate.collections.exists()` returns True and we
    DO NOT migrate -- the operator is responsible for choosing a new
    `collection_version` per playbook §6 (versioned collections, alias
    swap on promotion).
    """

    client: Any = None
    _created_collections: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        if self.client is None:
            from src.utils.weaviate_client import get_weaviate_client
            c = get_weaviate_client()
            if c is None:
                raise RuntimeError(
                    "Weaviate client unavailable. Check WEAVIATE_HOST/PORT "
                    "in .env and that the local Docker Weaviate is running. "
                    "See src/utils/weaviate_client.py for connection details."
                )
            self.client = c

    # --- Schema management ---------------------------------------------

    def _ensure_collection(self, collection: str) -> None:
        """Idempotent: create the collection if it doesn't exist, then
        remember so we don't re-check on every upsert.

        Cache is per-adapter-instance, so a fresh adapter re-validates
        once. That's the right shape: if Weaviate restarts mid-run, the
        first call after reconnect will re-validate.
        """
        if collection in self._created_collections:
            return
        try:
            exists = self.client.collections.exists(collection)
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(
                f"Weaviate collections.exists({collection!r}) failed: {e}. "
                f"Is the Weaviate server reachable?"
            ) from e

        if not exists:
            # Lazy import so this module can be imported without the
            # weaviate SDK present (e.g. in environments where the
            # adapter is never instantiated).
            from weaviate.classes.config import Configure, DataType, Property

            datatype_map = {
                "TEXT": DataType.TEXT,
                "INT": DataType.INT,
                "BOOL": DataType.BOOL,
                "TEXT_ARRAY": DataType.TEXT_ARRAY,
            }
            props = [
                Property(name=n, data_type=datatype_map[t])
                for n, t in _CHUNK_PROPERTIES
            ]
            self.client.collections.create(
                name=collection,
                # External vectorizer: we provide vectors from OpenAI;
                # Weaviate doesn't vectorize on write.
                vectorizer_config=Configure.Vectorizer.none(),
                properties=props,
            )
            logger.info(
                "created Weaviate collection",
                extra={"collection": collection, "n_properties": len(props)},
            )
        self._created_collections.add(collection)

    # --- WeaviateLike Protocol surface ---------------------------------

    def upsert_chunk(
        self,
        *,
        collection: str,
        chunk_id: str,
        properties: dict,
        vector: list[float],
        exists: Optional[bool] = None,
    ) -> None:
        """Insert if new, replace if exists. Idempotent on chunk_id.

        The chunker emits chunk_ids in the format 'c-<16 hex>' (see
        `scripts/etl/chunker._derive_chunk_id`). Weaviate v4 requires
        the object's id to be a valid UUID, so we hash the chunk_id
        through uuid5 (`_chunk_uuid`) before sending. The original
        chunk_id is stored as a property for callers that need to
        look up by it OR join to `ChunkProvenance.chunkId` (Postgres
        uses the original 'c-...' format).

        `exists` lets a caller that already knows the object's state
        (the ETL `step()` calls `get_chunk` first) pick the correct
        verb so we don't fire a request that's guaranteed to fail:
          - exists is True  -> object present -> `replace` (REST PUT)
          - exists is False -> object absent  -> `insert`  (REST POST)
          - exists is None  -> unknown -> historical replace-first order
        This matters on a FRESH collection (every ETL run writes to a
        brand-new `Chunk_v{version}`): without it, every chunk does a
        replace-of-nonexistent that some Weaviate builds answer with a
        500, then falls back to insert -- one wasted failing PUT and a
        500-spammed log per chunk. The opposite verb is kept only as a
        race fallback (stale snapshot / concurrent writer / retry).
        """
        self._ensure_collection(collection)
        coll = self.client.collections.get(collection)
        obj_uuid = _chunk_uuid(chunk_id)
        # Always include `chunk_id` as a property so the original
        # identifier survives the UUID conversion. Callers may also
        # have set it; if so we overwrite-with-same-value (no-op).
        props_with_chunk_id = {**properties, "chunk_id": chunk_id}

        def _replace() -> None:
            # `replace` == PUT: full overwrite, requires the object to
            # exist on builds that don't treat it as upsert-create.
            coll.data.replace(
                uuid=obj_uuid,
                properties=props_with_chunk_id,
                vector=vector,
            )

        def _insert() -> None:
            # `insert` == POST: create; conflicts if the object exists.
            coll.data.insert(
                uuid=obj_uuid,
                properties=props_with_chunk_id,
                vector=vector,
            )

        if exists is False:
            primary, fallback = _insert, _replace
            primary_name, fallback_name = "insert", "replace"
        else:
            # exists is True or None -> lead with replace (the v4 upsert
            # primitive when keying on UUID; also the historical order
            # so callers that pass nothing are unaffected).
            primary, fallback = _replace, _insert
            primary_name, fallback_name = "replace", "insert"

        try:
            primary()
        except Exception as e:  # noqa: BLE001
            # Primary verb failed: either the existence snapshot was
            # stale, or this build raises on replace-of-nonexistent.
            # The other verb is the correct one in both those cases.
            try:
                fallback()
            except Exception as e2:  # noqa: BLE001
                raise RuntimeError(
                    f"Weaviate upsert failed for chunk_id={chunk_id!r} "
                    f"(uuid={obj_uuid}) in {collection!r}: "
                    f"{primary_name}={e!r}, {fallback_name}={e2!r}"
                ) from e2

    def get_chunk(
        self,
        *,
        collection: str,
        chunk_id: str,
    ) -> Optional[dict]:
        """Return the chunk's `properties` dict, or None if not found.

        Used by `make_upsert_step` to compare content_hash -> dedup
        decision. We don't return the vector (it's not needed for the
        dedup check + dragging 3072 floats through this hot path would
        be wasteful).

        Like upsert_chunk, this hashes chunk_id -> UUID5 before the
        Weaviate fetch. The returned `properties` includes the original
        `chunk_id` field that upsert_chunk stored, so callers see the
        unaltered identifier.
        """
        if collection not in self._created_collections:
            # Collection doesn't exist -> object doesn't exist. Avoid
            # the round-trip.
            try:
                exists = self.client.collections.exists(collection)
            except Exception:  # noqa: BLE001
                return None
            if not exists:
                return None
            self._created_collections.add(collection)

        coll = self.client.collections.get(collection)
        obj_uuid = _chunk_uuid(chunk_id)
        try:
            obj = coll.query.fetch_object_by_id(obj_uuid)
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "get_chunk failed",
                extra={"collection": collection, "chunk_id": chunk_id,
                       "error": str(e)},
            )
            return None
        if obj is None:
            return None
        # v4 returns a `DataObject`; properties are at `.properties`.
        return dict(obj.properties)

    def soft_delete_by_url(
        self,
        *,
        collection: str,
        urls: Iterable[str],
    ) -> list[str]:
        """Soft-delete: set deleted=true on chunks whose source_url is
        NOT in `urls` (the current crawl's seen-set).

        Returns the list of `source_url` values that were tombstoned
        in this call. Idempotent: re-tombstoning an already-deleted
        chunk is a no-op and doesn't double-count.

        Implementation note: the Protocol takes the SEEN-set, not the
        delete-set, because computing the inverse requires fetching
        every URL in the collection. The adapter does that fetch here.
        """
        self._ensure_collection(collection)
        seen = set(urls)
        coll = self.client.collections.get(collection)

        # Iterate all objects to find non-seen ones. v4 supports
        # paginated iteration via collections.iterator().
        tombstoned: list[str] = []
        now_iso = dt.datetime.utcnow().isoformat()
        try:
            for obj in coll.iterator(return_properties=["source_url", "deleted"]):
                url = obj.properties.get("source_url")
                if not url or url in seen:
                    continue
                already_deleted = bool(obj.properties.get("deleted"))
                if already_deleted:
                    continue
                # Update the row in-place.
                try:
                    coll.data.update(
                        uuid=obj.uuid,
                        properties={"deleted": True, "tombstoned_at": now_iso},
                    )
                    tombstoned.append(url)
                except Exception as e:  # noqa: BLE001
                    logger.warning(
                        "tombstone update failed",
                        extra={"chunk_uuid": str(obj.uuid), "error": str(e)},
                    )
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(
                f"soft_delete_by_url iteration failed for {collection!r}: {e}"
            ) from e
        return tombstoned

    def gc_tombstones(
        self,
        *,
        collection: str,
        older_than: dt.datetime,
    ) -> int:
        """Hard-delete chunks where `deleted=true AND tombstoned_at < older_than`.

        Returns the count of chunks deleted. Per playbook §6 we keep
        tombstoned chunks for `TOMBSTONE_GC_AGE_DAYS` so a librarian
        asking "did the bot have X last week" gets a real answer.
        """
        if collection not in self._created_collections:
            # No collection -> nothing to GC.
            try:
                if not self.client.collections.exists(collection):
                    return 0
            except Exception:  # noqa: BLE001
                return 0
            self._created_collections.add(collection)

        coll = self.client.collections.get(collection)
        cutoff_iso = older_than.isoformat()

        # v4 supports `collection.data.delete_many` with a where filter.
        # Lazy import the Filter helpers so this module imports without
        # the SDK in environments that never call gc.
        from weaviate.classes.query import Filter

        try:
            result = coll.data.delete_many(
                where=Filter.by_property("deleted").equal(True)
                & Filter.by_property("tombstoned_at").less_than(cutoff_iso),
            )
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(
                f"gc_tombstones delete_many failed for {collection!r}: {e}"
            ) from e

        # v4 returns a result object; the field name varies by version.
        # Try `successful` first (current docs), fall back to `matches`.
        for attr in ("successful", "matches", "objects"):
            n = getattr(result, attr, None)
            if isinstance(n, int):
                return n
        # Last resort: trust the result was non-None and unknown shape.
        logger.warning(
            "gc_tombstones: could not parse delete count from result",
            extra={"collection": collection, "result_type": type(result).__name__},
        )
        return 0

    def count(self, *, collection: str) -> int:
        """Number of (non-deleted) chunks in the collection.

        The diff report uses this to display "5,091 chunks in index"
        after a successful run. Errors return -1 so the report still
        renders with a visible "couldn't determine" sentinel rather
        than failing the whole run.
        """
        try:
            if not self.client.collections.exists(collection):
                return 0
        except Exception:  # noqa: BLE001
            return -1
        coll = self.client.collections.get(collection)
        try:
            return coll.aggregate.over_all(total_count=True).total_count or 0
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "count failed",
                extra={"collection": collection, "error": str(e)},
            )
            return -1


__all__ = ["WeaviateETLAdapter"]
