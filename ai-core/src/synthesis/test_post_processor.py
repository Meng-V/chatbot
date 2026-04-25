"""
Unit tests for the load-bearing post-processor.

Run: `python -m src.synthesis.test_post_processor` from ai-core/.

The post_processor is the only thing standing between a fabricated URL
or a cross-campus citation leak and the user. The plan calls it
"non-negotiable" -- so test coverage is a release gate, not a nicety.

Tests cover every refusal path plus the happy path, in this order:
  1. Happy path -- medium confidence, valid citations, matching campus.
  2. Confidence=low -> MODEL_SELF_FLAGGED.
  3. Literal REFUSAL token in answer -> MODEL_SELF_FLAGGED.
  4. [n] in answer, n not in citations -> CITATION_INVALID.
  5. URL in answer not cited and not in allowlist -> CITATION_INVALID.
  6. URL in answer in allowlist (not cited) -> OK.
  7. URL in answer cited (not in allowlist) -> OK.
  8. URL trailing punctuation stripped before allowlist lookup.
  9. Cross-campus citation -> CROSS_CAMPUS_MISMATCH.
 10. campus="all" citation -> OK.
 11. Citation with no campus metadata -> CROSS_CAMPUS_MISMATCH (strict).
 12. Multiple failures -> priority order picks MODEL_SELF_FLAGGED first,
     then CITATION_INVALID, then CROSS_CAMPUS_MISMATCH.
 13. service_unavailable_trigger short-circuit -> SERVICE_NOT_AT_BUILDING.
 14. High-confidence + no citations (refusal-style answer) -> OK if no
     [n] and no URL fabrications, even though there's nothing cited.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running from ai-core/ as `python -m src.synthesis.test_post_processor`.
_HERE = Path(__file__).resolve().parent
_AI_CORE = _HERE.parent.parent
sys.path.insert(0, str(_AI_CORE))

from src.synthesis.post_processor import (  # noqa: E402
    Citation,
    SynthesizerOutput,
    process_synthesizer_output,
)
from src.synthesis.refusal_templates import (  # noqa: E402
    RefusalContext,
    RefusalTrigger,
)


KING_URL = "https://www.lib.miamioh.edu/about/locations/king-library/"
RENT_URL = "https://www.ham.miamioh.edu/library/"
MAKER_URL = "https://www.lib.miamioh.edu/use/spaces/makerspace/"


def _ok_oxford_citation(n: int = 1, url: str = KING_URL) -> Citation:
    return Citation(
        n=n, url=url, snippet="King is open Mon-Fri 7am-2am.",
        chunk_id=f"chunk-{n}", campus="oxford", library="king",
    )


def test_happy_path_returns_answer() -> None:
    out = SynthesizerOutput(
        answer="King opens at 7am [1].",
        citations=[_ok_oxford_citation()],
        confidence="high",
    )
    result = process_synthesizer_output(
        out, scope_campus="oxford", url_allowlist={KING_URL},
    )
    assert not result.is_refusal, f"unexpected refusal: {result.refusal}"
    assert result.answer is out


def test_confidence_low_refuses() -> None:
    out = SynthesizerOutput(
        answer="King opens at 7am [1].",
        citations=[_ok_oxford_citation()],
        confidence="low",
    )
    result = process_synthesizer_output(
        out, scope_campus="oxford", url_allowlist={KING_URL},
    )
    assert result.is_refusal
    assert result.refusal.trigger == RefusalTrigger.MODEL_SELF_FLAGGED


def test_literal_REFUSAL_token_refuses() -> None:
    out = SynthesizerOutput(
        answer="REFUSAL",
        citations=[],
        confidence="high",
    )
    result = process_synthesizer_output(
        out, scope_campus="oxford", url_allowlist=set(),
    )
    assert result.is_refusal
    assert result.refusal.trigger == RefusalTrigger.MODEL_SELF_FLAGGED


def test_unmatched_citation_number_refuses() -> None:
    out = SynthesizerOutput(
        # [2] referenced but only [1] is provided.
        answer="King opens at 7am [1] and closes at 2am [2].",
        citations=[_ok_oxford_citation(n=1)],
        confidence="high",
    )
    result = process_synthesizer_output(
        out, scope_campus="oxford", url_allowlist={KING_URL},
    )
    assert result.is_refusal
    assert result.refusal.trigger == RefusalTrigger.CITATION_INVALID
    assert any("don't exist in citations" in f.detail for f in result.refusal.failures)


def test_url_not_cited_not_in_allowlist_refuses() -> None:
    out = SynthesizerOutput(
        # URL fabricated -- not in any citation, not in allowlist.
        answer="See https://www.lib.miamioh.edu/fake-page/ for details.",
        citations=[],
        confidence="high",
    )
    result = process_synthesizer_output(
        out, scope_campus="oxford", url_allowlist={KING_URL},
    )
    assert result.is_refusal
    assert result.refusal.trigger == RefusalTrigger.CITATION_INVALID
    assert any("fake-page" in f.detail for f in result.refusal.failures)


def test_url_in_allowlist_not_cited_is_ok() -> None:
    """A bare URL the model includes is fine if the URL is in the
    allowlist (i.e. ETL has confirmed the page exists). This is the
    'point_to_url' tool's natural output shape."""
    out = SynthesizerOutput(
        answer="See King Library: " + KING_URL,
        citations=[],
        confidence="high",
    )
    result = process_synthesizer_output(
        out, scope_campus="oxford", url_allowlist={KING_URL},
    )
    assert not result.is_refusal


