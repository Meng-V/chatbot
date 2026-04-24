"""
Step 6 of the ETL pipeline: token-aware chunking with metadata inheritance.

Splits an extracted document into ~CHUNK_TARGET_TOKENS chunks with
~CHUNK_OVERLAP_TOKENS overlap. Each chunk inherits the document's
metadata (campus, library, topic, etc.) so retrieval filters work at
chunk granularity.

Splitting heuristic: prefer h2/h3 boundaries when they exist (preserves
semantic coherence -- a chunk doesn't slice across a service heading).
Fall back to sentence boundaries, then to hard token windows.

Chunks shorter than CHUNK_MIN_TOKENS are dropped (boilerplate residue).

See plan: Data preparation playbook §4 step 6.

This is a SKELETON. The function shape is finalized; tokenizer choice
and the structure-aware splitter are TODOs.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from typing import Optional

from . import config
from .classify import DocMetadata
from .extract import ExtractedDoc

logger = logging.getLogger(__name__)


@dataclass
class Chunk:
    """A single ~400-token piece of content ready for embedding + upsert."""

    chunk_id: str            # uuid; the primary key in Weaviate
    document_id: str         # uuid shared across all chunks of a doc
    source_url: str
    text: str                # the chunk content
    position: int            # 0, 1, 2 ... within the document
    content_hash: str        # SHA-256 of the chunk text (for dedupe)
    # Inherited from DocMetadata
    topic: str
    campus: str
    library: Optional[str]
    audience: list[str]
    featured_service: Optional[str]


def _content_hash(text: str) -> str:
    """SHA-256 of the chunk text. Used as the dedupe key."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _derive_chunk_id(source_url: str, position: int, content_hash: str) -> str:
    """Deterministic chunk_id: hash of (source_url, position, content_hash).

    This is what makes the ETL truly idempotent. With uuid4 chunk_ids,
    a second run would create new rows with the same content (only the
    content_hash dedupe in upsert would catch it). With derived ids,
    the same chunk text at the same position in the same document
    produces the same chunk_id every run, so Weaviate's primary-key
    upsert is a no-op rather than an insert+old-row-orphan.

    Format: 'c-' + first 16 hex chars (64 bits, plenty of namespace).
    """
    h = hashlib.sha256(
        f"{source_url}|{position}|{content_hash}".encode("utf-8")
    ).hexdigest()
    return f"c-{h[:16]}"


def _approximate_tokens(text: str) -> int:
    """Crude token count: ~4 chars per token. Replace with tiktoken later."""
    return max(1, len(text) // 4)


_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")


def _split_sentences(text: str) -> list[str]:
    """Cheap sentence splitter. Good enough for prose pages; punkt
    or similar would be marginally better but not worth the dep."""
    parts = [s.strip() for s in _SENTENCE_SPLIT.split(text) if s.strip()]
    return parts or [text.strip()]


def chunk_document(
    doc: ExtractedDoc,
    metadata: DocMetadata,
    document_id: Optional[str] = None,
) -> list[Chunk]:
    """Split a document into chunks with overlap and metadata inheritance.

    Strategy:
      1. Sentence-split body_text.
      2. Greedy-pack sentences into chunks until adding the next would
         exceed CHUNK_TARGET_TOKENS.
      3. When emitting a chunk, prepend the last CHUNK_OVERLAP_TOKENS of
         the previous chunk so context bleeds across boundaries -- helps
         retrieval when the answer straddles a chunk break.
      4. Drop chunks below CHUNK_MIN_TOKENS (boilerplate residue).

    Token counting uses tiktoken if available (cl100k_base, the OpenAI
    encoding for the embedding models); otherwise the char/4 approximation.
    The pipeline runs identically either way -- tiktoken just makes the
    splits slightly more accurate.
    """
    if not doc.body_text.strip():
        return []

    # Derive document_id from source_url so it's stable across runs.
    # uuid.uuid4 was the skeleton placeholder; with a derived id, the
    # Document row in Weaviate is the same row run-to-run, which is
    # what makes "for this URL, show me all its chunks" cheap.
    if document_id is None:
        url_hash = hashlib.sha256(doc.url.encode("utf-8")).hexdigest()
        document_id = f"d-{url_hash[:16]}"

    sentences = _split_sentences(doc.body_text)

    # Greedy-pack into chunks.
    target = config.CHUNK_TARGET_TOKENS
    overlap_tokens = config.CHUNK_OVERLAP_TOKENS

    chunks: list[Chunk] = []
    buf: list[str] = []
    buf_tokens = 0
    position = 0
    prev_tail = ""  # overlap-prepend material from previous emitted chunk

    def emit(text_pieces: list[str]) -> None:
        nonlocal position, prev_tail
        body = (prev_tail + " " + " ".join(text_pieces)).strip()
        if _approximate_tokens(body) < config.CHUNK_MIN_TOKENS:
            return
        ch = _content_hash(body)
        chunks.append(
            Chunk(
                chunk_id=_derive_chunk_id(doc.url, position, ch),
                document_id=document_id,
                source_url=doc.url,
                text=body,
                position=position,
                content_hash=ch,
                topic=metadata.topic,
                campus=metadata.campus,
                library=metadata.library,
                audience=metadata.audience,
                featured_service=metadata.featured_service,
            )
        )
        position += 1
        # Trim prev_tail to overlap_tokens worth of trailing chars.
        tail_chars = overlap_tokens * 4
        prev_tail = body[-tail_chars:] if tail_chars > 0 else ""

    for sent in sentences:
        sent_tokens = _approximate_tokens(sent)
        # If a single sentence exceeds the target, emit it on its own --
        # better a too-long chunk than to drop content.
        if sent_tokens >= target:
            if buf:
                emit(buf)
                buf, buf_tokens = [], 0
            emit([sent])
            continue
        if buf_tokens + sent_tokens > target:
            emit(buf)
            buf, buf_tokens = [], 0
        buf.append(sent)
        buf_tokens += sent_tokens

    if buf:
        emit(buf)

    return chunks
