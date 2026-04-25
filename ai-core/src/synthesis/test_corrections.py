"""
Unit tests for the ManualCorrection apply step.

Run: `python -m src.synthesis.test_corrections` from ai-core/.

apply_corrections() is the librarian's "fix it without a deploy" lever
(plan Op 2). Bugs here cause either:
  - Corrections silently no-op (librarian thinks they fixed it; bot
    keeps citing the bad URL) -> insidious; eroded trust.
  - Corrections wrongly fire (legit chunks get suppressed) -> corpus
    coverage shrinks invisibly.

Both are bad. Tests cover every action + every order rule.

Tests:
  1. Empty corrections list returns the bundle unchanged.
  2. blacklist_url drops every chunk with that source_url.
  3. suppress drops a chunk by chunk_id.
  4. replace edits chunk text + sets corrected_by.
  5. pin reorders a chunk to position 0 when the pattern matches.
  6. pin no-op when the pattern doesn't match the user_query.
  7. pin no-op when the target chunk isn't in the bundle (no inject).
  8. Order: blacklist runs before suppress (whole URL drop wins).
  9. Order: suppress runs before pin (pinning a suppressed chunk fails).
 10. Order: replace doesn't move the chunk; pin then can move it.
 11. Bad regex in pin.query_pattern is skipped gracefully.
 12. Multiple corrections firing on the same chunk all get logged.
 13. fired list is sorted (deterministic for snapshot logging).
 14. pin by URL (scope=url) works alongside pin by chunk (scope=chunk).
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running from ai-core/ as `python -m src.synthesis.test_corrections`.
_HERE = Path(__file__).resolve().parent
_AI_CORE = _HERE.parent.parent
sys.path.insert(0, str(_AI_CORE))

from src.synthesis.corrections import (  # noqa: E402
    EvidenceChunk,
    ManualCorrection,
    apply_corrections,
)


KING_URL = "https://www.lib.miamioh.edu/about/locations/king-library/"
WERTZ_URL = "https://www.lib.miamioh.edu/about/locations/art-arch/"
ILL_URL = "https://www.lib.miamioh.edu/use/borrow/ill/"


def _chunk(chunk_id: str, source_url: str = KING_URL, text: str = "default text") -> EvidenceChunk:
    return EvidenceChunk(
        chunk_id=chunk_id, source_url=source_url, text=text,
        campus="oxford", library="king",
    )


# --- Tests ----------------------------------------------------------------


def test_empty_corrections_returns_bundle_unchanged() -> None:
    chunks = [_chunk("c1"), _chunk("c2")]
    out = apply_corrections(chunks, [], "any query")
    assert out.chunks == chunks
    assert out.fired == []


def test_blacklist_url_drops_all_chunks_with_that_url() -> None:
    chunks = [
        _chunk("c1", source_url=KING_URL),
        _chunk("c2", source_url=KING_URL),
        _chunk("c3", source_url=WERTZ_URL),
    ]
    corr = [ManualCorrection(
        id=10, scope="url", target=KING_URL, action="blacklist_url",
    )]
    out = apply_corrections(chunks, corr, "q")
    assert [c.chunk_id for c in out.chunks] == ["c3"]
    assert out.fired == [10]


def test_suppress_drops_chunk_by_id() -> None:
    chunks = [_chunk("c1"), _chunk("c2"), _chunk("c3")]
    corr = [ManualCorrection(
        id=11, scope="chunk", target="c2", action="suppress",
    )]
    out = apply_corrections(chunks, corr, "q")
    assert [c.chunk_id for c in out.chunks] == ["c1", "c3"]
    assert out.fired == [11]


def test_replace_edits_text_and_marks_corrected_by() -> None:
    chunks = [_chunk("c1", text="STALE TEXT")]
    corr = [ManualCorrection(
        id=12, scope="chunk", target="c1", action="replace",
        replacement="FRESH TEXT",
        created_by="jane.librarian@miamioh.edu",
    )]
    out = apply_corrections(chunks, corr, "q")
    assert len(out.chunks) == 1
    assert out.chunks[0].text == "FRESH TEXT"
    assert out.chunks[0].corrected_by == "jane.librarian@miamioh.edu"
    assert out.fired == [12]


def test_pin_reorders_when_pattern_matches() -> None:
    chunks = [_chunk("c1"), _chunk("c2"), _chunk("c3-target")]
    corr = [ManualCorrection(
        id=13, scope="chunk", target="c3-target", action="pin",
        query_pattern=r"makerspace",
    )]
    out = apply_corrections(chunks, corr, "where is the MakerSpace?")
    assert out.chunks[0].chunk_id == "c3-target"
    assert out.fired == [13]


def test_pin_no_op_when_pattern_misses() -> None:
    chunks = [_chunk("c1"), _chunk("c2-target")]
    corr = [ManualCorrection(
        id=14, scope="chunk", target="c2-target", action="pin",
        query_pattern=r"adobe",
    )]
    out = apply_corrections(chunks, corr, "where is the makerspace?")
    # Original order preserved.
    assert [c.chunk_id for c in out.chunks] == ["c1", "c2-target"]
    assert out.fired == []


def test_pin_does_not_inject_unretrieved_chunk() -> None:
    """Pins boost rank; they don't synthesize chunks. If the pinned
    chunk_id wasn't in the retrieval bundle, the pin no-ops."""
    chunks = [_chunk("c1"), _chunk("c2")]
    corr = [ManualCorrection(
        id=15, scope="chunk", target="c-not-in-bundle", action="pin",
        query_pattern=r".*",  # always matches
    )]
    out = apply_corrections(chunks, corr, "anything")
    assert [c.chunk_id for c in out.chunks] == ["c1", "c2"]
    assert out.fired == []


