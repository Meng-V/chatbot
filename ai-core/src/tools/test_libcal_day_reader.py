"""describe_libcal_day: the four shapes LibCal publishes a day in.

Written after a live student session on 2026-08-04, where "when does
Makerspace close today" was answered "The Makerspace is Closed today" with a
citation. The Makerspace was open 9am-4pm that day. LibCal was returning

    {"status": "text",
     "text": "<a href=\"...\" target=\"_blank\">9am-4pm by appt</a>"}

with no `hours` array, and every reader in libcal_comprehensive_tools.py
tested `day_data.get("hours")` and fell through to a hardcoded `Closed`.

That is the worst failure mode this bot has: not a shrug, but a confident,
cited claim that turns a patron away from an open building. So the reader is
one function with one test file, and "we don't know" is a distinct state from
"closed".
"""
from __future__ import annotations

from src.tools.libcal_comprehensive_tools import (
    HOURS_NOT_POSTED,
    _clean_libcal_text,
    describe_libcal_day,
)


def test_interval_day():
    assert describe_libcal_day(
        {"status": "open", "hours": [{"from": "7:30am", "to": "9:00pm"}]}
    ) == ("open", "7:30am to 9:00pm")


def test_split_day_keeps_both_spans():
    """A day that closes for lunch has two intervals; reporting one is wrong."""
    state, display = describe_libcal_day({
        "status": "open",
        "hours": [{"from": "8am", "to": "12pm"}, {"from": "1pm", "to": "5pm"}],
    })
    assert state == "open"
    assert display == "8am to 12pm and 1pm to 5pm"


def test_closed_day():
    assert describe_libcal_day({"status": "closed", "hours": None}) == (
        "closed", "Closed")


def test_round_the_clock_day_is_not_closed():
    """status "24hours" carries no intervals either -- the old
    `if day_data.get("hours")` test would have called it Closed."""
    assert describe_libcal_day({"status": "24hours"}) == (
        "24hours", "Open 24 hours")


def test_free_text_day_is_the_regression():
    """The exact payload from the failing session."""
    state, display = describe_libcal_day({
        "status": "text",
        "text": ('<a href="https://muohio.libcal.com/reserve/equipment/'
                 'makerspace" target="_blank">9am-4pm by appt</a>'),
    })
    assert state == "text"
    assert display == "9am-4pm by appointment"
    assert "Closed" not in display
    assert "<a" not in display, "HTML must not reach a patron answer"


def test_missing_day_is_unknown_not_closed():
    """A day we have no data for is a day we must not make a claim about.

    This was the second half of the same bug: LibCalWeekHoursTool asked
    LibCal for today..today+6 while labelling rows Monday..Sunday, so on a
    Thursday three days of the current week were never fetched -- and every
    one of them was reported "Closed".
    """
    assert describe_libcal_day(None) == ("unknown", HOURS_NOT_POSTED)
    assert describe_libcal_day({}) == ("unknown", HOURS_NOT_POSTED)
    assert HOURS_NOT_POSTED.lower() != "closed"


def test_open_status_without_intervals_is_unknown():
    """Rather than an empty or invented range."""
    assert describe_libcal_day({"status": "open"})[0] == "unknown"
    assert describe_libcal_day({"status": "open", "hours": []})[0] == "unknown"


def test_unrecognised_status_does_not_claim_closed():
    """LibCal can add statuses; a future one must degrade to "unknown"."""
    state, _ = describe_libcal_day({"status": "some-future-status"})
    assert state == "unknown"


def test_empty_free_text_points_at_the_website():
    assert describe_libcal_day({"status": "text", "text": ""}) == (
        "text", "See website")


def test_clean_libcal_text_unescapes_and_strips():
    assert _clean_libcal_text("<b>9am</b> &amp; noon") == "9am & noon"
    assert _clean_libcal_text("  spaced   out  ") == "spaced out"
    assert _clean_libcal_text(None) == ""
    # Adjacent tags must not weld words together.
    assert _clean_libcal_text("<span>9am</span><span>4pm</span>") == "9am 4pm"


def test_appointment_abbreviations_are_spelled_out():
    """A patron should not have to decode LibCal's shorthand."""
    assert _clean_libcal_text("9am-4pm by appt") == "9am-4pm by appointment"
    assert _clean_libcal_text("appt only") == "by appointment only"
