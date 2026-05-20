"""
Offline tests for the hours 1-month date-window rule.

Run: `python -m src.scope.test_date_window` from ai-core/.

Deterministic via an injected `today` -- no clock dependence, no API.
Asserts the hr_thanksgiving operator ruling end-to-end through the v2
gate `_is_long_period_hours`.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_AI_CORE = _HERE.parent.parent
sys.path.insert(0, str(_AI_CORE))

from src.scope.date_window import (
    WINDOW_DAYS,
    resolve_target_date,
    within_window,
)
from src.graph.new_orchestrator import _is_long_period_hours

_MAY19 = date(2026, 5, 19)


def test_resolve_holiday_far() -> None:
    d = resolve_target_date("are you open Thanksgiving day?", today=_MAY19)
    assert d is not None and d.year == 2026 and d.month == 11
    assert (d - _MAY19).days > WINDOW_DAYS  # ~6 months out


def test_resolve_relative_and_explicit() -> None:
    assert resolve_target_date("hours tomorrow", today=_MAY19) == date(2026, 5, 20)
    d = resolve_target_date("library hours on May 25", today=_MAY19)
    assert d == date(2026, 5, 25)
    dec = resolve_target_date("open on December 25?", today=_MAY19)
    assert dec == date(2026, 12, 25)


def test_resolve_none_for_generic_or_openended() -> None:
    assert resolve_target_date("what are the summer hours", today=_MAY19) is None
    assert resolve_target_date("what are the library hours", today=_MAY19) is None
    assert resolve_target_date("", today=_MAY19) is None


def test_within_window() -> None:
    assert within_window(_MAY19 + timedelta(days=10), today=_MAY19) is True
    assert within_window(_MAY19 + timedelta(days=WINDOW_DAYS), today=_MAY19) is True
    assert within_window(_MAY19 + timedelta(days=WINDOW_DAYS + 1), today=_MAY19) is False
    assert within_window(_MAY19 - timedelta(days=1), today=_MAY19) is False  # past


def test_gate_short_term_is_live() -> None:
    assert _is_long_period_hours("is the library open tonight?", today=_MAY19) is False
    assert _is_long_period_hours("what time do you close today", today=_MAY19) is False


def test_gate_thanksgiving_far_is_long_period() -> None:
    # hr_thanksgiving: 6 months out -> point-to-page + explain.
    assert _is_long_period_hours("are you open Thanksgiving day?", today=_MAY19) is True


def test_gate_thanksgiving_near_is_live() -> None:
    # Same question, but asked ~2 weeks before -> answerable live.
    assert _is_long_period_hours(
        "are you open Thanksgiving day?", today=date(2026, 11, 12)
    ) is False


def test_gate_near_specific_date_is_live() -> None:
    assert _is_long_period_hours("hours next Tuesday?", today=_MAY19) is False
    assert _is_long_period_hours("library hours on May 25", today=_MAY19) is False


def test_gate_far_specific_date_is_long_period() -> None:
    assert _is_long_period_hours("hours on December 25?", today=_MAY19) is True


def test_gate_openended_phrasing_is_long_period() -> None:
    assert _is_long_period_hours("what are the summer hours", today=_MAY19) is True
    assert _is_long_period_hours("hours during winter break?", today=_MAY19) is True


def test_gate_generic_no_date_not_long_period() -> None:
    # No date, no open-ended marker -> normal path (live), unchanged.
    assert _is_long_period_hours("what are the library hours", today=_MAY19) is False


def main() -> int:
    tests = [
        test_resolve_holiday_far,
        test_resolve_relative_and_explicit,
        test_resolve_none_for_generic_or_openended,
        test_within_window,
        test_gate_short_term_is_live,
        test_gate_thanksgiving_far_is_long_period,
        test_gate_thanksgiving_near_is_live,
        test_gate_near_specific_date_is_live,
        test_gate_far_specific_date_is_long_period,
        test_gate_openended_phrasing_is_long_period,
        test_gate_generic_no_date_not_long_period,
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