def test_url_cited_not_in_allowlist_is_ok() -> None:
    """If a URL is cited (so it came from a tool's evidence bundle), we
    don't second-guess the allowlist. The retrieval layer is the
    authority on what evidence chunks contain."""
    out = SynthesizerOutput(
        answer="King opens at 7am [1]. " + KING_URL,
        citations=[_ok_oxford_citation()],
        confidence="high",
    )
    # Empty allowlist on purpose.
    result = process_synthesizer_output(
        out, scope_campus="oxford", url_allowlist=set(),
    )
    assert not result.is_refusal


def test_url_trailing_punctuation_stripped() -> None:
    """Real prose: 'See https://x.com.' -- the trailing period is not
    part of the URL. Without strip, the allowlist check fails for valid
    URLs followed by sentence-ending punctuation."""
    out = SynthesizerOutput(
        answer=f"See ({KING_URL}). And also {KING_URL}, you'll find more.",
        citations=[],
        confidence="high",
    )
    result = process_synthesizer_output(
        out, scope_campus="oxford", url_allowlist={KING_URL},
    )
    assert not result.is_refusal, (
        "expected punctuation-trimmed URL to match allowlist; "
        f"refusal failures: {[f.detail for f in result.refusal.failures] if result.refusal else None}"
    )


def test_cross_campus_citation_refuses() -> None:
    """Bot is answering a Hamilton question but cited an Oxford chunk.
    Must refuse -- this is the King-hours-for-Hamilton failure mode."""
    out = SynthesizerOutput(
        answer="The library opens at 7am [1].",
        citations=[_ok_oxford_citation()],  # campus=oxford
        confidence="high",
    )
    result = process_synthesizer_output(
        out, scope_campus="hamilton", url_allowlist={KING_URL},
    )
    assert result.is_refusal
    assert result.refusal.trigger == RefusalTrigger.CROSS_CAMPUS_MISMATCH
    assert "Hamilton" in result.refusal.message  # rendered template


def test_campus_all_citation_is_ok() -> None:
    """A chunk tagged campus='all' (university-wide content like Adobe
    licensing) is allowed for any scope.campus."""
    universal = Citation(
        n=1, url=KING_URL, snippet="University-wide.",
        chunk_id="c", campus="all", library="all",
    )
    out = SynthesizerOutput(
        answer="Adobe is available [1].",
        citations=[universal],
        confidence="high",
    )
    result = process_synthesizer_output(
        out, scope_campus="hamilton", url_allowlist={KING_URL},
    )
    assert not result.is_refusal


def test_citation_without_campus_metadata_refuses_strict() -> None:
    """If the caller forgot to join campus metadata (a coding bug), we
    must NOT silently pass. The post_processor refuses with the
    cross-campus trigger so the bug is visible in production logs."""
    no_campus = Citation(
        n=1, url=KING_URL, snippet="...",
        chunk_id="c", campus=None, library=None,
    )
    out = SynthesizerOutput(
        answer="Hours are 7am [1].",
        citations=[no_campus],
        confidence="high",
    )
    result = process_synthesizer_output(
        out, scope_campus="oxford", url_allowlist={KING_URL},
    )
    assert result.is_refusal
    assert result.refusal.trigger == RefusalTrigger.CROSS_CAMPUS_MISMATCH
    assert any("no campus metadata" in f.detail for f in result.refusal.failures)


