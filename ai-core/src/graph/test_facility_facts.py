"""Operator-provided building facts: do they fire, and do they NOT overfire?

These short-circuit ahead of the agent, so a false positive replaces a good
retrieved answer with a canned one. The negative cases matter more than the
positive ones.
"""
from __future__ import annotations

import pytest

from src.graph import facility_facts as F


def _ans(fn, q):
    r = fn(q)
    return r[0] if r else None


# --- quiet study: 2nd AND 3rd floor -------------------------------------


@pytest.mark.parametrize("q", [
    "where is the silent study area",
    "Where is the silent study area?",
    "is there a quiet floor",
    "quiet study space?",
    "where can i study quietly",
    "do you have silent areas",
    "which floor is quiet",
])
def test_quiet_fires_on_how_students_ask(q):
    a = _ans(F.quiet_study_answer, q)
    assert a is not None, q
    assert "second and third" in a.lower()


def test_quiet_answer_names_both_floors_not_just_one():
    """The gold said THIRD floor only; the operator says second AND third."""
    a = _ans(F.quiet_study_answer, "where is the silent study area")
    assert "second" in a.lower() and "third" in a.lower()


def test_quiet_answer_says_where_the_fact_came_from():
    """It is not on any page, so the answer must not imply a page said it."""
    a = _ans(F.quiet_study_answer, "quiet study area")
    assert "library staff" in a.lower()
    assert F.KING_PHONE in a


@pytest.mark.parametrize("q", [
    "can you be quiet about my fines",          # 'quiet' but not a space question
    "how do I renew a book",
    "who is my librarian",
])
def test_quiet_does_not_overfire(q):
    assert F.quiet_study_answer(q) is None, q


# --- reading rooms: both on the 2nd floor -------------------------------


@pytest.mark.parametrize("q", [
    "where is the graduate reading room",
    "is there a faculty reading room",
    "grad reading room location",
    "staff reading room",
])
def test_reading_room_fires(q):
    a = _ans(F.reading_room_answer, q)
    assert a is not None, q
    assert "second floor" in a.lower()


def test_reading_room_tells_undergrads_where_to_go_instead():
    """The rooms are restricted, so a bare "you can't" is a dead end."""
    a = _ans(F.reading_room_answer, "can I use the graduate reading room")
    assert "undergraduate" in a.lower()
    assert "quiet study" in a.lower()


def test_reading_room_cites_the_page_that_really_is_titled_that():
    r = F.reading_room_answer("graduate reading room")
    assert r[1][0]["url"] == F.READING_ROOMS_URL


# --- restrooms: every floor ---------------------------------------------


@pytest.mark.parametrize("q", [
    "where are the bathrooms at King Library",
    "is there a restroom",
    "where's the toilet",
    "mens room",
])
def test_restroom_fires(q):
    a = _ans(F.restroom_answer, q)
    assert a is not None, q
    assert "every floor" in a.lower()


def test_restroom_answer_carries_no_citation():
    """No page states this, so no page gets cited for it."""
    assert F.restroom_answer("where are the bathrooms")[1] == []


def test_restroom_offers_a_route_for_accessible_or_all_gender():
    a = _ans(F.restroom_answer, "where are the bathrooms")
    assert "accessible" in a.lower()


# --- nursing room: there isn't one --------------------------------------


@pytest.mark.parametrize("q", [
    "do you have a lactation room",
    "is there a nursing room",
    "where can I breastfeed",
    "is there a mothers room",
])
def test_nursing_fires(q):
    assert F.nursing_room_answer(q) is not None, q


def test_nursing_answer_is_an_honest_no_with_a_route():
    """A parent needs to know BEFORE they travel."""
    a = _ans(F.nursing_room_answer, "is there a nursing room")
    assert "does **not** have" in a or "does not have" in a
    assert F.KING_PHONE in a
    assert "elsewhere on campus" in a.lower()


# --- printing / scanning / wifi -----------------------------------------


@pytest.mark.parametrize("q", [
    "how do I print",
    "can I scan a document",
    "where is the scanner",
    "how do I connect to wifi",
    "what's the wireless network",
    "can I print in color",
    "scan to email",
])
def test_print_scan_wifi_fires(q):
    a = _ans(F.printing_scanning_wifi_answer, q)
    assert a is not None, q


def test_print_answer_gives_the_actual_guides_not_a_shrug():
    """The old answer was "King Library offers printing/scanning services",
    retrieved from 231 characters of navigation menu."""
    r = F.printing_scanning_wifi_answer("how do I scan a document")
    a, cites = r
    urls = [c["url"] for c in cites]
    assert F.MUPRINT_GUIDE_URL in urls
    assert F.WIFI_SERVICE_URL in urls
    assert F.PRINTING_VIDEO_URL in urls
    assert "MUprint" in a
    assert "scan" in a.lower()


def test_all_cited_urls_are_the_verified_canonical_forms():
    """Recorded post-redirect on 2026-08-04; a stale ArticleDet?ID= form would
    still work but would not match what we checked."""
    _a, cites = F.printing_scanning_wifi_answer("how do I print")
    for c in cites:
        assert c["url"].startswith("https://")
        assert "ArticleDet?ID=" not in c["url"], "use the canonical redirect target"
        assert c["snippet"].strip()


@pytest.mark.parametrize("q", [
    "does the makerspace have a 3d printer",
    "how much does printing cost",
    "what are the fines for printing",
    "how do I get a reprint permission",
    "3D printing services",
])
def test_print_does_not_hijack_the_specific_cases(q):
    """3D printing, cost and reprints each have their own handler; this
    matcher is the broadest in the table and must yield to them."""
    assert F.printing_scanning_wifi_answer(q) is None, q


# --- shared -------------------------------------------------------------


def test_every_answer_is_nonempty_and_every_citation_is_numbered():
    cases = [
        (F.quiet_study_answer, "quiet study area"),
        (F.reading_room_answer, "graduate reading room"),
        (F.restroom_answer, "where are the bathrooms"),
        (F.nursing_room_answer, "lactation room"),
        (F.printing_scanning_wifi_answer, "how do I print"),
    ]
    for fn, q in cases:
        answer, cites = fn(q)
        assert answer.strip()
        for i, c in enumerate(cites, 1):
            assert c["n"] == i
            assert c["url"] and c["snippet"]
        # Every [n] marker in the text must have a matching citation.
        import re
        markers = {int(x) for x in re.findall(r"\[(\d+)\]", answer)}
        assert markers <= {c["n"] for c in cites}, (q, markers)
