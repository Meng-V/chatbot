"""
Tests for the inspect_turn diagnostic CLI.

Run: `python -m src.eval.test_inspect_turn` from ai-core/.

Catches three failure classes:
  1. Keyword classifier misroutes the user-flagged failure case
     (was the whole reason for the v2 taxonomy)
  2. CLI flags don't actually override the orchestrator's defaults
  3. The pretty-trace output drops one of the documented sections
"""

from __future__ import annotations

import io
import sys
from contextlib import redirect_stdout
from pathlib import Path

# Allow `python -m src.eval.test_inspect_turn` from ai-core/.
_HERE = Path(__file__).resolve().parent
_AI_CORE = _HERE.parent.parent
sys.path.insert(0, str(_AI_CORE))

from src.eval.inspect_turn import (  # noqa: E402
    _keyword_classify,
    inspect,
)
from src.router.intent_knn import INTENTS  # noqa: E402


# --- _keyword_classify --------------------------------------------------


def test_keyword_routes_user_flagged_failure_to_circulation_basic() -> None:
    """The original librarian-flagged failure mode. The whole reason
    we re-did the taxonomy."""
    cls = _keyword_classify(
        "Will I get a confirmation when I place a hold?"
    )
    assert cls.intent == "circulation_basic"


def test_keyword_routes_account_question_to_account() -> None:
    cls = _keyword_classify("How much do I owe?")
    assert cls.intent == "account"


def test_keyword_routes_makerspace_to_makerspace_3d() -> None:
    cls = _keyword_classify("Where is the makerspace?")
    assert cls.intent == "makerspace_3d"


def test_keyword_routes_ill_to_interlibrary_loan() -> None:
    cls = _keyword_classify(
        "I need to get a book through OhioLINK"
    )
    assert cls.intent == "interlibrary_loan"


def test_keyword_routes_no_match_to_out_of_scope() -> None:
    """Garbage input falls through to out_of_scope, not a crash."""
    cls = _keyword_classify("blarghhh foofloofy")
    assert cls.intent == "out_of_scope"


def test_keyword_classifier_intents_all_in_INTENTS() -> None:
    """Keyword hint table can't reference an intent that doesn't
    exist in the registry -- would silently fail downstream."""
    from src.eval.inspect_turn import _KEYWORD_HINTS
    valid = set(INTENTS)
    for intent in _KEYWORD_HINTS:
        assert intent in valid, f"unknown intent: {intent}"


def test_keyword_classifier_returns_classification_shape() -> None:
    cls = _keyword_classify("hours")
    assert hasattr(cls, "intent")
    assert hasattr(cls, "margin")
    assert hasattr(cls, "score")
    assert hasattr(cls, "needs_clarification")
    assert hasattr(cls, "candidates")


def test_keyword_classifier_clarification_on_tied_keywords() -> None:
    """A query that hits two intent buckets equally should trigger
    clarification (low margin)."""
    # 'do you have JSTOR' -> find_resource ('do you have') AND
    # databases ('jstor') both score 1 hit -> margin 0
    cls = _keyword_classify("do you have JSTOR?")
    assert cls.margin < 0.05
    assert cls.needs_clarification is True


# --- inspect() integration ---


def test_inspect_returns_response_and_latency() -> None:
    buf = io.StringIO()
    with redirect_stdout(buf):
        resp, latency_us = inspect(
            "What time does King close?",
            print_trace=False,
        )
    assert resp is not None
    assert latency_us > 0
    # Response is a TurnResponse-shaped object.
    assert hasattr(resp, "answer")
    assert hasattr(resp, "is_refusal")
    assert hasattr(resp, "intent")


def test_inspect_account_question_short_circuits_to_refusal() -> None:
    buf = io.StringIO()
    with redirect_stdout(buf):
        resp, _ = inspect("How much do I owe?", print_trace=False)
    assert resp.is_refusal
    assert resp.refusal_trigger == "account_privacy"
    # No LLM tokens because of the capability-registry short-circuit.
    assert resp.tokens["input"] == 0


def test_inspect_circulation_basic_runs_agent() -> None:
    buf = io.StringIO()
    with redirect_stdout(buf):
        resp, _ = inspect(
            "Will I get a confirmation when I place a hold?",
            print_trace=False,
        )
    assert not resp.is_refusal
    assert resp.intent == "circulation_basic"
    # Agent path -> nonzero LLM tokens.
    assert resp.tokens["input"] > 0


