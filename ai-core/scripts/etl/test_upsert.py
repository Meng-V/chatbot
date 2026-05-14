"""
Unit tests for the ETL upsert/embed/tombstone/allowlist steps.

Run: `python -m scripts.etl.test_upsert` from ai-core/.

These steps wrap the only Weaviate / OpenAI / Postgres I/O in the
ETL. The Protocol seam means tests can pass in-memory stubs and
exercise every branch (dedup, change, new, embed-batch-failure,
tombstone GC, featured-URL priority) without touching real
infrastructure.

A bug here is the worst kind:
  - Embedding-batch error swallowed -> entire run silently indexes
    zero-vectors.
  - Dedup misses content_hash collision -> duplicate Weaviate rows.
  - Tombstone GC fires too aggressively -> librarian loses the
    "what did the bot have last week" forensic window.
  - Allowlist forgets to mark featured URLs -> a transient sitemap
    glitch blackholes the highest-value pages.

Tests pin every branch.
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path
from typing import Any, Iterable, Optional

# Allow running from ai-core/ as `python -m scripts.etl.test_upsert`.
_HERE = Path(__file__).resolve().parent
_AI_CORE = _HERE.parent.parent
sys.path.insert(0, str(_AI_CORE))

from scripts.etl.chunker import Chunk  # noqa: E402
from scripts.etl.upsert import (  # noqa: E402
    UpsertResult,
    embed_chunks,
    make_allowlist_step,
    make_tombstone_step,
    make_upsert_step,
    promote_collection,
)


# --- Stubs --------------------------------------------------------------


class _EmbedItem:
    def __init__(self, vec: list[float]) -> None:
        self.embedding = vec


class _EmbedResp:
    def __init__(self, vecs: list[list[float]]) -> None:
        self.data = [_EmbedItem(v) for v in vecs]


class StubEmbedClient:
    """OpenAI-shaped stub that returns canned vectors per call."""

    def __init__(self, *, raises_on_calls: Optional[list[bool]] = None):
        self.calls: list[dict] = []
        self.raises_on_calls = raises_on_calls or []

    def create(self, *, model: str, input: list[str]) -> Any:
        idx = len(self.calls)
        self.calls.append({"model": model, "input": list(input)})
        if idx < len(self.raises_on_calls) and self.raises_on_calls[idx]:
            raise RuntimeError("simulated embed failure")
        # Return one deterministic vector per input string.
        return _EmbedResp([[float(idx + 1), float(len(t))] for t in input])


class StubWeaviate:
    """In-memory Weaviate-like store for upsert/tombstone tests."""

    def __init__(self) -> None:
        # collection -> {chunk_id: {properties, vector}}
        self._data: dict[str, dict[str, dict]] = {}
        self.gc_deleted = 0

    def upsert_chunk(
        self, *, collection: str, chunk_id: str,
        properties: dict, vector: list[float],
    ) -> None:
        self._data.setdefault(collection, {})[chunk_id] = {
            "properties": dict(properties),
            "vector": list(vector),
        }

    def get_chunk(
        self, *, collection: str, chunk_id: str,
    ) -> Optional[dict]:
        row = self._data.get(collection, {}).get(chunk_id)
        return row["properties"] if row else None

    def soft_delete_by_url(
        self, *, collection: str, urls: Iterable[str],
    ) -> list[str]:
        seen = set(urls)
        tombstoned: list[str] = []
        for chunk_id, row in self._data.get(collection, {}).items():
            url = row["properties"].get("source_url")
            if url and url not in seen and not row["properties"].get("deleted"):
                row["properties"]["deleted"] = True
                tombstoned.append(url)
        return tombstoned

    def gc_tombstones(
        self, *, collection: str, older_than: dt.datetime,
    ) -> int:
        # Stub returns whatever was set; tests configure it.
        return self.gc_deleted

    def count(self, *, collection: str) -> int:
        return len(self._data.get(collection, {}))


class StubUrlSeenStore:
    """Tracks upserts so tests can assert on the featured-URL set."""

    def __init__(self, return_count: int = 0):
        self.calls: list[dict] = []
        self.return_count = return_count

    def upsert_many(self, rows: list[dict], *, featured_urls: set[str]) -> int:
        self.calls.append({
            "rows": list(rows),
            "featured_urls": set(featured_urls),
        })
        return self.return_count


def _chunk(
    chunk_id: str = "c-1", source_url: str = "https://x/p",
    text: str = "hello world", content_hash: str = "h-1",
) -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        document_id="d-1",
        source_url=source_url,
        text=text,
        position=0,
        content_hash=content_hash,
        topic="spaces",
        campus="oxford",
        library="king",
        audience=["all"],
        featured_service=None,
    )


# --- embed_chunks ------------------------------------------------------


def test_embed_chunks_empty_returns_empty() -> None:
    out = embed_chunks([], StubEmbedClient(), model="text-embedding-3-large")
    assert out == []


def test_embed_chunks_returns_one_vector_per_chunk() -> None:
    chunks = [_chunk(chunk_id=f"c-{i}", text=f"t{i}") for i in range(3)]
    client = StubEmbedClient()
    out = embed_chunks(chunks, client, model="text-embedding-3-large", batch_size=10)
    assert len(out) == 3
    assert all(isinstance(v, list) and v for v in out)


def test_embed_chunks_batches() -> None:
    chunks = [_chunk(chunk_id=f"c-{i}", text=f"t{i}") for i in range(7)]
    client = StubEmbedClient()
    out = embed_chunks(chunks, client, model="text-embedding-3-large", batch_size=3)
    # 7 / 3 = 3 batches: 3 + 3 + 1.
    assert len(client.calls) == 3
    assert len(out) == 7


def test_embed_chunks_failure_pads_with_empty_vectors() -> None:
    """A batch that raises must NOT poison the run -- those positions
    get [] vectors so upsert can skip them, and OTHER batches still
    succeed."""
    chunks = [_chunk(chunk_id=f"c-{i}", text=f"t{i}") for i in range(6)]
    # 3 batches of 2; middle batch fails.
    client = StubEmbedClient(raises_on_calls=[False, True, False])
    out = embed_chunks(chunks, client, model="text-embedding-3-large", batch_size=2)
    assert len(out) == 6
    # Failed batch positions: 2, 3.
    assert out[0] and out[1]  # first batch succeeded
    assert out[2] == [] and out[3] == []  # failed batch
    assert out[4] and out[5]  # third batch succeeded


def test_embed_chunks_truncates_oversized_input() -> None:
    """Regression: if a chunk's text exceeds the embedding model's
    input limit (~32k chars / 8192 tokens), embed_chunks MUST truncate
    rather than send it as-is. The previous behavior caused OpenAI to
    400 the whole batch, silently dropping up to 100 chunks per
    oversized input. This is a second-layer defense; the chunker's
    CHUNK_HARD_MAX_TOKENS is the primary guard."""
    # 100k chars -> well above the 32k-ish embedding input cap.
    huge_text = "x" * 100_000
    chunks = [
        _chunk(chunk_id="c-small", text="hello"),
        _chunk(chunk_id="c-huge", text=huge_text),
    ]
    client = StubEmbedClient()
    out = embed_chunks(chunks, client, model="text-embedding-3-large", batch_size=10)
    # Batch succeeded (no padding-with-empties): both got real vectors.
    assert len(out) == 2
    assert out[0] and out[1]
    # The client saw a truncated string for the huge input, not 100k chars.
    sent_huge = client.calls[0]["input"][1]
    assert len(sent_huge) < 100_000
    assert len(sent_huge) <= 8192 * 4  # under the model's char-equivalent cap


# --- upsert step -------------------------------------------------------


def test_upsert_new_chunk_records_new() -> None:
    weaviate = StubWeaviate()
    step = make_upsert_step(weaviate)
    chunk = _chunk()
    result = step([chunk], [[0.1, 0.2]], version="20260507_0200")
    assert result.new_chunk_ids == ["c-1"]
    assert result.changed_chunk_ids == []
    assert result.deduped_chunk_ids == []
    # Wrote into the versioned collection.
    assert weaviate.get_chunk(collection="Chunk_v20260507_0200", chunk_id="c-1") is not None


def test_upsert_dedupes_unchanged_content_hash() -> None:
    weaviate = StubWeaviate()
    step = make_upsert_step(weaviate)
    chunk = _chunk()
    # First run -> new.
    step([chunk], [[0.1]], version="1")
    # Second run with SAME content_hash -> dedup.
    result = step([chunk], [[0.1]], version="1")
    assert result.new_chunk_ids == []
    assert result.deduped_chunk_ids == ["c-1"]


def test_upsert_records_change_when_content_hash_differs() -> None:
    weaviate = StubWeaviate()
    step = make_upsert_step(weaviate)
    step([_chunk(content_hash="h-1")], [[0.1]], version="1")
    # Same chunk_id, NEW content_hash (page text was updated).
    result = step(
        [_chunk(content_hash="h-2")], [[0.1]], version="1",
    )
    assert result.changed_chunk_ids == ["c-1"]
    assert result.new_chunk_ids == []


def test_upsert_skips_chunks_with_empty_vector() -> None:
    """Embedding-batch failures produce [] vectors. Upsert must NOT
    write those (would poison the index with zero-vector rows)."""
    weaviate = StubWeaviate()
    step = make_upsert_step(weaviate)
    chunks = [_chunk(chunk_id="c-1"), _chunk(chunk_id="c-2")]
    embeddings = [[0.1], []]  # second one failed
    result = step(chunks, embeddings, version="1")
    assert result.new_chunk_ids == ["c-1"]
    # c-2 was NOT written.
    assert weaviate.get_chunk(collection="Chunk_v1", chunk_id="c-2") is None


def test_upsert_writes_full_metadata() -> None:
    weaviate = StubWeaviate()
    step = make_upsert_step(weaviate)
    chunk = Chunk(
        chunk_id="c-9", document_id="d-9", source_url="https://x/p",
        text="body", position=2, content_hash="h-9",
        topic="spaces", campus="oxford", library="king",
        audience=["student", "faculty"], featured_service="makerspace",
    )
    step([chunk], [[0.1]], version="1")
    props = weaviate.get_chunk(collection="Chunk_v1", chunk_id="c-9")
    assert props is not None
    assert props["topic"] == "spaces"
    assert props["campus"] == "oxford"
    assert props["library"] == "king"
    assert props["audience"] == ["student", "faculty"]
    assert props["featured_service"] == "makerspace"
    assert props["deleted"] is False
    assert "ingested_at" in props


def test_upsert_total_count_set() -> None:
    weaviate = StubWeaviate()
    step = make_upsert_step(weaviate)
    chunks = [_chunk(chunk_id=f"c-{i}") for i in range(3)]
    embeddings = [[0.1]] * 3
    result = step(chunks, embeddings, version="1")
    assert result.total_chunks_in_index == 3


# --- tombstone step ----------------------------------------------------


def test_tombstone_marks_chunks_whose_url_is_not_in_seen() -> None:
    weaviate = StubWeaviate()
    upsert_step = make_upsert_step(weaviate)
    # Seed two chunks at two URLs.
    upsert_step(
        [
            _chunk(chunk_id="c-a", source_url="https://x/a"),
            _chunk(chunk_id="c-b", source_url="https://x/b"),
        ],
        [[0.1], [0.2]], version="1",
    )
    tomb_step = make_tombstone_step(weaviate)
    # Only x/a is in the seen-set this run.
    result = tomb_step({"https://x/a"}, version="1")
    assert "https://x/b" in result.tombstoned_urls
    assert "https://x/a" not in result.tombstoned_urls


def test_tombstone_already_seen_url_not_marked() -> None:
    weaviate = StubWeaviate()
    upsert_step = make_upsert_step(weaviate)
    upsert_step([_chunk(source_url="https://x/p")], [[0.1]], version="1")
    tomb_step = make_tombstone_step(weaviate)
    result = tomb_step({"https://x/p"}, version="1")
    assert result.tombstoned_urls == []


def test_tombstone_records_gc_count() -> None:
    weaviate = StubWeaviate()
    weaviate.gc_deleted = 17
    tomb_step = make_tombstone_step(weaviate)
    result = tomb_step(set(), version="1")
    assert result.gc_deleted_chunk_count == 17


# --- allowlist step ----------------------------------------------------


def test_allowlist_passes_through_count() -> None:
    store = StubUrlSeenStore(return_count=42)
    step = make_allowlist_step(store)
    out = step([("https://x/p", 200, "sitemap", "text/html")])
    assert out == 42


def test_allowlist_marks_featured_urls() -> None:
    """URLs matching FEATURED_SERVICE_PATTERNS get into the featured_urls
    set so the store can mark UrlSeen.priority='high'. Critical: these
    are the highest-value pages and must NOT be blackholed by transient
    sitemap glitches."""
    store = StubUrlSeenStore()
    step = make_allowlist_step(store)
    rows = [
        ("https://www.lib.miamioh.edu/use/spaces/makerspace/", 200, "sitemap", "text/html"),
        ("https://www.lib.miamioh.edu/about/contact-us/", 200, "sitemap", "text/html"),
    ]
    step(rows)
    call = store.calls[0]
    assert "https://www.lib.miamioh.edu/use/spaces/makerspace/" in call["featured_urls"]
    # Non-featured stays out of the set.
    assert "https://www.lib.miamioh.edu/about/contact-us/" not in call["featured_urls"]


def test_allowlist_passes_url_data_through() -> None:
    store = StubUrlSeenStore()
    step = make_allowlist_step(store)
    step([("https://x/p", 200, "sitemap", "text/html")])
    row = store.calls[0]["rows"][0]
    assert row["url"] == "https://x/p"
    assert row["http_status"] == 200
    assert row["source"] == "sitemap"
    assert row["content_type"] == "text/html"
    assert "last_seen" in row


def test_allowlist_empty_input_still_calls_store_with_empty_set() -> None:
    """The orchestrator might call this with an empty list (rare, but
    possible if all fetches failed). Must not crash."""
    store = StubUrlSeenStore(return_count=0)
    step = make_allowlist_step(store)
    out = step([])
    assert out == 0


# --- promote_collection ------------------------------------------------


def test_promote_collection_calls_swap_alias() -> None:
    class WeaviateWithAlias:
        def __init__(self) -> None:
            self.swap_args: dict = {}

        def swap_alias(self, *, alias: str, target: str) -> None:
            self.swap_args = {"alias": alias, "target": target}

    weaviate = WeaviateWithAlias()
    promote_collection(weaviate, version="20260507_0200")
    assert weaviate.swap_args == {
        "alias": "Chunk_current",
        "target": "Chunk_v20260507_0200",
    }


def test_promote_collection_raises_when_swap_alias_missing() -> None:
    """Without swap_alias support the operation can't be safely
    performed; we fail loud rather than silently doing nothing."""
    class NoAliasClient:
        pass

    try:
        promote_collection(NoAliasClient(), version="1")
    except NotImplementedError as e:
        assert "swap_alias" in str(e)
        return
    raise AssertionError("expected NotImplementedError")


# --- UpsertResult shape ------------------------------------------------


def test_upsert_result_default_empty_lists() -> None:
    r = UpsertResult()
    assert r.new_chunk_ids == []
    assert r.changed_chunk_ids == []
    assert r.deduped_chunk_ids == []
    assert r.tombstoned_urls == []
    assert r.gc_deleted_chunk_count == 0


def main() -> int:
    tests = [
        test_embed_chunks_empty_returns_empty,
        test_embed_chunks_returns_one_vector_per_chunk,
        test_embed_chunks_batches,
        test_embed_chunks_failure_pads_with_empty_vectors,
        test_embed_chunks_truncates_oversized_input,
        test_upsert_new_chunk_records_new,
        test_upsert_dedupes_unchanged_content_hash,
        test_upsert_records_change_when_content_hash_differs,
        test_upsert_skips_chunks_with_empty_vector,
        test_upsert_writes_full_metadata,
        test_upsert_total_count_set,
        test_tombstone_marks_chunks_whose_url_is_not_in_seen,
        test_tombstone_already_seen_url_not_marked,
        test_tombstone_records_gc_count,
        test_allowlist_passes_through_count,
        test_allowlist_marks_featured_urls,
        test_allowlist_passes_url_data_through,
        test_allowlist_empty_input_still_calls_store_with_empty_set,
        test_promote_collection_calls_swap_alias,
        test_promote_collection_raises_when_swap_alias_missing,
        test_upsert_result_default_empty_lists,
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
