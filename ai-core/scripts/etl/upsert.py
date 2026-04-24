"""
Steps 7-10 of the ETL pipeline: embed -> upsert -> tombstone -> URL allowlist.

This is the only file in the ETL that talks to Weaviate, Postgres, and
OpenAI directly. Everything upstream is pure transformation; everything
here is side effects with rollback semantics.

Critical engineering rules (plan §4):
  - Idempotent: running twice produces no second-run changes.
  - Resumable: each step writes a checkpoint so failures don't redo work.
  - Reversible: writes go to a fresh Weaviate collection version; promote
    by alias swap, rollback by re-aliasing.

The four prod functions (`embed_chunks`, `upsert_to_weaviate`,
`tombstone_removed_urls`, `update_url_allowlist`) are factories that
take their concrete client (OpenAI / Weaviate / Prisma) and return a
callable matching the `Pipeline` step signatures in run_etl.py. This
keeps the ETL orchestrator transport-agnostic AND testable: the smoke
test passes in-memory implementations of the same three protocols.

See plan: Data preparation playbook §4 steps 7-10, §6 lifecycle.
"""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Optional, Protocol

from . import config
from .chunker import Chunk

logger = logging.getLogger(__name__)


# --- Result types ------------------------------------------------------------


@dataclass
class UpsertResult:
    """Summary of what an upsert run did. Feeds the diff report."""

    new_chunk_ids: list[str] = field(default_factory=list)
    changed_chunk_ids: list[str] = field(default_factory=list)
    deduped_chunk_ids: list[str] = field(default_factory=list)
    tombstoned_urls: list[str] = field(default_factory=list)
    gc_deleted_chunk_count: int = 0
    new_url_count: int = 0
    total_chunks_in_index: Optional[int] = None
    weaviate_collection_version: Optional[str] = None


# --- Backend protocols (transport-agnostic seam) -----------------------------


class EmbeddingClient(Protocol):
    """Subset of OpenAI's embeddings API the ETL uses.

    Only the `create` call is needed. Tests provide a stub that returns
    deterministic vectors so the smoke test doesn't need an API key.
    """

    def create(self, *, model: str, input: list[str]) -> Any: ...


class WeaviateLike(Protocol):
    """Subset of the Weaviate client surface the ETL uses.

    Stays narrow on purpose: the ETL is allowed to UPSERT chunks,
    SOFT-DELETE chunks (set deleted=true), and GC hard-delete chunks
    older than `TOMBSTONE_GC_AGE_DAYS`. Anything else (collection
    creation, alias swaps) is wrapped separately so the destructive
    surface is small and auditable.
    """

    def upsert_chunk(
        self, *, collection: str, chunk_id: str, properties: dict, vector: list[float]
    ) -> None: ...
    def get_chunk(
        self, *, collection: str, chunk_id: str
    ) -> Optional[dict]: ...
    def soft_delete_by_url(
        self, *, collection: str, urls: Iterable[str]
    ) -> list[str]: ...
    def gc_tombstones(
        self, *, collection: str, older_than: dt.datetime
    ) -> int: ...
    def count(self, *, collection: str) -> int: ...


class UrlSeenStore(Protocol):
    """Subset of the Prisma `urlseen` model the ETL writes to.

    Returns the count of NEW (previously-unseen) rows so the diff report
    can show "5 new URLs added to allowlist" rather than "1273 URLs upserted".
    """

    def upsert_many(
        self, rows: list[dict], *, featured_urls: set[str]
    ) -> int: ...


# --- Step 7: Embed -----------------------------------------------------------


def embed_chunks(
    chunks: list[Chunk],
    client: EmbeddingClient,
    *,
    model: str,
    batch_size: int = config.EMBED_BATCH_SIZE,
) -> list[list[float]]:
    """Compute embeddings for a list of chunks.

    Batched per `batch_size` (OpenAI text-embedding-3-large allows up
    to 2048; we default lower for headroom). Per-batch failure logs and
    skips that batch with zero-vectors -- the upsert step tolerates
    zero-vector rows by leaving them out of the index, so a partial
    failure doesn't poison the whole run.

    `model` MUST come from src/config/models.py::EMBEDDING_MODEL -- never
    hard-code a string here. The freshness rule applies: confirm the
    model identifier against live OpenAI docs before changing.
    """
    if not chunks:
        return []
    out: list[list[float]] = []
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i : i + batch_size]
        texts = [c.text for c in batch]
        try:
            resp = client.create(model=model, input=texts)
            # OpenAI SDK shape: resp.data is a list of objects with .embedding
            for item in resp.data:
                out.append(list(item.embedding))
        except Exception as e:  # noqa: BLE001 -- never let one batch kill the run
            logger.error(
                "embed batch failed",
                extra={"batch_start": i, "batch_size": len(batch), "error": str(e)},
            )
            # Pad with empty vectors so positions line up; upsert drops these.
            out.extend([[]] * len(batch))
    return out


# --- Step 8: Upsert ----------------------------------------------------------