def test_inspect_forced_intent_overrides_classifier() -> None:
    buf = io.StringIO()
    with redirect_stdout(buf):
        resp, _ = inspect(
            "this is some random text",
            forced_intent="hours",
            print_trace=False,
        )
    assert resp.intent == "hours"


def test_inspect_unknown_forced_intent_raises() -> None:
    try:
        inspect("anything", forced_intent="not_a_real_intent",
                print_trace=False)
    except ValueError as e:
        assert "unknown intent" in str(e)
        return
    raise AssertionError("expected ValueError on bad intent")


def test_inspect_session_origin_resolves_to_hamilton_default() -> None:
    """When the chat widget loads on ham.miamioh.edu, scope.campus
    defaults to hamilton even without explicit campus mention."""
    buf = io.StringIO()
    with redirect_stdout(buf):
        resp, _ = inspect(
            "library hours today",
            session_origin_url="https://ham.miamioh.edu/library/",
            print_trace=False,
        )
    assert resp.scope["campus"] == "hamilton"


def test_inspect_explicit_campus_in_question_resolves_correctly() -> None:
    """The right way to scope a question is to mention the campus or
    library in the question text itself -- the real resolver picks it
    up via alias matching, the same way it would in prod.
    (Earlier this test asserted forced_campus / forced_library kwargs
    overrode the resolver. They didn't actually thread through to the
    orchestrator -- they only modified the printed trace -- so the
    flags were misleading and got removed.)"""
    buf = io.StringIO()
    with redirect_stdout(buf):
        resp, _ = inspect(
            "what time does Gardner-Harvey close",
            print_trace=False,
        )
    assert resp.scope["campus"] == "middletown"
    assert resp.scope["library"] == "gardner_harvey"


def test_inspect_service_unavailable_short_circuits() -> None:
    """When --service-unavailable is set, post-processor returns the
    SERVICE_NOT_AT_BUILDING refusal regardless of synthesizer output."""
    buf = io.StringIO()
    with redirect_stdout(buf):
        resp, _ = inspect(
            "where is the makerspace at Hamilton",
            service_unavailable=True,
            print_trace=False,
        )
    assert resp.is_refusal
    assert resp.refusal_trigger == "service_not_at_building"


# --- Pretty-trace output ---


def test_pretty_trace_includes_all_sections() -> None:
    buf = io.StringIO()
    with redirect_stdout(buf):
        inspect(
            "hours today",
            print_trace=True,
        )
    out = buf.getvalue()
    # Required sections in order.
    for section in (
        "Inspect Turn:",
        "[1] Scope resolution",
        "[2] Intent classification",
        "[3] Capability tier",
        "[final] TurnResponse",
    ):
        assert section in out, f"trace missing section: {section}"


def test_pretty_trace_shows_tokens_on_agent_path() -> None:
    buf = io.StringIO()
    with redirect_stdout(buf):
        inspect("hours today", print_trace=True)
    out = buf.getvalue()
    # Agent path -> tokens should be visible (not 0/0/0).
    assert "tokens" in out
    # The trace emits the dict directly.
    assert "input" in out


def test_pretty_trace_shows_capability_short_circuit() -> None:
    """For account questions, trace must show the SHORT-CIRCUIT note
    so the operator knows the agent didn't run."""
    buf = io.StringIO()
    with redirect_stdout(buf):
        inspect("how much do I owe?", print_trace=True)
    out = buf.getvalue()
    assert "SHORT-CIRCUIT" in out
    assert "refuse" in out


def main() -> int:
    tests = [
        test_keyword_routes_user_flagged_failure_to_circulation_basic,
        test_keyword_routes_account_question_to_account,
        test_keyword_routes_makerspace_to_makerspace_3d,
        test_keyword_routes_ill_to_interlibrary_loan,
        test_keyword_routes_no_match_to_out_of_scope,
        test_keyword_classifier_intents_all_in_INTENTS,
        test_keyword_classifier_returns_classification_shape,
        test_keyword_classifier_clarification_on_tied_keywords,
        test_inspect_returns_response_and_latency,
        test_inspect_account_question_short_circuits_to_refusal,
        test_inspect_circulation_basic_runs_agent,
        test_inspect_forced_intent_overrides_classifier,
        test_inspect_unknown_forced_intent_raises,
        test_inspect_session_origin_resolves_to_hamilton_default,
        test_inspect_explicit_campus_in_question_resolves_correctly,
        test_inspect_service_unavailable_short_circuits,
        test_pretty_trace_includes_all_sections,
        test_pretty_trace_shows_tokens_on_agent_path,
        test_pretty_trace_shows_capability_short_circuit,
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