def test_priority_order_model_self_flag_wins() -> None:
    """When BOTH confidence=low AND a fabricated URL are present, the
    user-facing trigger is MODEL_SELF_FLAGGED (severity priority)."""
    out = SynthesizerOutput(
        answer="See https://fake-url.example/ for hours.",
        citations=[],
        confidence="low",  # also self-flagged
    )
    result = process_synthesizer_output(
        out, scope_campus="oxford", url_allowlist={KING_URL},
    )
    assert result.is_refusal
    assert result.refusal.trigger == RefusalTrigger.MODEL_SELF_FLAGGED
    # But both failures were logged for debugging.
    triggers_logged = {f.trigger for f in result.refusal.failures}
    assert RefusalTrigger.MODEL_SELF_FLAGGED in triggers_logged
    assert RefusalTrigger.CITATION_INVALID in triggers_logged


def test_priority_order_citation_beats_cross_campus() -> None:
    """When citation is fabricated AND remaining citations are cross-
    campus, the citation refusal wins (citation invalid is more
    fundamental than scope mismatch)."""
    cross_campus_cite = Citation(
        n=1, url=RENT_URL, snippet="Rentschler info.",
        chunk_id="c", campus="hamilton", library="rentschler",
    )
    out = SynthesizerOutput(
        # [2] doesn't exist; [1] is cross-campus from oxford scope.
        answer="See [1] and [2].",
        citations=[cross_campus_cite],
        confidence="high",
    )
    result = process_synthesizer_output(
        out, scope_campus="oxford", url_allowlist={RENT_URL},
    )
    assert result.is_refusal
    assert result.refusal.trigger == RefusalTrigger.CITATION_INVALID


def test_service_unavailable_short_circuits() -> None:
    """If the agent already determined the requested service isn't
    offered at this campus (LibrarySpace.services_offered check), the
    post_processor refuses immediately without running any other check."""
    ctx = RefusalContext(
        campus_display="Hamilton",
        service_name="MakerSpace",
        service_available_at="King Library on the Oxford campus",
    )
    out = SynthesizerOutput(
        answer="The MakerSpace at Hamilton has 3D printers [1].",  # would otherwise pass
        citations=[_ok_oxford_citation()],
        confidence="high",
    )
    result = process_synthesizer_output(
        out, scope_campus="hamilton", url_allowlist={KING_URL},
        service_unavailable_trigger=ctx,
    )
    assert result.is_refusal
    assert result.refusal.trigger == RefusalTrigger.SERVICE_NOT_AT_BUILDING
    assert "MakerSpace" in result.refusal.message
    assert "Hamilton" in result.refusal.message


def test_no_citations_no_urls_high_confidence_is_ok() -> None:
    """A pure prose answer with no URLs and no [n] markers passes -- no
    citations to validate, no URLs to check, scope check has nothing to
    look at. (Real synthesizer answers should always cite, but this
    edge case must not crash the validator.)"""
    out = SynthesizerOutput(
        answer="The library has many resources for students.",
        citations=[],
        confidence="medium",
    )
    result = process_synthesizer_output(
        out, scope_campus="oxford", url_allowlist=set(),
    )
    assert not result.is_refusal


def test_multiple_urls_all_cited_is_ok() -> None:
    out = SynthesizerOutput(
        answer=f"King hours [1] are at {KING_URL} and the MakerSpace [2] is at {MAKER_URL}.",
        citations=[
            _ok_oxford_citation(n=1, url=KING_URL),
            _ok_oxford_citation(n=2, url=MAKER_URL),
        ],
        confidence="high",
    )
    result = process_synthesizer_output(
        out, scope_campus="oxford", url_allowlist=set(),
    )
    assert not result.is_refusal


def main() -> int:
    tests = [
        test_happy_path_returns_answer,
        test_confidence_low_refuses,
        test_literal_REFUSAL_token_refuses,
        test_unmatched_citation_number_refuses,
        test_url_not_cited_not_in_allowlist_refuses,
        test_url_in_allowlist_not_cited_is_ok,
        test_url_cited_not_in_allowlist_is_ok,
        test_url_trailing_punctuation_stripped,
        test_cross_campus_citation_refuses,
        test_campus_all_citation_is_ok,
        test_citation_without_campus_metadata_refuses_strict,
        test_priority_order_model_self_flag_wins,
        test_priority_order_citation_beats_cross_campus,
        test_service_unavailable_short_circuits,
        test_no_citations_no_urls_high_confidence_is_ok,
        test_multiple_urls_all_cited_is_ok,
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
