"""
Apply active ManualCorrection rows to the retrieval bundle BEFORE
synthesis.

The correction workflow (plan Op 2) lets librarians fix wrong answers
without a deploy. A correction is a row in the Postgres
ManualCorrection table; this module reads the *already-fetched* active
rows (the caller does the DB query) and rewrites the evidence bundle:

  suppress       -- drop a chunk by chunk_id
  blacklist_url  -- drop every chunk whose source_url is blacklisted
  replace        -- substitute chunk text with the librarian's version
  pin            -- if user query matches query_pattern, boost a chunk
                    to rank 1

Why here and not inside retrieval? Because corrections are a post-
retrieval editorial step, conceptually closer to synthesis than to
vector search. Keeping them out of the retriever means the retriever's
fan-out / filter / rerank logic stays test-covered by pure retrieval
cases, and the corrections layer stays test-covered by pure correction
cases.

See plan:
  - Operations -> Op 2 "Content correction workflow"
  - ManualCorrection schema in plan's Critical files section
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from typing import Literal, Optional


CorrectionAction = Literal["suppress", "replace", "pin", "blacklist_url"]
CorrectionScope = Literal["url", "chunk", "intent", "global"]


@dataclass(frozen=True)
class ManualCorrection:
    """An active correction row, denormalized to what apply_corrections
    actually needs. Caller loads from Postgres ManualCorrection table
    filtered by `active=true AND expires_at > now()`.
    """

    id: int
    scope: CorrectionScope
    target: str
    """url, chunk_id, intent name, or `*` (for scope=global)."""

    action: CorrectionAction
    replacement: Optional[str] = None
    """For action=replace: the librarian-written substitute text."""

    query_pattern: Optional[str] = None
    """For action=pin: regex against user query. Compiled fresh per
    call (rarely fires, don't bother caching)."""

    reason: str = ""
    created_by: str = ""


@dataclass(frozen=True)
class EvidenceChunk:
    """One evidence-bundle item passed from retrieval to synthesis.

    This shape is what the synthesizer consumes; retrieval returns a
    list of these and corrections may edit / drop / reorder them.
    """

    chunk_id: str
    source_url: str
    text: str
    campus: Optional[str] = None
    library: Optional[str] = None
    topic: Optional[str] = None
    featured_service: Optional[str] = None
    score: float = 0.0
    corrected_by: Optional[str] = None
    """Set by a `replace` correction -- surfaced to the UI citation
    chip so users see the text they're reading was librarian-edited."""


@dataclass(frozen=True)
class CorrectionOutcome:
    """What `apply_corrections()` returns: the rewritten bundle plus
    a record of which corrections fired. The fired list is logged and
    shown on the admin dashboard (Op 2 fire-count metric).
    """

    chunks: list[EvidenceChunk] = field(default_factory=list)
    fired: list[int] = field(default_factory=list)
    """IDs of ManualCorrection rows that modified this bundle."""


def apply_corrections(
    chunks: list[EvidenceChunk],
    corrections: list[ManualCorrection],
    user_query: str,
) -> CorrectionOutcome:
    """Rewrite the retrieval bundle with any matching corrections.

    Order of application is fixed and matters:
      1. blacklist_url   -- strictest; drops whole URLs
      2. suppress        -- drops by chunk_id
      3. replace         -- edits text in place
      4. pin             -- reorders (must come last so we don't pin
                            a chunk that a later suppress would drop)

    Args:
        chunks: Evidence as returned from retrieval, ranked.
        corrections: Active ManualCorrection rows (caller pre-filters
            `active=true AND expires_at > now()`).
        user_query: Raw user message, used to match `pin` query_pattern.

    Returns:
        CorrectionOutcome with the rewritten chunk list and the ids of
        corrections that actually fired.
    """
    fired: set[int] = set()

    # Partition corrections by action so we apply in the fixed order.
    blacklist_urls = {c.target for c in corrections if c.action == "blacklist_url"}
    suppress_chunks = {c.target for c in corrections if c.action == "suppress"}
    replacements = {
        c.target: c
        for c in corrections
        if c.action == "replace" and c.replacement is not None
    }
    pins = [c for c in corrections if c.action == "pin"]

    result: list[EvidenceChunk] = []
    for chunk in chunks:
        # 1. blacklist_url
        if chunk.source_url in blacklist_urls:
            for c in corrections:
                if c.action == "blacklist_url" and c.target == chunk.source_url:
                    fired.add(c.id)
            continue

        # 2. suppress
        if chunk.chunk_id in suppress_chunks:
            for c in corrections:
                if c.action == "suppress" and c.target == chunk.chunk_id:
                    fired.add(c.id)
            continue

        # 3. replace
        if chunk.chunk_id in replacements:
            repl = replacements[chunk.chunk_id]
            chunk = replace(
                chunk,
                text=repl.replacement or chunk.text,
                corrected_by=repl.created_by or "librarian",
            )
            fired.add(repl.id)

        result.append(chunk)

    # 4. pin (rank-1 boost)
    # Pins are applied after the above so we never pin something a
    # suppress would have dropped. If the pinned chunk isn't in the
    # current bundle, the pin is a no-op -- pins boost, they don't
    # inject. Injecting unretrieved chunks would undermine the
    # retrieval signal and confuse debugging.
    for pin in pins:
        if pin.query_pattern is None:
            continue
        try:
            pat = re.compile(pin.query_pattern, re.IGNORECASE)
        except re.error:
            # Bad regex is a librarian authoring error; skip gracefully
            # and let the admin UI's validation catch it next time.
            continue
        if not pat.search(user_query):
            continue
        # Find the pinned chunk by target chunk_id (scope=chunk) or by
        # source_url (scope=url). Move it to position 0 if present.
        for i, chunk in enumerate(result):
            if pin.scope == "chunk" and chunk.chunk_id == pin.target:
                result.insert(0, result.pop(i))
                fired.add(pin.id)
                break
            if pin.scope == "url" and chunk.source_url == pin.target:
                result.insert(0, result.pop(i))
                fired.add(pin.id)
                break

    return CorrectionOutcome(chunks=result, fired=sorted(fired))


__all__ = [
    "CorrectionAction",
    "CorrectionOutcome",
    "CorrectionScope",
    "EvidenceChunk",
    "ManualCorrection",
    "apply_corrections",
]
