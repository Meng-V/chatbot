"""
Unit tests for the LLM-as-judge module.

Run: `python -m src.eval.test_judge` from ai-core/.

The judge is the eval suite's automated scorer for "answer correctness"
per plan §verification 2. Bugs here mean every regression metric is
suspect:
  - Verdict misparsing -> right-but-malformed judge calls counted as wrong
  - Aggregate math wrong -> the correct_rate gate fires false
  - Citation validity rollup wrong -> the citation-validity gate fires false

Tests cover:
  1. Prompt suffix shape (order matches the rubric the judge expects)
  2. Verdict parsing happy path
  3. Verdict parsing rejects unknown labels (don't silently coerce)
  4. Verdict parsing rejects bad JSON / wrong type
  5. judge_answer() integration with an injectable stub
  6. aggregate_verdicts() math, including empty-list edge case
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running from ai-core/ as `python -m src.eval.test_judge`.
_HERE = Path(__file__).resolve().parent
_AI_CORE = _HERE.parent.parent
sys.path.insert(0, str(_AI_CORE))

from src.eval.judge import (  # noqa: E402
    JudgeAggregate,
    JudgeOutcome,
    JudgeParseError,
    JudgeRequest,
    Verdict,
    aggregate_verdicts,
    build_judge_dynamic_suffix,
    judge_answer,
    parse_verdict,
)


# --- Stub judge LLM -------------------------------------------------------


class CannedJudge:
    """Stub JudgeLLM. Returns a canned response on each call."""

    def __init__(self, response: dict):
        self._response = response
        self.calls = 0
        self.last_suffix: str = ""

    def __call__(self, *, prefix_id, dynamic_suffix, model):
        self.calls += 1
        self.last_suffix = dynamic_suffix
        return self._response, {"input_tokens": 100, "output_tokens": 20}


# --- Prompt suffix --------------------------------------------------------


def test_build_judge_suffix_includes_all_fields() -> None:
    req = JudgeRequest(
        question="What time does King close?",
        expected_answer="King Library closes at 2am on weekdays.",
        bot_answer="King closes at 2am [1].",
        allowed_urls=["https://lib.miamioh.edu/king/hours/"],
    )
    suffix = build_judge_dynamic_suffix(req)
    assert "QUESTION: What time does King close?" in suffix
    assert "EXPECTED: King Library closes at 2am" in suffix
    assert "BOT ANSWER: King closes at 2am [1]." in suffix
    assert "https://lib.miamioh.edu/king/hours/" in suffix


def test_build_judge_suffix_handles_empty_allowed_urls() -> None:
    req = JudgeRequest(
        question="q", expected_answer="e", bot_answer="b", allowed_urls=[],
    )
    suffix = build_judge_dynamic_suffix(req)
    assert "(none)" in suffix


def test_build_judge_suffix_question_appears_before_expected() -> None:
    """Order matters -- the rubric is anchored by question + expected
    BEFORE the bot answer, so the judge doesn't bias on the bot's text."""
    req = JudgeRequest(
        question="q-marker", expected_answer="e-marker",
        bot_answer="b-marker", allowed_urls=[],
    )
    s = build_judge_dynamic_suffix(req)
    assert s.index("q-marker") < s.index("e-marker") < s.index("b-marker")


# --- Verdict parsing ------------------------------------------------------


def test_parse_verdict_happy_path() -> None:
    v = parse_verdict({
        "verdict": "correct",
        "reason": "matches expected",
        "citation_validity": "all_valid",
    })
    assert v.verdict == "correct"
    assert v.reason == "matches expected"
    assert v.citation_validity == "all_valid"


def test_parse_verdict_accepts_string_json() -> None:
    v = parse_verdict('{"verdict": "wrong", "reason": "off-topic", '
                      '"citation_validity": "no_citations"}')
    assert v.verdict == "wrong"
    assert v.citation_validity == "no_citations"


def test_parse_verdict_rejects_unknown_verdict_label() -> None:
    """Don't silently coerce -- an unknown label means the rubric drifted
    and the eval gate math is now broken; fail loud so we catch it."""
    try:
        parse_verdict({
            "verdict": "absolutely_wrong",
            "reason": "nope",
            "citation_validity": "n_a",
        })
    except JudgeParseError as e:
        assert "absolutely_wrong" in str(e)
        return
    raise AssertionError("expected JudgeParseError on unknown verdict")


def test_parse_verdict_rejects_unknown_citation_validity() -> None:
    try:
        parse_verdict({
            "verdict": "correct",
            "reason": "x",
            "citation_validity": "questionable",
        })
    except JudgeParseError as e:
        assert "questionable" in str(e)
        return
    raise AssertionError("expected JudgeParseError on unknown citation_validity")


def test_parse_verdict_rejects_bad_json_string() -> None:
    try:
        parse_verdict("not json at all {")
    except JudgeParseError:
        return
    raise AssertionError("expected JudgeParseError on bad json")


def test_parse_verdict_rejects_wrong_type() -> None:
    try:
        parse_verdict(42)  # type: ignore[arg-type]
    except JudgeParseError:
        return
    raise AssertionError("expected JudgeParseError on int input")


def test_parse_verdict_missing_reason_defaults_empty() -> None:
    """`reason` is optional -- some judge variants might skip it.
    Default to empty string rather than failing parsing."""
    v = parse_verdict({
        "verdict": "correct",
        "citation_validity": "all_valid",
    })
    assert v.reason == ""


# --- judge_answer entry point --------------------------------------------


def test_judge_answer_calls_llm_with_right_inputs() -> None:
    canned = CannedJudge({
        "verdict": "correct",
        "reason": "right URL cited",
        "citation_validity": "all_valid",
    })
    out = judge_answer(
        JudgeRequest(
            question="Where can I print?",
            expected_answer="Use the printing page.",
            bot_answer="Use https://lib.miamioh.edu/use/technology/printing/ [1].",
            allowed_urls=["https://lib.miamioh.edu/use/technology/printing/"],
        ),
        judge_llm=canned,
    )
    assert canned.calls == 1
    assert isinstance(out, JudgeOutcome)
    assert out.verdict.verdict == "correct"
    # Suffix should carry through unchanged.
    assert "Where can I print?" in canned.last_suffix


def test_judge_answer_propagates_parse_error() -> None:
    canned = CannedJudge({"verdict": "made_up", "citation_validity": "n_a"})
    try:
        judge_answer(
            JudgeRequest(
                question="q", expected_answer="e", bot_answer="b",
                allowed_urls=[],
            ),
            judge_llm=canned,
        )
    except JudgeParseError:
        return
    raise AssertionError("expected JudgeParseError to propagate")


# --- Aggregate ------------------------------------------------------------


def _v(verdict: str, cv: str = "all_valid") -> Verdict:
    return Verdict(verdict=verdict, reason="", citation_validity=cv)


def test_aggregate_correct_rate_counts_correct_and_refused_correctly() -> None:
    """Both 'correct' and 'refused_correctly' count toward correctness:
    a clean refusal of an off-topic question is a correct outcome."""
    verdicts = [
        _v("correct"),
        _v("correct"),
        _v("refused_correctly", "n_a"),
        _v("partial"),
        _v("wrong"),
    ]
    agg = aggregate_verdicts(verdicts)
    assert agg.total == 5
    assert agg.correct_rate == 3 / 5
    assert agg.by_verdict["correct"] == 2
    assert agg.by_verdict["refused_correctly"] == 1


def test_aggregate_citation_validity_excludes_refusals() -> None:
    """Refusals have citation_validity='n_a' -- they shouldn't drag
    down the citation-validity gate, which is about answer quality."""
    verdicts = [
        _v("correct", "all_valid"),
        _v("correct", "all_valid"),
        _v("correct", "some_invalid"),
        _v("refused_correctly", "n_a"),
        _v("refused_correctly", "n_a"),
    ]
    agg = aggregate_verdicts(verdicts)
    # 2 of 3 non-refusal answers have all_valid citations
    assert agg.citation_valid_rate == 2 / 3


def test_aggregate_empty_list_returns_zeros() -> None:
    """Edge case: --filter narrowed to a category with no cases.
    Must not divide by zero."""
    agg = aggregate_verdicts([])
    assert agg.total == 0
    assert agg.correct_rate == 0.0
    assert agg.citation_valid_rate == 0.0


def test_aggregate_all_refusals_citation_rate_is_zero() -> None:
    """Edge case: every verdict was a refusal -> no eligible cases for
    citation validity -> return 0 (matches the empty-list convention
    rather than NaN / division error)."""
    verdicts = [_v("refused_correctly", "n_a"), _v("refused_incorrectly", "n_a")]
    agg = aggregate_verdicts(verdicts)
    assert agg.citation_valid_rate == 0.0


# --- Runner ---------------------------------------------------------------


def main() -> int:
    tests = [
        test_build_judge_suffix_includes_all_fields,
        test_build_judge_suffix_handles_empty_allowed_urls,
        test_build_judge_suffix_question_appears_before_expected,
        test_parse_verdict_happy_path,
        test_parse_verdict_accepts_string_json,
        test_parse_verdict_rejects_unknown_verdict_label,
        test_parse_verdict_rejects_unknown_citation_validity,
        test_parse_verdict_rejects_bad_json_string,
        test_parse_verdict_rejects_wrong_type,
        test_parse_verdict_missing_reason_defaults_empty,
        test_judge_answer_calls_llm_with_right_inputs,
        test_judge_answer_propagates_parse_error,
        test_aggregate_correct_rate_counts_correct_and_refused_correctly,
        test_aggregate_citation_validity_excludes_refusals,
        test_aggregate_empty_list_returns_zeros,
        test_aggregate_all_refusals_citation_rate_is_zero,
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
