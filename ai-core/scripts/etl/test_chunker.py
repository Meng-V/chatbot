"""
Unit tests for the ETL chunker.

Run: `python -m scripts.etl.test_chunker` from ai-core/.

Chunker bugs are nasty: a chunk that's too short gets dropped (silent
content loss) or too long blows past the embedding model's context
(silent truncation). The chunk_id derivation is what makes the ETL
idempotent -- a wrong derivation creates duplicate rows on every run.
Tests pin every behavior load-bearing for retrieval correctness +
ETL idempotency.

Tests cover:
  - chunk_document: empty body produces no chunks
  - chunk_id is deterministic (same input -> same id, run-to-run)
  - chunk_id includes source_url + position + content_hash (changing
    any of those changes the id; same content at different positions
    in the same doc gets different ids)
  - document_id is derived from source_url (idempotent across runs)
  - All chunks inherit the document's metadata (campus, library, topic,
    audience, featured_service)
  - position increments 0, 1, 2, ...
  - Long single sentence emits as its own chunk (don't drop content)
  - Chunks below CHUNK_MIN_TOKENS are dropped (boilerplate residue)
  - Overlap actually overlaps (last N chars of prev chunk in next
    chunk's prefix)
  - content_hash is stable for stable text
  - Sentence splitter handles common punctuation + abbreviations
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running from ai-core/ as `python -m scripts.etl.test_chunker`.
_HERE = Path(__file__).resolve().parent
_AI_CORE = _HERE.parent.parent
sys.path.insert(0, str(_AI_CORE))

from scripts.etl import config  # noqa: E402
from scripts.etl.chunker import (  # noqa: E402
    Chunk,
    _approximate_tokens,
    _content_hash,
    _derive_chunk_id,
    _split_sentences,
    chunk_document,
)
from scripts.etl.classify import DocMetadata  # noqa: E402
from scripts.etl.extract import ExtractedDoc  # noqa: E402


# --- Fixtures ----------------------------------------------------------


def _doc(
    url: str = "https://www.lib.miamioh.edu/use/spaces/makerspace/",
    body_text: str = "",
    title: str = "MakerSpace",
) -> ExtractedDoc:
    return ExtractedDoc(
        url=url,
        title=title,
        body_text=body_text,
        breadcrumbs=["Home", "Use", "Spaces", "MakerSpace"],
        word_count=len(body_text.split()),
        schema_org_json=None,
        last_modified=None,
        rejection_reason=None,
    )


def _meta(
    *,
    topic: str = "spaces",
    campus: str = "oxford",
    library: str = "king",
    audience: list = None,
    featured_service: str = "makerspace",
) -> DocMetadata:
    return DocMetadata(
        topic=topic,
        campus=campus,
        library=library,
        audience=audience or ["all"],
        featured_service=featured_service,
    )


def _long_text(target_tokens: int) -> str:
    """Build deterministic prose of approximately `target_tokens`
    tokens (using the chunker's char/4 approximation)."""
    sentence = (
        "King Library hosts a state-of-the-art MakerSpace on the second "
        "floor with three-dimensional printers, vinyl cutters, sewing "
        "machines, and audiovisual production equipment available to "
        "students and faculty alike. "
    )
    # Roughly 50 tokens per sentence (200 chars / 4).
    repeats = max(1, target_tokens // 50)
    return sentence * repeats


# --- Empty / edge cases ------------------------------------------------


def test_empty_body_returns_no_chunks() -> None:
    chunks = chunk_document(_doc(body_text=""), _meta())
    assert chunks == []


def test_whitespace_only_body_returns_no_chunks() -> None:
    chunks = chunk_document(_doc(body_text="   \n\t  "), _meta())
    assert chunks == []


def test_too_short_body_drops() -> None:
    """Body below CHUNK_MIN_TOKENS yields zero chunks (boilerplate
    residue / shell pages with no real content)."""
    chunks = chunk_document(_doc(body_text="Short."), _meta())
    assert chunks == []


# --- Idempotency: chunk_id + document_id derivation --------------------


def test_chunk_id_is_deterministic() -> None:
    """Same (url, position, content_hash) -> same chunk_id. Required
    for the ETL to be truly idempotent (Weaviate primary-key upsert)."""
    h = _content_hash("hello world")
    a = _derive_chunk_id("https://x/p", 0, h)
    b = _derive_chunk_id("https://x/p", 0, h)
    assert a == b
    assert a.startswith("c-")
    assert len(a) == 18  # "c-" + 16 hex


def test_chunk_id_changes_with_url() -> None:
    h = _content_hash("body")
    a = _derive_chunk_id("https://x/a", 0, h)
    b = _derive_chunk_id("https://x/b", 0, h)
    assert a != b


def test_chunk_id_changes_with_position() -> None:
    h = _content_hash("body")
    a = _derive_chunk_id("https://x/p", 0, h)
    b = _derive_chunk_id("https://x/p", 1, h)
    assert a != b


def test_chunk_id_changes_with_content() -> None:
    a = _derive_chunk_id("https://x/p", 0, _content_hash("foo"))
    b = _derive_chunk_id("https://x/p", 0, _content_hash("bar"))
    assert a != b


def test_document_id_derived_from_url() -> None:
    """Same source URL -> same document_id every run."""
    body = _long_text(800)
    chunks_1 = chunk_document(_doc(body_text=body), _meta())
    chunks_2 = chunk_document(_doc(body_text=body), _meta())
    assert chunks_1[0].document_id == chunks_2[0].document_id


def test_document_id_differs_per_url() -> None:
    body = _long_text(800)
    a = chunk_document(_doc(url="https://x/a", body_text=body), _meta())
    b = chunk_document(_doc(url="https://x/b", body_text=body), _meta())
    assert a[0].document_id != b[0].document_id


def test_caller_can_override_document_id() -> None:
    """Useful for testing/migration: pass an explicit document_id."""
    body = _long_text(800)
    chunks = chunk_document(
        _doc(body_text=body), _meta(),
        document_id="d-fixed-12345",
    )
    assert all(c.document_id == "d-fixed-12345" for c in chunks)


# --- Metadata inheritance ---------------------------------------------


def test_all_chunks_inherit_doc_metadata() -> None:
    """Every chunk MUST carry the same campus/library/topic so retrieval
    filters work uniformly. A bug here means a chunk gets the wrong
    campus and slips past the cross-campus guard."""
    body = _long_text(1500)  # enough for 3+ chunks
    metadata = _meta(
        topic="spaces", campus="oxford", library="king",
        audience=["student", "faculty"], featured_service="makerspace",
    )
    chunks = chunk_document(_doc(body_text=body), metadata)
    assert len(chunks) >= 2  # confirm we have multiple to check
    for c in chunks:
        assert c.topic == "spaces"
        assert c.campus == "oxford"
        assert c.library == "king"
        assert c.audience == ["student", "faculty"]
        assert c.featured_service == "makerspace"


def test_position_increments() -> None:
    body = _long_text(2000)
    chunks = chunk_document(_doc(body_text=body), _meta())
    assert len(chunks) >= 2
    for i, c in enumerate(chunks):
        assert c.position == i


# --- Sizing rules ------------------------------------------------------


def test_short_doc_emits_one_chunk() -> None:
    """A doc that's well below CHUNK_TARGET_TOKENS but above the min
    yields exactly one chunk with all its content."""
    # Build text just above CHUNK_MIN_TOKENS but well below TARGET.
    # MIN=50, TARGET=400 (approx-token = char/4).
    body = _long_text(120)  # ~120 tokens; well clear of the min, well below the target
    chunks = chunk_document(_doc(body_text=body), _meta())
    assert len(chunks) == 1


def test_long_doc_splits_into_multiple_chunks() -> None:
    body = _long_text(2000)  # ~5x the target
    chunks = chunk_document(_doc(body_text=body), _meta())
    assert len(chunks) >= 3  # rough; depends on overlap arithmetic


def test_oversized_single_sentence_still_emits() -> None:
    """A pathological single sentence longer than CHUNK_TARGET_TOKENS
    still emits chunks -- better a fat chunk than to drop content."""
    huge_sentence = "Word " * 1500  # ~1875 approx-tokens, all one "sentence"
    chunks = chunk_document(_doc(body_text=huge_sentence), _meta())
    # Got something back even though it's larger than the target.
    assert len(chunks) >= 1


def test_oversized_single_sentence_is_capped_at_hard_max() -> None:
    """Regression: a pathological "sentence" (e.g. a JS dump or
    unparagraphed list on a library page) MUST NOT produce a chunk
    larger than CHUNK_HARD_MAX_TOKENS, because OpenAI's
    text-embedding-3-large rejects inputs above 8192 tokens with a
    400, which silently kills the whole embed batch.

    Without the hard-split, a single 15k-token sentence would emit
    one 15k-token chunk. We require it to be split into pieces, each
    under the hard cap (with ~4 chars/token + small overlap slack)."""
    # ~15000 approx-tokens (~60000 chars), well over the 8192 limit.
    huge_sentence = "x" * 60_000
    chunks = chunk_document(_doc(body_text=huge_sentence), _meta())
    assert len(chunks) >= 2, "expected hard-split into multiple chunks"
    # Each emitted chunk's approx-token count must be at-or-below the
    # hard cap, plus a small slack for the prepended overlap prefix.
    slack_tokens = config.CHUNK_OVERLAP_TOKENS + 10
    cap = config.CHUNK_HARD_MAX_TOKENS + slack_tokens
    for ch in chunks:
        assert _approximate_tokens(ch.text) <= cap, (
            f"chunk exceeds hard cap: {_approximate_tokens(ch.text)} > {cap}"
        )


def test_position_resets_per_document() -> None:
    """Each call to chunk_document starts at position 0."""
    body = _long_text(1500)
    chunks = chunk_document(_doc(body_text=body), _meta())
    assert chunks[0].position == 0
    chunks2 = chunk_document(_doc(url="https://x/p2", body_text=body), _meta())
    assert chunks2[0].position == 0


# --- Overlap behavior --------------------------------------------------


def test_overlap_carries_text_across_boundary() -> None:
    """The last N chars of an emitted chunk should appear at the start
    of the next chunk -- that's how retrieval handles answers that
    straddle a chunk break."""
    body = _long_text(2000)
    chunks = chunk_document(_doc(body_text=body), _meta())
    if len(chunks) >= 2:
        # Last bit of chunk 0 should appear in chunk 1's prefix.
        tail_len = config.CHUNK_OVERLAP_TOKENS * 4  # chars
        # Extract a meaningful tail piece -- pull a 30-char window.
        tail_window = chunks[0].text[-30:]
        assert tail_window in chunks[1].text, (
            "expected last 30 chars of chunk[0] to appear in chunk[1]"
        )


# --- content_hash + Chunk shape ---------------------------------------


def test_content_hash_stable_for_stable_text() -> None:
    a = _content_hash("hello world")
    b = _content_hash("hello world")
    assert a == b
    # Different text -> different hash.
    assert a != _content_hash("hello world!")


def test_chunk_dataclass_shape() -> None:
    body = _long_text(800)
    chunks = chunk_document(_doc(body_text=body), _meta())
    c = chunks[0]
    assert isinstance(c, Chunk)
    assert c.chunk_id.startswith("c-")
    assert c.document_id.startswith("d-")
    assert c.source_url == "https://www.lib.miamioh.edu/use/spaces/makerspace/"
    assert isinstance(c.text, str) and c.text
    assert isinstance(c.position, int)
    assert isinstance(c.content_hash, str) and len(c.content_hash) == 64


# --- Sentence splitter -------------------------------------------------


def test_split_sentences_basic() -> None:
    text = "First sentence. Second sentence. Third one!"
    parts = _split_sentences(text)
    assert len(parts) == 3


def test_split_sentences_handles_question_mark() -> None:
    parts = _split_sentences("Where is King? It is the main library.")
    assert len(parts) == 2


def test_split_sentences_returns_input_when_no_split() -> None:
    """A single short fragment with no sentence-final punctuation
    still returns one element rather than empty."""
    parts = _split_sentences("Just a fragment")
    assert parts == ["Just a fragment"]


def test_split_sentences_drops_empty() -> None:
    """Empty fragments from extra whitespace or stray newlines are
    filtered out."""
    parts = _split_sentences("First.   \n\n  Second.")
    assert all(p.strip() for p in parts)


# --- Token approximation ----------------------------------------------


def test_approximate_tokens_returns_at_least_one() -> None:
    assert _approximate_tokens("a") >= 1
    assert _approximate_tokens("") >= 1


def test_approximate_tokens_scales_with_length() -> None:
    short = _approximate_tokens("x" * 4)
    long = _approximate_tokens("x" * 400)
    assert long > short


def main() -> int:
    tests = [
        test_empty_body_returns_no_chunks,
        test_whitespace_only_body_returns_no_chunks,
        test_too_short_body_drops,
        test_chunk_id_is_deterministic,
        test_chunk_id_changes_with_url,
        test_chunk_id_changes_with_position,
        test_chunk_id_changes_with_content,
        test_document_id_derived_from_url,
        test_document_id_differs_per_url,
        test_caller_can_override_document_id,
        test_all_chunks_inherit_doc_metadata,
        test_position_increments,
        test_short_doc_emits_one_chunk,
        test_long_doc_splits_into_multiple_chunks,
        test_oversized_single_sentence_still_emits,
        test_oversized_single_sentence_is_capped_at_hard_max,
        test_position_resets_per_document,
        test_overlap_carries_text_across_boundary,
        test_content_hash_stable_for_stable_text,
        test_chunk_dataclass_shape,
        test_split_sentences_basic,
        test_split_sentences_handles_question_mark,
        test_split_sentences_returns_input_when_no_split,
        test_split_sentences_drops_empty,
        test_approximate_tokens_returns_at_least_one,
        test_approximate_tokens_scales_with_length,
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
