"""Booking caps: 2 per conversation, 2 per email per day.

The failure that matters is not "the cap is off by one", it is the cap
turning away a student who is trying to book one room. So the fail-open
paths are tested as carefully as the limits.
"""
from __future__ import annotations

import json

import pytest

from src.observability import booking_quota as Q


@pytest.fixture(autouse=True)
def _ledger(tmp_path, monkeypatch):
    """Redirect via the ENV VAR, not the module constant.

    booking_quota resolves its path per call through _ledger(), which reads
    BOOKING_QUOTA_PATH first -- and src/conftest.py sets that for every test
    in the suite so nothing can reach production state. Patching the module
    constant instead would be silently overridden by that guard.
    """
    path = tmp_path / "quota.json"
    monkeypatch.setenv("BOOKING_QUOTA_PATH", str(path))
    yield path


def test_the_limits_are_two_and_two():
    assert Q.MAX_PER_CONVERSATION == 2
    assert Q.MAX_PER_EMAIL_PER_DAY == 2


def test_first_two_bookings_are_allowed_then_the_third_is_not():
    for _ in range(2):
        assert Q.check("qum@miamioh.edu").allowed is True
        Q.record("qum@miamioh.edu")
    v = Q.check("qum@miamioh.edu")
    assert v.allowed is False
    assert "daily limit" in v.reason


def test_a_refusal_says_what_to_do_next():
    """Never a bare no: the student still needs the room."""
    for _ in range(2):
        Q.record("a@miamioh.edu")
    reason = Q.check("a@miamioh.edu").reason
    assert "libcal" in reason.lower()
    assert "Ask Us" in reason


def test_the_cap_is_per_address():
    for _ in range(2):
        Q.record("a@miamioh.edu")
    assert Q.check("a@miamioh.edu").allowed is False
    assert Q.check("b@miamioh.edu").allowed is True, (
        "one abuser must not lock out everyone else"
    )


def test_address_matching_ignores_case_and_spaces():
    Q.record("Qum@MiamiOH.edu")
    Q.record("  qum@miamioh.edu  ")
    assert Q.check("QUM@MIAMIOH.EDU").allowed is False


def test_conversation_cap_is_independent_of_the_email_cap():
    """Two different students on one shared widget session still hit the
    conversation cap; one student across two chats does not."""
    Q.record("a@miamioh.edu", "conv-1")
    Q.record("b@miamioh.edu", "conv-1")
    v = Q.check("c@miamioh.edu", "conv-1")
    assert v.allowed is False
    assert "this conversation" in v.reason
    assert Q.check("c@miamioh.edu", "conv-2").allowed is True


def test_recording_happens_only_on_success(tmp_path):
    """check() must not consume the allowance -- a LibCal outage during two
    attempts would otherwise burn a student's whole day."""
    for _ in range(5):
        assert Q.check("a@miamioh.edu").allowed is True
    assert Q.usage_today().get("a@miamioh.edu") is None


def test_missing_ledger_allows(tmp_path, monkeypatch):
    monkeypatch.setattr(Q, "LEDGER_PATH", tmp_path / "nope" / "quota.json")
    assert Q.check("a@miamioh.edu").allowed is True


def test_corrupt_ledger_fails_open(_ledger):
    """A bad JSON file must not stop students booking rooms."""
    _ledger.write_text("{ not json")
    assert Q.check("a@miamioh.edu").allowed is True
    # ...and a subsequent record repairs the file rather than raising.
    Q.record("a@miamioh.edu")
    assert json.loads(_ledger.read_text())["days"]


def test_no_email_does_not_crash():
    """book_room can reach the cap with an empty address if validation
    changes upstream; that must not raise on a live turn."""
    assert Q.check("").allowed is True
    Q.record("")
    assert Q.check("", "conv-1").allowed is True


def test_old_days_are_pruned(_ledger):
    Q.record("a@miamioh.edu")
    data = json.loads(_ledger.read_text())
    data["days"]["2020-01-01"] = {"old@miamioh.edu": 99}
    _ledger.write_text(json.dumps(data))
    Q.record("b@miamioh.edu")
    assert "2020-01-01" not in json.loads(_ledger.read_text())["days"]


def test_write_leaves_no_temp_file(_ledger):
    Q.record("a@miamioh.edu")
    assert list(_ledger.parent.glob("*.tmp")) == []


def test_usage_today_reports_counts():
    Q.record("a@miamioh.edu")
    Q.record("a@miamioh.edu")
    Q.record("b@miamioh.edu")
    assert Q.usage_today() == {"a@miamioh.edu": 2, "b@miamioh.edu": 1}
