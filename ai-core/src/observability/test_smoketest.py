"""
Unit tests for the synthetic-monitoring smoketest.

Run: `python -m src.observability.test_smoketest` from ai-core/.

The /smoketest endpoint is the canary that catches outages where every
component reports healthy but the chain is broken. A bug here means
real outages slip past the external pinger -- worse than no monitoring
at all (false sense of security).

Tests use stub `ask_bot` callables that return canned shapes, so the
test runs in milliseconds and covers every check independently.

Tests:
  1. Happy path: answer + citations + under budget -> passed=True.
  2. ask_bot raises -> passed=False, reachable=False, reason includes exception type.
  3. is_refusal=True -> passed=False, "response was a refusal".
  4. citations=[] -> passed=False, "no citations".
  5. Slow ask_bot -> passed=False, latency exceeds budget.
  6. Multiple failures composed in reason string.
  7. answer_preview truncated to 200 chars.
  8. checks dict has all three keys on success path.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

# Allow running from ai-core/ as `python -m src.observability.test_smoketest`.
_HERE = Path(__file__).resolve().parent
_AI_CORE = _HERE.parent.parent
sys.path.insert(0, str(_AI_CORE))

from src.observability.smoketest import (  # noqa: E402
    DEFAULT_LATENCY_BUDGET_MS,
    DEFAULT_QUESTION,
    SmoketestResult,
    run_smoketest,
)


def _good_response() -> dict:
    return {
        "answer": "King opens at 7am [1].",
        "citations": [{"n": 1, "url": "https://lib.miamioh.edu/king/"}],
        "is_refusal": False,
    }


def test_happy_path_passes() -> None:
    result = run_smoketest(ask_bot=lambda q: _good_response())
    assert result.passed
    assert result.reason == ""
    assert result.checks["is_answer"] is True
    assert result.checks["has_citation"] is True
    assert result.checks["under_latency"] is True
    assert "King opens" in result.answer_preview


def test_ask_bot_raises_returns_unreachable() -> None:
    def crash(_):
        raise ConnectionError("backend down")

    result = run_smoketest(ask_bot=crash)
    assert not result.passed
    assert result.checks == {"reachable": False}
    assert "ConnectionError" in result.reason
    assert "backend down" in result.reason


def test_refusal_fails_check() -> None:
    result = run_smoketest(ask_bot=lambda q: {
        "answer": "I can't help with that.",
        "citations": [{"n": 1, "url": "https://x"}],
        "is_refusal": True,
    })
    assert not result.passed
    assert result.checks["is_answer"] is False
    assert "refusal" in result.reason


def test_no_citations_fails_check() -> None:
    result = run_smoketest(ask_bot=lambda q: {
        "answer": "King opens at 7am.",
        "citations": [],
        "is_refusal": False,
    })
    assert not result.passed
    assert result.checks["has_citation"] is False
    assert "no citations" in result.reason


def test_slow_response_fails_under_latency() -> None:
    def slow(_):
        time.sleep(0.05)
        return _good_response()

    # Tiny budget so even the 50ms sleep blows it.
    result = run_smoketest(ask_bot=slow, latency_budget_ms=10)
    assert not result.passed
    assert result.checks["under_latency"] is False
    assert "latency" in result.reason
    assert "budget 10" in result.reason


def test_multiple_failures_composed_in_reason() -> None:
    """Refusal + no citations: reason should mention both so the
    pager-tier alert tells operators the full story."""
    result = run_smoketest(ask_bot=lambda q: {
        "answer": "no",
        "citations": [],
        "is_refusal": True,
    })
    assert not result.passed
    assert "refusal" in result.reason
    assert "no citations" in result.reason
    assert ";" in result.reason  # bits joined by "; "


def test_answer_preview_truncated_to_200_chars() -> None:
    long_answer = "a" * 1000
    result = run_smoketest(ask_bot=lambda q: {
        "answer": long_answer,
        "citations": [{"n": 1, "url": "https://x"}],
        "is_refusal": False,
    })
    assert len(result.answer_preview) == 200


def test_default_question_is_exposed() -> None:
    """The canned question is a public constant so external pingers
    and integration tests reference the same string."""
    assert isinstance(DEFAULT_QUESTION, str)
    assert "King" in DEFAULT_QUESTION  # default targets King hours
    assert DEFAULT_LATENCY_BUDGET_MS > 0


def test_latency_recorded_even_on_failure() -> None:
    """Failed runs must still report latency (helps debug 'is it
    slow because the call hung?')."""
    result = run_smoketest(ask_bot=lambda q: {
        "answer": "x", "citations": [], "is_refusal": False,
    })
    assert result.latency_ms >= 0


def test_smoketest_question_passed_through() -> None:
    seen: list[str] = []

    def capture(q):
        seen.append(q)
        return _good_response()

    run_smoketest(ask_bot=capture, question="What time does Wertz close?")
    assert seen == ["What time does Wertz close?"]


def main() -> int:
    tests = [
        test_happy_path_passes,
        test_ask_bot_raises_returns_unreachable,
        test_refusal_fails_check,
        test_no_citations_fails_check,
        test_slow_response_fails_under_latency,
        test_multiple_failures_composed_in_reason,
        test_answer_preview_truncated_to_200_chars,
        test_default_question_is_exposed,
        test_latency_recorded_even_on_failure,
        test_smoketest_question_passed_through,
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