def make_upsert_step(
    weaviate: WeaviateLike,
    *,
    collection_prefix: str = "Chunk",
) -> Callable[[list[Chunk], list[list[float]], str], UpsertResult]:
    """Build the upsert step closure for the Pipeline.

    Writes go to `{prefix}_v{collection_version}` -- a FRESH collection,
    not the one currently aliased as `Chunk_current`. Promotion is a
    separate operation (`promote_collection`) that swaps the alias only
    after eval has run against the new version.

    Idempotent on chunk_id: a chunk whose `content_hash` already exists
    in the destination collection is skipped (counted in `deduped_chunk_ids`).
    Same chunk_id with a different content_hash counts as `changed`.
    """

    def step(
        chunks: list[Chunk],
        embeddings: list[list[float]],
        version: str,
    ) -> UpsertResult:
        collection = f"{collection_prefix}_v{version}"
        result = UpsertResult(weaviate_collection_version=version)
        for chunk, vector in zip(chunks, embeddings):
            if not vector:
                # Embedding failed for this batch; skip rather than index a zero vec.
                continue
            existing = weaviate.get_chunk(collection=collection, chunk_id=chunk.chunk_id)
            if existing and existing.get("content_hash") == chunk.content_hash:
                result.deduped_chunk_ids.append(chunk.chunk_id)
                continue

            properties = {
                "document_id": chunk.document_id,
                "source_url": chunk.source_url,
                "text": chunk.text,
                "position": chunk.position,
                "topic": chunk.topic,
                "campus": chunk.campus,
                "library": chunk.library or "",
                "audience": chunk.audience,
                "featured_service": chunk.featured_service or "",
                "content_hash": chunk.content_hash,
                "deleted": False,
                "ingested_at": dt.datetime.utcnow().isoformat(),
            }
            weaviate.upsert_chunk(
                collection=collection,
                chunk_id=chunk.chunk_id,
                properties=properties,
                vector=vector,
            )
            if existing:
                result.changed_chunk_ids.append(chunk.chunk_id)
            else:
                result.new_chunk_ids.append(chunk.chunk_id)

        try:
            result.total_chunks_in_index = weaviate.count(collection=collection)
        except Exception:  # noqa: BLE001
            result.total_chunks_in_index = None
        return result

    return step


# --- Step 9: Tombstone -------------------------------------------------------


def make_tombstone_step(
    weaviate: WeaviateLike,
    *,
    collection_prefix: str = "Chunk",
    gc_age_days: int = config.TOMBSTONE_GC_AGE_DAYS,
) -> Callable[[set[str], str], UpsertResult]:
    """Build the tombstone step closure for the Pipeline.

    Soft-delete: any chunk whose `source_url` was NOT in the current
    crawl's seen-set gets `deleted=true` set. Per playbook §6, we DON'T
    hard-delete for `gc_age_days` so a librarian asking "did the bot have
    X last week" gets a real answer.
    """

    def step(seen_urls: set[str], version: str) -> UpsertResult:
        collection = f"{collection_prefix}_v{version}"
        # The store is responsible for the inversion ("delete chunks whose
        # source_url is NOT in this set") because doing it client-side
        # requires fetching every URL in the collection.
        tombstoned = weaviate.soft_delete_by_url(
            collection=collection,
            urls=seen_urls,
        )
        gc_deleted = weaviate.gc_tombstones(
            collection=collection,
            older_than=dt.datetime.utcnow() - dt.timedelta(days=gc_age_days),
        )
        return UpsertResult(
            tombstoned_urls=list(tombstoned),
            gc_deleted_chunk_count=gc_deleted,
            weaviate_collection_version=version,
        )

    return step


# --- Step 10: URL allowlist --------------------------------------------------


def make_allowlist_step(
    store: UrlSeenStore,
) -> Callable[[list[tuple[str, int, str, Optional[str]]]], int]:
    """Build the allowlist-update step closure for the Pipeline.

    Idempotent on `url` PK. Updates http_status, last_seen, content_type
    on each call. Featured-service URLs (matching FEATURED_SERVICE_PATTERNS)
    get priority='high' set -- the validator treats them leniently in
    freshness checks so a transient sitemap glitch doesn't blackhole the
    highest-value pages.

    NEVER touches is_blacklisted -- that's librarian-controlled via the
    ManualCorrection workflow (Op 2). This is the load-bearing invariant
    that lets librarians override the bot's URL choices without code deploys.
    """

    def step(rows: list[tuple[str, int, str, Optional[str]]]) -> int:
        # Compute the featured set client-side so the store doesn't need
        # to know our config. This keeps the store interface narrow.
        featured: set[str] = set()
        for url, _status, _source, _ct in rows:
            lowered = url.lower()
            for substr, _tag in config.FEATURED_SERVICE_PATTERNS:
                if substr in lowered:
                    featured.add(url)
                    break

        formatted = [
            {
                "url": url,
                "http_status": status,
                "source": source,
                "content_type": content_type,
                "last_seen": dt.datetime.utcnow(),
            }
            for url, status, source, content_type in rows
        ]
        return store.upsert_many(formatted, featured_urls=featured)

    return step


# --- Promotion (alias swap, manual gate) -------------------------------------


def promote_collection(
    weaviate: Any, *, version: str, alias: str = "Chunk_current"
) -> None:
    """Atomically swap `alias` to point to `Chunk_v{version}`.

    Called ONLY after eval passes against the new version. Rollback is
    `promote_collection(weaviate, version=previous_version)` -- a single
    alias swap, no data movement. Not part of the Pipeline because it's
    a manual decision gate (you don't want a cron auto-promoting).
    """
    if not hasattr(weaviate, "swap_alias"):
        raise NotImplementedError(
            "weaviate client does not expose swap_alias; wire one up "
            "(Weaviate v4 client supports collections.alias.create / .replace)."
        )
    weaviate.swap_alias(alias=alias, target=f"Chunk_v{version}")
    logger.info("promoted collection", extra={"alias": alias, "version": version})
