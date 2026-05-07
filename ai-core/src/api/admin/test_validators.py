"""
Unit tests for the admin-router validators (pure logic).

Run: `python -m src.api.admin.test_validators` from ai-core/.

The reviews and corrections routers each have a pure validator that
runs BEFORE the (currently-stubbed) DB call. Bugs in validation are
the worst kind of admin-API bug:

  - Permissive: librarians can submit malformed corrections that
    crash retrieval at runtime ("pin action without query_pattern").
  - Restrictive: librarians can't submit legitimate verdicts because
    a typo'd validator rejects them.

Both endpoints route through these pure functions today (the wired
DB calls in week 7 will sit BEHIND the validators). Locking the
contract now means the wiring won't introduce a regression.

Tests cover:
  validate_verdict (reviews_router):
    - happy path verdict
    - bad verdict label
    - empty message_id
    - non-positive librarian_id
    - oversized note (> 2000 chars)
    - VALID_VERDICTS lock-in (4 documented values)

  validate_correction (corrections_router):
    - happy path each action: suppress, replace, pin, blacklist_url
    - bad action label
    - bad scope label
    - missing reason
    - missing created_by
    - replace without replacement
    - pin without query_pattern
    - blacklist_url with non-url scope
    - suppress with non-chunk scope
    - default_expiry returns now+180d

  build_*_router placeholder fallback when fastapi is missing
  (smoke check that import doesn't crash).
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Allow running from ai-core/ as `python -m src.api.admin.test_validators`.
_HERE = Path(__file__).resolve().parent
_AI_CORE = _HERE.parent.parent.parent
sys.path.insert(0, str(_AI_CORE))

from src.api.admin.corrections_router import (  # noqa: E402
    DEFAULT_EXPIRY_DAYS,
    VALID_ACTIONS,
    VALID_SCOPES,
    CorrectionInput,
    build_corrections_router,
    default_expiry,
    validate_correction,
)
from src.api.admin.reviews_router import (  # noqa: E402
    VALID_VERDICTS,
    ReviewVerdict,
    build_reviews_router,
    validate_verdict,
)


# --- validate_verdict ---


def _good_verdict(**kw) -> ReviewVerdict:
    defaults = {
        "message_id": "msg-123",
        "librarian_id": 42,
        "verdict": "correct",
        "note": "looks good",
    }
    defaults.update(kw)
    return ReviewVerdict(**defaults)


def test_validate_verdict_happy_path() -> None:
    assert validate_verdict(_good_verdict()) is None


def test_validate_verdict_unknown_label() -> None:
    err = validate_verdict(_good_verdict(verdict="amazing"))
    assert err is not None
    assert "verdict must be one of" in err


def test_validate_verdict_empty_message_id() -> None:
    err = validate_verdict(_good_verdict(message_id=""))
    assert err == "message_id is required"


def test_validate_verdict_non_positive_librarian_id() -> None:
    err = validate_verdict(_good_verdict(librarian_id=0))
    assert err == "librarian_id must be positive"
    err = validate_verdict(_good_verdict(librarian_id=-1))
    assert err == "librarian_id must be positive"


def test_validate_verdict_oversized_note() -> None:
    long_note = "x" * 2001
    err = validate_verdict(_good_verdict(note=long_note))
    assert err is not None
    assert "exceeds 2000" in err


def test_validate_verdict_at_limit_note_ok() -> None:
    """Boundary: exactly 2000 chars is allowed."""
    note_2000 = "x" * 2000
    assert validate_verdict(_good_verdict(note=note_2000)) is None


def test_validate_verdict_no_note_ok() -> None:
    assert validate_verdict(_good_verdict(note=None)) is None


def test_valid_verdicts_locked_in() -> None:
    """The four documented verdicts. A future PR adding a 5th must
    update this test (and downstream consumers like the eval harness's
    judge prompts). Removing one is what this lock catches."""
    expected = {"correct", "partial", "wrong", "should_refuse"}
    assert set(VALID_VERDICTS) == expected


# --- validate_correction ---


def _good_correction(**kw) -> CorrectionInput:
    defaults = {
        "scope": "chunk",
        "target": "chunk-uuid-123",
        "action": "suppress",
        "reason": "Wrong answer for room booking",
        "created_by": "lib@miamioh.edu",
        "replacement": None,
        "query_pattern": None,
        "expires_at": None,
    }
    defaults.update(kw)
    return CorrectionInput(**defaults)


def test_validate_correction_suppress_happy() -> None:
    assert validate_correction(_good_correction()) is None


def test_validate_correction_replace_happy() -> None:
    c = _good_correction(action="replace", replacement="corrected text")
    assert validate_correction(c) is None


def test_validate_correction_pin_happy() -> None:
    c = _good_correction(
        scope="chunk", action="pin",
        query_pattern=r".*makerspace.*",
    )
    assert validate_correction(c) is None


def test_validate_correction_blacklist_happy() -> None:
    c = _good_correction(
        scope="url", action="blacklist_url",
        target="https://example/bad",
    )
    assert validate_correction(c) is None


def test_validate_correction_bad_action() -> None:
    err = validate_correction(_good_correction(action="delete"))
    assert err is not None
    assert "action must be one of" in err


def test_validate_correction_bad_scope() -> None:
    err = validate_correction(_good_correction(scope="elsewhere"))
    assert err is not None
    assert "scope must be one of" in err


def test_validate_correction_missing_reason() -> None:
    err = validate_correction(_good_correction(reason=""))
    assert err == "reason is required"
    # Whitespace-only also rejected.
    err = validate_correction(_good_correction(reason="   "))
    assert err == "reason is required"


def test_validate_correction_missing_created_by() -> None:
    err = validate_correction(_good_correction(created_by=""))
    assert err == "created_by is required"


def test_validate_correction_replace_without_replacement() -> None:
    err = validate_correction(_good_correction(action="replace"))
    assert err is not None
    assert "replacement" in err


def test_validate_correction_pin_without_query_pattern() -> None:
    err = validate_correction(_good_correction(action="pin"))
    assert err is not None
    assert "query_pattern" in err


def test_validate_correction_blacklist_with_chunk_scope() -> None:
    """blacklist_url is by definition URL-scoped; chunk scope is
    nonsensical and would route the wrong table."""
    err = validate_correction(_good_correction(
        action="blacklist_url", scope="chunk",
    ))
    assert err is not None
    assert "scope=url" in err


def test_validate_correction_suppress_with_url_scope() -> None:
    """suppress is by definition chunk-scoped; URL-suppress is what
    blacklist_url is for. Distinct actions, distinct scopes."""
    err = validate_correction(_good_correction(
        action="suppress", scope="url",
    ))
    assert err is not None
    assert "scope=chunk" in err


# --- default_expiry ---


def test_default_expiry_180_days_from_now() -> None:
    """Six-month auto-renewal cadence per plan §Op 2."""
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    out = default_expiry(now)
    expected = now + timedelta(days=DEFAULT_EXPIRY_DAYS)
    assert out == expected
    # 180 days is the documented value.
    assert DEFAULT_EXPIRY_DAYS == 180


def test_default_expiry_uses_utc_now_by_default() -> None:
    out = default_expiry()
    delta = out - datetime.now(timezone.utc)
    # Within a couple seconds of expected.
    assert abs((delta - timedelta(days=180)).total_seconds()) < 5


# --- VALID_ACTIONS / VALID_SCOPES lock-in ---


def test_valid_actions_locked_in() -> None:
    expected = {"suppress", "replace", "pin", "blacklist_url"}
    assert set(VALID_ACTIONS) == expected


def test_valid_scopes_locked_in() -> None:
    expected = {"url", "chunk", "intent", "global"}
    assert set(VALID_SCOPES) == expected


# --- Router build smoke checks ---


def test_build_reviews_router_imports_without_crashing() -> None:
    """fastapi may or may not be installed; either way build_router
    returns SOMETHING (real router or _PlaceholderRouter shim).
    Imports must not raise."""
    out = build_reviews_router({"db": object()})
    assert out is not None
    # Both shapes have a `.routes` attribute.
    assert hasattr(out, "routes")


def test_build_corrections_router_imports_without_crashing() -> None:
    out = build_corrections_router({"db": object()})
    assert out is not None
    assert hasattr(out, "routes")


def main() -> int:
    tests = [
        test_validate_verdict_happy_path,
        test_validate_verdict_unknown_label,
        test_validate_verdict_empty_message_id,
        test_validate_verdict_non_positive_librarian_id,
        test_validate_verdict_oversized_note,
        test_validate_verdict_at_limit_note_ok,
        test_validate_verdict_no_note_ok,
        test_valid_verdicts_locked_in,
        test_validate_correction_suppress_happy,
        test_validate_correction_replace_happy,
        test_validate_correction_pin_happy,
        test_validate_correction_blacklist_happy,
        test_validate_correction_bad_action,
        test_validate_correction_bad_scope,
        test_validate_correction_missing_reason,
        test_validate_correction_missing_created_by,
        test_validate_correction_replace_without_replacement,
        test_validate_correction_pin_without_query_pattern,
        test_validate_correction_blacklist_with_chunk_scope,
        test_validate_correction_suppress_with_url_scope,
        test_default_expiry_180_days_from_now,
        test_default_expiry_uses_utc_now_by_default,
        test_valid_actions_locked_in,
        test_valid_scopes_locked_in,
        test_build_reviews_router_imports_without_crashing,
        test_build_corrections_router_imports_without_crashing,
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