def test_blacklist_runs_before_suppress() -> None:
    """When both fire on the same chunk, only the blacklist gets credit
    (the chunk is dropped at the first matching action; suppress doesn't
    re-fire on a chunk that's already gone)."""
    chunks = [_chunk("c1", source_url=KING_URL)]
    corr = [
        ManualCorrection(id=20, scope="url", target=KING_URL, action="blacklist_url"),
        ManualCorrection(id=21, scope="chunk", target="c1", action="suppress"),
    ]
    out = apply_corrections(chunks, corr, "q")
    assert out.chunks == []
    # Blacklist fired (it ran first); suppress did NOT (no chunk left to drop).
    assert out.fired == [20]


def test_suppress_beats_pin_for_same_chunk() -> None:
    """Pinning a suppressed chunk would resurrect it. Order rules
    forbid that: suppress runs first, pin runs against the survivors."""
    chunks = [_chunk("c1"), _chunk("c2")]
    corr = [
        ManualCorrection(id=30, scope="chunk", target="c2", action="suppress"),
        ManualCorrection(id=31, scope="chunk", target="c2", action="pin",
                         query_pattern=r".*"),
    ]
    out = apply_corrections(chunks, corr, "q")
    assert [c.chunk_id for c in out.chunks] == ["c1"]
    # Pin no-ops because c2 is gone after suppress.
    assert out.fired == [30]


def test_replace_then_pin_can_move_replaced_chunk() -> None:
    chunks = [_chunk("c1"), _chunk("c2", text="STALE")]
    corr = [
        ManualCorrection(id=40, scope="chunk", target="c2", action="replace",
                         replacement="FIXED", created_by="jane@x.edu"),
        ManualCorrection(id=41, scope="chunk", target="c2", action="pin",
                         query_pattern=r".*"),
    ]
    out = apply_corrections(chunks, corr, "q")
    assert out.chunks[0].chunk_id == "c2"
    assert out.chunks[0].text == "FIXED"
    assert out.chunks[0].corrected_by == "jane@x.edu"
    assert sorted(out.fired) == [40, 41]


def test_bad_regex_in_pin_pattern_skipped_gracefully() -> None:
    chunks = [_chunk("c1")]
    corr = [ManualCorrection(
        id=50, scope="chunk", target="c1", action="pin",
        query_pattern=r"[invalid(regex",  # unbalanced bracket
    )]
    # Must not raise -- librarian authoring errors are non-fatal.
    out = apply_corrections(chunks, corr, "q")
    assert [c.chunk_id for c in out.chunks] == ["c1"]
    assert out.fired == []


def test_fired_list_is_sorted() -> None:
    """Deterministic fired ordering is required for stable log/snapshot
    comparison and stable admin-dashboard counts."""
    chunks = [_chunk("c1"), _chunk("c2"), _chunk("c3")]
    corr = [
        ManualCorrection(id=99, scope="chunk", target="c1", action="suppress"),
        ManualCorrection(id=10, scope="chunk", target="c2", action="suppress"),
        ManualCorrection(id=50, scope="chunk", target="c3", action="suppress"),
    ]
    out = apply_corrections(chunks, corr, "q")
    assert out.fired == [10, 50, 99]


def test_pin_by_url_scope() -> None:
    chunks = [_chunk("c1", source_url=KING_URL),
              _chunk("c2", source_url=ILL_URL)]
    corr = [ManualCorrection(
        id=60, scope="url", target=ILL_URL, action="pin",
        query_pattern=r"interlibrary|ill",
    )]
    out = apply_corrections(chunks, corr, "how do I do interlibrary loan?")
    assert out.chunks[0].source_url == ILL_URL
    assert out.fired == [60]


def test_pin_by_url_scope_no_match() -> None:
    chunks = [_chunk("c1", source_url=KING_URL),
              _chunk("c2", source_url=ILL_URL)]
    corr = [ManualCorrection(
        id=61, scope="url", target=ILL_URL, action="pin",
        query_pattern=r"adobe",
    )]
    out = apply_corrections(chunks, corr, "where is the makerspace?")
    assert [c.source_url for c in out.chunks] == [KING_URL, ILL_URL]
    assert out.fired == []


def test_pin_pattern_case_insensitive() -> None:
    chunks = [_chunk("c1"), _chunk("c2-target")]
    corr = [ManualCorrection(
        id=70, scope="chunk", target="c2-target", action="pin",
        query_pattern=r"MAKERSPACE",
    )]
    out = apply_corrections(chunks, corr, "where is the makerspace?")
    assert out.chunks[0].chunk_id == "c2-target"
    assert out.fired == [70]


def main() -> int:
    tests = [
        test_empty_corrections_returns_bundle_unchanged,
        test_blacklist_url_drops_all_chunks_with_that_url,
        test_suppress_drops_chunk_by_id,
        test_replace_edits_text_and_marks_corrected_by,
        test_pin_reorders_when_pattern_matches,
        test_pin_no_op_when_pattern_misses,
        test_pin_does_not_inject_unretrieved_chunk,
        test_blacklist_runs_before_suppress,
        test_suppress_beats_pin_for_same_chunk,
        test_replace_then_pin_can_move_replaced_chunk,
        test_bad_regex_in_pin_pattern_skipped_gracefully,
        test_fired_list_is_sorted,
        test_pin_by_url_scope,
        test_pin_by_url_scope_no_match,
        test_pin_pattern_case_insensitive,
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
