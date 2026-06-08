"""
Unit tests for synthesizer pure functions: prompt construction +
response parsing.

Run: `python -m src.synthesis.test_synthesizer` from ai-core/.

The LLM call itself (`synthesize`) is gated on the live OpenAI client
wiring per the model freshness rule, so it's not tested here. What IS
tested is the load-bearing pure logic around the LLM call:

  - _format_evidence_block: numbered evidence with metadata
  - _build_dynamic_suffix: scope + sources + question, in that order
  - parse_synthesizer_response: joins citation `n` back to chunk
    metadata so the post-processor's cross-campus check has the data
    it needs to enforce the contract.

A bug in parse_synthesizer_response is the worst kind: the model output
is correct, the post-processor logic is correct, but the join in the
middle drops the campus metadata -- and every cross-campus citation
silently passes the guard. Tests here lock that boundary.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running from ai-core/ as `python -m src.synthesis.test_synthesizer`.
_HERE = Path(__file__).resolve().parent
_AI_CORE = _HERE.parent.parent
sys.path.insert(0, str(_AI_CORE))

from src.synthesis.corrections import EvidenceChunk  # noqa: E402
from src.synthesis.synthesizer import (  # noqa: E402
    _build_dynamic_suffix,
    _format_evidence_block,
    parse_synthesizer_response,
)


def _ev(chunk_id: str, source_url: str = "https://x.com/", **kw) -> EvidenceChunk:
    return EvidenceChunk(chunk_id=chunk_id, source_url=source_url,
                         text=kw.get("text", "default"),
                         campus=kw.get("campus", "oxford"),
                         library=kw.get("library", "king"),
                         topic=kw.get("topic"),
                         featured_service=kw.get("featured_service"),
                         kind=kw.get("kind", "crawled"))


# --- _format_evidence_block ---


def test_format_empty_evidence_returns_no_evidence_marker() -> None:
    assert _format_evidence_block([]) == "(no evidence)"


def test_format_single_chunk_uses_1_indexed_number() -> None:
    blk = _format_evidence_block([_ev("c1", text="hello world")])
    # 1-indexed because users see [1] in the UI.
    assert blk.startswith("[1]")
    assert "hello world" in blk


def test_format_multiple_chunks_separated_by_blank_lines() -> None:
    blk = _format_evidence_block([
        _ev("c1", text="first"),
        _ev("c2", text="second"),
    ])
    assert "[1]" in blk
    assert "[2]" in blk
    assert "\n\n" in blk
    assert blk.index("[1]") < blk.index("[2]")


def test_format_truncates_long_snippets() -> None:
    long_text = "x" * 1000
    blk = _format_evidence_block([_ev("c1", text=long_text)])
    # Truncated to 600 chars (then "..." appended -> 600 char body).
    # Find the snippet portion.
    assert "..." in blk
    # The truncated text shouldn't be the full 1000 chars.
    assert long_text not in blk


def test_format_replaces_internal_newlines_with_spaces() -> None:
    blk = _format_evidence_block([_ev("c1", text="line one\nline two")])
    # Snippet line should not contain a stray newline (the only
    # newlines in the block are structural).
    snippet_line = [l for l in blk.split("\n") if "line one" in l][0]
    assert "line two" in snippet_line, "internal newline should have become a space"


def test_format_emits_metadata_when_present() -> None:
    blk = _format_evidence_block([_ev("c1", topic="hours")])
    assert "library=king" in blk
    assert "campus=oxford" in blk
    assert "topic=hours" in blk


def test_format_omits_metadata_block_when_empty() -> None:
    chunk = EvidenceChunk(chunk_id="c1", source_url="https://x.com/",
                          text="abc", campus=None, library=None, topic=None)
    blk = _format_evidence_block([chunk])
    assert "library=" not in blk
    assert "campus=" not in blk
    # No empty `[]` either.
    assert "[1] []" not in blk
    assert blk.startswith("[1] https://x.com/")


# --- _build_dynamic_suffix ---


def test_dynamic_suffix_order_is_scope_sources_question() -> None:
    """Order matters: model treats the question (last) as the most
    recent instruction. Reordering would change behavior + tank cache
    consistency for the dynamic portion."""
    suffix = _build_dynamic_suffix(
        question="What time?",
        evidence=[_ev("c1", text="hello")],
        scope_campus="oxford",
        scope_library="king",
    )
    # Scope appears first.
    assert suffix.index("Scope:") < suffix.index("Sources:")
    # Sources appear before question.
    assert suffix.index("Sources:") < suffix.index("User question:")
    # Question is last.
    assert suffix.endswith("User question: What time?")


def test_dynamic_suffix_omits_library_from_scope_line_when_null() -> None:
    """Scope line should be 'Scope: campus=X' (no library) when
    scope_library is null. Chunk metadata may still mention library
    (that's the chunk's own provenance, separate from scope)."""
    # Use a chunk with library=None so the test isn't confused by chunk metadata.
    chunk = EvidenceChunk(chunk_id="c1", source_url="https://x/", text="t",
                          campus="oxford", library=None)
    suffix = _build_dynamic_suffix(
        question="q", evidence=[chunk],
        scope_campus="oxford", scope_library=None,
    )
    scope_line = [l for l in suffix.split("\n") if l.startswith("Scope:")][0]
    assert "library=" not in scope_line
    assert "campus=oxford" in scope_line


def test_dynamic_suffix_includes_library_when_set() -> None:
    suffix = _build_dynamic_suffix(
        question="q", evidence=[_ev("c1")],
        scope_campus="hamilton", scope_library="rentschler",
    )
    assert "campus=hamilton" in suffix
    assert "library=rentschler" in suffix


# --- parse_synthesizer_response ---


def test_parse_basic_response() -> None:
    raw = {
        "answer": "King opens at 7am [1].",
        "citations": [{"n": 1, "url": "https://lib.miamioh.edu/king/", "snippet": "Hours..."}],
        "confidence": "high",
    }
    evidence = [_ev("chunk-king", source_url="https://lib.miamioh.edu/king/")]
    out = parse_synthesizer_response(raw, evidence)
    assert out.answer == "King opens at 7am [1]."
    assert out.confidence == "high"
    assert len(out.citations) == 1
    c = out.citations[0]
    assert c.n == 1
    assert c.url == "https://lib.miamioh.edu/king/"
    # CRITICAL: campus joined back from evidence so post-processor can check.
    assert c.campus == "oxford"
    assert c.library == "king"
    assert c.chunk_id == "chunk-king"


def test_parse_joins_campus_metadata_from_evidence() -> None:
    """The load-bearing join: citation [n] indexes back into the
    evidence list to get campus/library. Bug here = silent
    cross-campus leak even though post_processor logic is correct."""
    raw = {
        "answer": "[2]",
        "citations": [{"n": 2, "url": "https://x", "snippet": "..."}],
        "confidence": "high",
    }
    evidence = [
        _ev("oxford-c", campus="oxford", library="king"),
        _ev("hamilton-c", campus="hamilton", library="rentschler"),
    ]
    out = parse_synthesizer_response(raw, evidence)
    # n=2 -> evidence[1] -> hamilton citation
    assert out.citations[0].campus == "hamilton"
    assert out.citations[0].library == "rentschler"


def test_parse_out_of_range_citation_keeps_campus_none() -> None:
    """If the model emits [99] but only 2 chunks exist, the citation
    is preserved with campus=None so the post-processor's strict
    'no campus metadata' check fires (CROSS_CAMPUS_MISMATCH refusal).
    Failing loud > silently dropping the citation."""
    raw = {
        "answer": "See [99].",
        "citations": [{"n": 99, "url": "https://made-up", "snippet": ""}],
        "confidence": "high",
    }
    evidence = [_ev("c1"), _ev("c2")]
    out = parse_synthesizer_response(raw, evidence)
    assert len(out.citations) == 1
    assert out.citations[0].n == 99
    assert out.citations[0].campus is None
    assert out.citations[0].chunk_id is None


def test_parse_missing_url_falls_back_to_chunk_url() -> None:
    """Belt and suspenders: if the model forgets to emit a URL on a
    citation, fall back to the cited chunk's source_url. Beats
    dropping the whole citation."""
    raw = {
        "answer": "[1]",
        "citations": [{"n": 1, "snippet": "..."}],  # no url field
        "confidence": "high",
    }
    evidence = [_ev("c1", source_url="https://lib.miamioh.edu/king/")]
    out = parse_synthesizer_response(raw, evidence)
    assert out.citations[0].url == "https://lib.miamioh.edu/king/"


def test_parse_backfills_orphan_marker_from_evidence() -> None:
    """REGRESSION: the synthesizer LLM intermittently writes an `[n]`
    marker but returns an empty citations[] (observed on the hours
    intent). The orphan marker rendered an un-clickable `[1]` in the UI
    and the post-processor would refuse an otherwise-correct answer.
    parse_synthesizer_response must reconstruct the citation from the
    positional evidence chunk it points at -- url + campus + library so
    the chip is clickable AND the cross-campus guard still has metadata."""
    raw = {
        "answer": "King Library closes today at 9:00pm [1].",
        "citations": [],  # <- model omitted it
        "confidence": "high",
    }
    evidence = [_ev("tool:get_hours:king",
                    source_url="https://www.lib.miamioh.edu/about/locations/hours/",
                    text="King Library Hours: Monday 7:30am to 9:00pm",
                    campus="oxford", library="king")]
    out = parse_synthesizer_response(raw, evidence)
    assert len(out.citations) == 1, "orphan [1] not back-filled"
    c = out.citations[0]
    assert c.n == 1
    assert c.url == "https://www.lib.miamioh.edu/about/locations/hours/"
    assert c.snippet  # snippet derived from evidence text, non-empty
    # Cross-campus guard needs these; a None campus would force a refusal.
    assert c.campus == "oxford"
    assert c.library == "king"
    assert c.chunk_id == "tool:get_hours:king"


def test_parse_live_api_citation_gets_honest_snippet_not_page_quote() -> None:
    """Option-1 honest-snippet: a LIVE-API citation (hours) must NOT
    echo the API value as if it were a verbatim page quote. The chip
    text is labeled as live, and the URL still points at the canonical
    page for verification. Applies whether the model filled the
    citation or it was back-filled."""
    hours_ev = _ev("tool:get_hours:king",
                   source_url="https://www.lib.miamioh.edu/about/locations/hours/",
                   text="King Library Hours: Monday 7:30am to 9:00pm",
                   kind="live_api")
    # (a) model filled the citation with the API string as snippet:
    raw_filled = {
        "answer": "Closes 9pm [1].",
        "citations": [{"n": 1, "url": hours_ev.source_url,
                       "snippet": "King Library Hours: Monday 7:30am to 9:00pm"}],
        "confidence": "high",
    }
    c = parse_synthesizer_response(raw_filled, [hours_ev]).citations[0]
    assert "LibCal" in c.snippet and "real-time" in c.snippet.lower()
    assert "7:30am" not in c.snippet  # API value NOT masquerading as a quote
    assert c.url == "https://www.lib.miamioh.edu/about/locations/hours/"
    # (b) back-filled orphan marker -> same honest snippet:
    raw_orphan = {"answer": "Closes 9pm [1].", "citations": [], "confidence": "high"}
    c2 = parse_synthesizer_response(raw_orphan, [hours_ev]).citations[0]
    assert "LibCal" in c2.snippet


def test_parse_prose_citation_keeps_real_excerpt() -> None:
    """Counterpart: a CRAWLED (prose) citation keeps the model's real
    excerpt -- the honest-snippet relabel is live-API-only."""
    prose_ev = _ev("chunk-ill", source_url="https://lib/ill/",
                   text="Interlibrary loan lets you borrow from other libraries.",
                   kind="crawled")
    raw = {
        "answer": "ILL [1].",
        "citations": [{"n": 1, "url": "https://lib/ill/",
                       "snippet": "Interlibrary loan lets you borrow"}],
        "confidence": "high",
    }
    c = parse_synthesizer_response(raw, [prose_ev]).citations[0]
    assert c.snippet == "Interlibrary loan lets you borrow"  # untouched


def test_parse_backfill_does_not_duplicate_existing_citation() -> None:
    """If the model already cited [1], the back-fill must not add a
    second [1]."""
    raw = {
        "answer": "Open till 9pm [1].",
        "citations": [{"n": 1, "url": "https://lib/hours/", "snippet": "s"}],
        "confidence": "high",
    }
    out = parse_synthesizer_response(raw, [_ev("c1", source_url="https://lib/hours/")])
    assert len(out.citations) == 1
    assert out.citations[0].url == "https://lib/hours/"  # model's, not overwritten


def test_parse_backfill_skips_out_of_range_marker() -> None:
    """An `[5]` marker with only 1 evidence chunk must NOT be
    reconstructed (there's nothing authoritative to point at). Leaving
    it absent lets the post-processor's CITATION_INVALID guard refuse,
    which is the correct outcome for a fabricated reference."""
    raw = {"answer": "See [5].", "citations": [], "confidence": "high"}
    out = parse_synthesizer_response(raw, [_ev("c1")])
    assert out.citations == []


def test_parse_backfill_multiple_orphans_sorted_by_n() -> None:
    """Two evidence chunks, model writes [2] then [1], omits both
    citations. Both get back-filled, sorted ascending by n."""
    raw = {
        "answer": "Wertz [2] and King [1] both open.",
        "citations": [],
        "confidence": "high",
    }
    evidence = [
        _ev("king-c", source_url="https://lib/king/", library="king"),
        _ev("wertz-c", source_url="https://lib/wertz/", library="wertz"),
    ]
    out = parse_synthesizer_response(raw, evidence)
    assert [c.n for c in out.citations] == [1, 2]
    assert out.citations[0].url == "https://lib/king/"
    assert out.citations[1].url == "https://lib/wertz/"


def test_parse_defaults_confidence_to_medium() -> None:
    """When the model forgets the confidence field, default to medium
    (NOT high). Prevents accidental skipping of the confidence gate."""
    raw = {"answer": "ok", "citations": []}
    out = parse_synthesizer_response(raw, [])
    assert out.confidence == "medium"


def test_parse_empty_citations() -> None:
    raw = {"answer": "no sources answer", "citations": [], "confidence": "low"}
    out = parse_synthesizer_response(raw, [])
    assert out.citations == []
    assert out.confidence == "low"


def main() -> int:
    tests = [
        test_format_empty_evidence_returns_no_evidence_marker,
        test_format_single_chunk_uses_1_indexed_number,
        test_format_multiple_chunks_separated_by_blank_lines,
        test_format_truncates_long_snippets,
        test_format_replaces_internal_newlines_with_spaces,
        test_format_emits_metadata_when_present,
        test_format_omits_metadata_block_when_empty,
        test_dynamic_suffix_order_is_scope_sources_question,
        test_dynamic_suffix_omits_library_from_scope_line_when_null,
        test_dynamic_suffix_includes_library_when_set,
        test_parse_basic_response,
        test_parse_joins_campus_metadata_from_evidence,
        test_parse_out_of_range_citation_keeps_campus_none,
        test_parse_missing_url_falls_back_to_chunk_url,
        test_parse_defaults_confidence_to_medium,
        test_parse_empty_citations,
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
