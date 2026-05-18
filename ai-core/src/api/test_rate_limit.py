"""
Offline tests for the chat abuse/cost guard.

Run: `python -m src.api.test_rate_limit` from ai-core/.

Pure, no API, no network. Deterministic time via the injected `now`.
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_AI_CORE = _HERE.parent.parent
sys.path.insert(0, str(_AI_CORE))

from src.api import rate_limit as RL
from src.api.rate_limit import (
    MAX_MESSAGE_CHARS,
    MessageRejected,
    SlidingWindowLimiter,
    check_rate,
    client_ip_from_request,
    conversation_turn_exceeded,
    validate_message,
)


def test_validate_rejects_non_str() -> None:
    for bad in (None, 123, {"a": 1}, ["x"]):
        try:
            validate_message(bad)
            assert False, f"expected reject for {bad!r}"
        except MessageRejected as e:
            assert e.code == 400


def test_validate_rejects_empty() -> None:
    for bad in ("", "   ", "\n\t "):
        try:
            validate_message(bad)
            assert False
        except MessageRejected as e:
            assert e.code == 400


def test_validate_rejects_oversized_413() -> None:
    try:
        validate_message("x" * (MAX_MESSAGE_CHARS + 1))
        assert False
    except MessageRejected as e:
        assert e.code == 413


def test_validate_ok_strips() -> None:
    assert validate_message("  what are King hours?  ") == "what are King hours?"


def test_limiter_allows_then_blocks_then_slides() -> None:
    lim = SlidingWindowLimiter(max_events=3, window_s=60)
    t = 1000.0
    assert lim.allow("ip", now=t) is True
    assert lim.allow("ip", now=t + 1) is True
    assert lim.allow("ip", now=t + 2) is True
    # 4th within window -> blocked
    assert lim.allow("ip", now=t + 3) is False
    # after the window slides past the first 3 hits -> allowed again
    assert lim.allow("ip", now=t + 61) is True
    # a different key is independent
    assert lim.allow("other", now=t + 3) is True


def test_check_rate_raises_429_over_limit() -> None:
    # Swap in a tiny limiter so the test is deterministic + isolated.
    orig = RL._chat_limiter
    RL._chat_limiter = SlidingWindowLimiter(max_events=1, window_s=999)
    try:
        check_rate("k")  # 1st ok
        try:
            check_rate("k")  # 2nd -> over
            assert False, "expected 429"
        except MessageRejected as e:
            assert e.code == 429
    finally:
        RL._chat_limiter = orig


def test_check_rate_fails_open_on_internal_error() -> None:
    """A limiter bug must NOT deny a legitimate user (fail-open)."""
    orig = RL._chat_limiter

    class _Boom:
        def allow(self, *a, **k):
            raise RuntimeError("limiter exploded")

    RL._chat_limiter = _Boom()
    try:
        check_rate("k")  # must NOT raise
    finally:
        RL._chat_limiter = orig


def test_conversation_turn_ceiling() -> None:
    assert conversation_turn_exceeded(RL.MAX_TURNS_PER_CONVERSATION) is True
    assert conversation_turn_exceeded(RL.MAX_TURNS_PER_CONVERSATION - 1) is False


def test_client_ip_xff_and_fallback_and_safe() -> None:
    class _R:
        def __init__(self, headers, host):
            self.headers = headers
            self.client = type("C", (), {"host": host})()

    assert client_ip_from_request(
        _R({"x-forwarded-for": "203.0.113.7, 10.0.0.1"}, "10.0.0.1")
    ) == "203.0.113.7"
    assert client_ip_from_request(_R({}, "198.51.100.4")) == "198.51.100.4"
    # Garbage object -> never raises, returns 'unknown'
    assert client_ip_from_request(object()) == "unknown"


def main() -> int:
    tests = [
        test_validate_rejects_non_str,
        test_validate_rejects_empty,
        test_validate_rejects_oversized_413,
        test_validate_ok_strips,
        test_limiter_allows_then_blocks_then_slides,
        test_check_rate_raises_429_over_limit,
        test_check_rate_fails_open_on_internal_error,
        test_conversation_turn_ceiling,
        test_client_ip_xff_and_fallback_and_safe,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
