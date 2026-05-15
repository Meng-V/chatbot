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


# Per-input cap. OpenAI text-embedding-3-large rejects single inputs
# > 8192 tokens with a 400. ~4 chars/token, minus 1k chars slack for
# multibyte / dense content. The chunker's CHUNK_HARD_MAX_TOKENS is
# the primary guard; this is the second layer.
_EMBED_MAX_INPUT_CHARS = 8192 * 4 - 1000

# Per-REQUEST cap. text-embedding-3-large accepts up to 300_000 tokens
# per request. We target a much lower budget because:
#   1. tiktoken (cl100k_base) isn't always available, and our char/4
#      estimate is wildly optimistic on dense text (URLs, code) where
#      real tokens can be ~1.5x our estimate.
#   2. The TPM (tokens-per-minute) rate limit is 5M; a few back-to-back
#      300K-token requests trigger 429s. Smaller requests pace better.
# 200_000 leaves 33% headroom against the 300K hard limit.
_EMBED_MAX_BATCH_TOKENS = 200_000


def _count_tokens(text: str, encoder: Any) -> int:
    """Tokens for `text`, using tiktoken if available, else chars/4.

    The chunker uses the same fallback (`_approximate_tokens`) so this
    is consistent with chunk-size decisions when tiktoken isn't loaded.
    """
    if encoder is not None:
        try:
            return len(encoder.encode(text))
        except Exception:  # noqa: BLE001 -- never let counting kill the run
            pass
    return max(1, len(text) // 4)


def _iter_token_budgeted_batches(
    texts: list[str],
    *,
    max_count: int,
    max_tokens: int,
    encoder: Any,
) -> Iterable[tuple[int, list[str]]]:
    """Yield `(batch_start, batch_texts)` such that each batch has
    `len(batch) <= max_count` AND sum(tokens) <= max_tokens.

    Single inputs already above `max_tokens` are yielded alone (caller
    has already truncated to the per-input cap, so this is safe).
    """
    cur: list[str] = []
    cur_tokens = 0
    cur_start = 0
    for i, t in enumerate(texts):
        n = _count_tokens(t, encoder)
        # Flush before adding if adding would exceed either cap.
        if cur and (len(cur) >= max_count or cur_tokens + n > max_tokens):
            yield cur_start, cur
            cur = []
            cur_tokens = 0
            cur_start = i
        cur.append(t)
        cur_tokens += n
    if cur:
        yield cur_start, cur


def embed_chunks(
    chunks: list[Chunk],
    client: EmbeddingClient,
    *,
    model: str,
    batch_size: int = config.EMBED_BATCH_SIZE,
) -> list[list[float]]:
    """Compute embeddings for a list of chunks.

    Batches are dynamically sized to satisfy BOTH:
      - `len(batch) <= batch_size` (the count cap), AND
      - sum(tokens(batch)) <= _EMBED_MAX_BATCH_TOKENS (the request cap).

    The request-cap guard exists because OpenAI's embeddings API
    rejects requests above 300_000 tokens, and our previous
    fixed-count batching of 100 chunks could exceed that on
    token-dense content even when each chunk was under the per-input
    cap. See git history / PR #45 follow-up for the failure mode.

    Per-batch failures log and pad with zero-vectors; the upsert step
    tolerates zero-vector rows by leaving them out of the index, so a
    partial failure doesn't poison the whole run.

    `model` MUST come from src/config/models.py::EMBEDDING_MODEL -- never
    hard-code a string here. The freshness rule applies: confirm the
    model identifier against live OpenAI docs before changing.
    """
    if not chunks:
        return []
    # tiktoken is optional. If absent, fall back to chars/4 (same shape
    # as the chunker's _approximate_tokens). The pipeline runs either
    # way; tiktoken just makes the batching tighter.
    encoder: Any = None
    try:
        import tiktoken  # type: ignore

        encoder = tiktoken.get_encoding("cl100k_base")
    except Exception:  # noqa: BLE001
        encoder = None

    # First pass: per-input truncation to keep any single chunk under
    # the model's 8192-token-per-input cap.
    texts: list[str] = []
    for c in chunks:
        t = c.text
        if len(t) > _EMBED_MAX_INPUT_CHARS:
            logger.warning(
                "embed input truncated [chunk_id=%s orig_chars=%d -> %d]",
                c.chunk_id, len(t), _EMBED_MAX_INPUT_CHARS,
            )
            t = t[:_EMBED_MAX_INPUT_CHARS]
        texts.append(t)

    out: list[list[float]] = []
    for batch_start, batch_texts in _iter_token_budgeted_batches(
        texts,
        max_count=batch_size,
        max_tokens=_EMBED_MAX_BATCH_TOKENS,
        encoder=encoder,
    ):
        try:
            resp = client.create(model=model, input=batch_texts)
            # OpenAI SDK shape: resp.data is a list of objects with .embedding
            for item in resp.data:
                out.append(list(item.embedding))
        except Exception as e:  # noqa: BLE001 -- never let one batch kill the run
            # Include the actual error text in the log message so the
            # default logging format surfaces it (extras aren't shown by
            # default). Also log batch position + the longest input's
            # length -- OpenAI's most common 400 cause is a single
            # chunk exceeding the 8192-token cap.
            max_chars = max((len(t) for t in batch_texts), default=0)
            logger.error(
                "embed batch failed [batch_start=%d size=%d max_chars=%d]: %s",
                batch_start, len(batch_texts), max_chars, e,
            )
            # Pad with empty vectors so positions line up; upsert drops these.
            out.extend([[]] * len(batch_texts))
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

    Server compatibility:
      * Weaviate v1.32+ supports server-side aliases via the v4 client's
        `client.alias.{create,update,list_all}` API. We use that path
        when available.
      * Older servers (v1.27, v1.28, v1.31) don't support aliases at
        all -- the API call returns a 404. For those, this function
        emits clear instructions for the env-var fallback path
        (set `WEAVIATE_CHUNK_COLLECTION=Chunk_v{version}` in `.env` and
        restart the bot). Both `src/retrieval/search.py` and
        `src/tools/search_kb_tool.py` honor that env var at request
        time.
    """
    target_collection = f"Chunk_v{version}"

    # Attempt server-side alias swap (v1.32+ servers).
    alias_api = getattr(weaviate, "alias", None)
    if alias_api is not None:
        try:
            # The v4 client exposes alias management via client.alias.
            # Use update if the alias exists, create otherwise.
            existing = list(alias_api.list_all() or [])
            existing_names = {a.alias_name for a in existing}
            if alias in existing_names:
                alias_api.update(
                    alias_name=alias,
                    new_target_collection=target_collection,
                )
                action = "updated"
            else:
                alias_api.create(
                    alias_name=alias,
                    target_collection=target_collection,
                )
                action = "created"
            logger.info(
                "promoted collection (server-side alias)",
                extra={"alias": alias, "target": target_collection, "action": action},
            )
            return
        except Exception as e:  # noqa: BLE001
            # Fall through to env-var instructions. Server probably
            # too old (v1.27 / v1.28 / v1.31 don't have aliases).
            logger.info(
                "server-side alias promotion failed (likely server pre-v1.32): %s",
                e,
            )

    # Fallback path: server doesn't support aliases. The bot reads from
    # WEAVIATE_CHUNK_COLLECTION at request time -- update that env var.
    msg = (
        f"\n  Server-side alias promotion not available on this Weaviate "
        f"(typically pre-v1.32).\n"
        f"  To make the bot read from the new collection, set this in "
        f"your `.env`:\n\n"
        f"      WEAVIATE_CHUNK_COLLECTION={target_collection}\n\n"
        f"  Then restart the FastAPI worker so the env var is picked up.\n"
        f"  This is functionally equivalent to an alias swap; it just "
        f"requires a process restart\n  instead of an atomic server-side "
        f"operation. The retrieval code in `src/retrieval/search.py`\n  "
        f"and `src/tools/search_kb_tool.py` resolves the collection name "
        f"from this env var at\n  request time.\n"
    )
    logger.info("promote_collection: %s", msg)
    print(msg)
