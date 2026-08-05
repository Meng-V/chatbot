"""Equipment questions answered from the tech-checkout page's own list.

The interesting cases are the NEGATIVE ones. This handler sits in the
short-circuit table ahead of the agent, so a false positive replaces a good
retrieved answer with a canned one -- which is exactly how the printing
pointer lost four correct answers on 2026-08-04 before it was narrowed twice.

The positive cases exist because the opposite failure was also real: on the
2026-08-05 gold run both `tech_charger` and `tech2_calculator_borrow` refused
while the answer sat in the retrieved evidence, unread, inside a nested
bullet list.
"""
from __future__ import annotations

import pytest

from src.graph import tech_checkout as T

# The live chunk, verbatim from Chunk_vv20260804_1110 on 2026-08-05. Pinned as
# a fixture rather than fetched: the parser's contract is with THIS markup, and
# a test that reads the live index would go green or red for reasons that have
# nothing to do with the parser.
PAGE = """Equipment to Checkout and Go
The libraries offer a wide range of technology you can checkout to support your coursework (and your enjoyment). Come to a library checkout desk with your university ID to borrow equipment. Log into computers/iPads while on-campus with your ID/password and you will be ready to go!
- Call or stop by to check availability
Sometimes items become overdue or broken, so availability can be unpredictable. Feel free to call in advance to check on availability or ask details about our equipment at (513) 529-4141. Loan Periods and Late Fees
- Chromebook laptops may be checked out for 30 days.
- Tablets, Cameras, and camcorders are 24 hour checkouts.
- Damaged or Loss charges are up to $2,000 for laptops and tablets and $495 for cameras/audio-visual equipment. Available Equipment
- Laptops & Tablets

  - Chromebook
  - iPad Pros and Apple Pencils â€“ available at Art & Architecture Library
- Audio equipment (available at King Library)

  - Digital Audio Recorders
  - Microphones (assorted portable and desktop)
  - Headphones
  - Portable microphone/speaker sets.
- Photography

  - Digital Cameras (assorted)
  - Camera Tripods
- Video

  - DVD Players
  - Projectors
- Calculators

  - Financial
  - Graphing
  - Scientific
- Chinese-English translators
- Cables and peripherals

  - External Disc Drive
  - Card Readers
  - Network cables
  - Adaptors
  - Mouses
  - Chargers (Mac, PC, assorted phones)"""


def _ans(q, page=PAGE):
    r = T.tech_checkout_answer(q, page)
    return r[0] if r else None


# --- the parser ---------------------------------------------------------


def test_parses_seven_categories_and_nineteen_items():
    cats = T.parse_equipment(PAGE)
    assert len(cats) == 7
    assert sum(len(v) for v in cats.values()) == 19


def test_parser_ignores_the_bullets_that_are_prose_not_inventory():
    """The bullets BEFORE "Available Equipment" are loan periods and advice.
    Reading them as equipment would have the bot claim the library lends
    "Call or stop by to check availability"."""
    cats = T.parse_equipment(PAGE)
    joined = " ".join(cats.keys()).lower()
    assert "call or stop by" not in joined
    assert "may be checked out for 30 days" not in joined
    assert "damaged or loss" not in joined


def test_unparseable_page_disables_the_handler_rather_than_guessing():
    assert T.parse_equipment("") == {}
    assert T.parse_equipment("no list here at all") == {}
    assert T.tech_checkout_answer("do you lend chargers", "no list here") is None


# --- the two cases that refused in production --------------------------


def test_charger_no_longer_refuses():
    a = _ans("do you lend chargers")
    assert a is not None
    assert "Chargers" in a


def test_graphing_calculator_no_longer_refuses():
    """gold tech2_calculator_borrow. The page says `Calculators` / `Graphing`,
    two nested list items, and the synthesizer would not commit to it."""
    a = _ans("Does the library lend graphing calculators?")
    assert a is not None
    assert "Graphing calculators" in a


# --- how students actually type ----------------------------------------


@pytest.mark.parametrize("q", [
    "do you lend chargers",
    "do you have chargers",
    "can I borrow a phone charger",
    "got a laptop charger i can borrow",
    "any cables i can check out",
    "do you have calculators",
    "can i check out a scientific calculator",
    "do you lend laptops",
    "do you lend chromebooks",
    "can i borrow an ipad",
    "can i borrow an apple pencil",
    "do you have tripods",
    "can I check out a projector",
    "do you have microphones i can borrow",
    "do you lend headphones",
    "do you have hdmi adapters",
    "do you have dvd players",
    "can i check out an audio recorder",
    "do you lend network cables",
])
def test_fires_on_real_phrasings(q):
    assert _ans(q) is not None, q


# --- what it must NOT touch --------------------------------------------


@pytest.mark.parametrize("q", [
    # loan periods, fees and damages are on the page but are not inventory,
    # and each has its own handler or gold expectation
    "how long can i keep a laptop",
    "what's the late fee for a camera",
    "how much if i lose the ipad",
    "what's the loan period for calculators",
    "can i renew the laptop",
    "what is the tech checkout policy",
    "can i reserve a camera in advance",
    # counts are not on the page at all
    "how many laptops do you have",
    # not a borrowing question despite naming an item
    "where do i plug in my charger",
    # other domains entirely
    "how do I connect to wifi",
    "do you have study rooms",
    "where is the makerspace",
    # equipment the page does not list -- must fall through to the agent
    # rather than assert a "no" this handler cannot support
    "do you lend gopros",
    "can i borrow an umbrella",
    "do you have a 3d printer",
])
def test_does_not_overfire(q):
    assert T.tech_checkout_answer(q, PAGE) is None, q


# --- answer hygiene -----------------------------------------------------


def test_answer_repairs_the_pages_mis_encoded_dash():
    """The chunk carries a UTF-8 em dash read as Latin-1. Echoing it verbatim
    makes the bot look broken."""
    a = _ans("can i borrow an apple pencil")
    assert "â" not in a
    assert "Apple Pencils" in a


def test_every_citation_is_numbered_and_matches_a_marker():
    import re
    answer, cites = T.tech_checkout_answer("do you lend chargers", PAGE)
    assert cites
    for i, c in enumerate(cites, 1):
        assert c["n"] == i
        assert c["url"] and c["snippet"]
    markers = {int(x) for x in re.findall(r"\[(\d+)\]", answer)}
    assert markers <= {c["n"] for c in cites}


def test_answer_cites_only_the_tech_checkout_page():
    _a, cites = T.tech_checkout_answer("do you have calculators", PAGE)
    assert [c["url"] for c in cites] == [T.TECH_CHECKOUT_URL]


def test_answer_tells_the_student_to_ring_ahead():
    """Availability is explicitly unpredictable on the page; an answer that
    promises a charger is on the shelf would be over-claiming."""
    a = _ans("do you lend chargers")
    assert T.KING_PHONE in a
    assert "ID" in a


def test_the_answer_follows_the_page_not_a_hardcoded_list():
    """The inventory must be read from the page every time.

    Asserted behaviourally rather than by grepping the source: rename an item
    on the page and the answer must rename with it. A hardcoded list would keep
    citing the old wording, which is how a bot ends up confidently naming
    equipment the library retired two years ago.
    """
    # Reword an item the synonym table DOES cover. The synonym ("charger")
    # still matches, so the handler still fires -- but the wording it quotes
    # has to be the page's new wording, not the old string.
    reworded = PAGE.replace("Chargers (Mac, PC, assorted phones)",
                            "Power bricks and chargers (all types)")
    a = _ans("do you lend chargers", reworded)
    assert a is not None
    assert "Power bricks and chargers (all types)" in a
    assert "Mac, PC, assorted phones" not in a

    # And an item whose wording no longer mentions what was asked stops
    # being offered under the old name.
    dropped = PAGE.replace("Camera Tripods", "Lighting kits")
    a2 = _ans("do you have tripods", dropped)
    assert a2 is None or "Camera Tripods" not in a2


def test_an_item_removed_from_the_page_stops_being_offered():
    """The other direction: drop chargers from the page and the charger
    question must fall through to the agent, not keep answering yes."""
    without = PAGE.replace("  - Chargers (Mac, PC, assorted phones)", "")
    assert T.tech_checkout_answer("do you lend chargers", without) is None


# --- the cheap pre-filter used by step 3.60 -----------------------------


@pytest.mark.parametrize("q", [
    "do you lend chargers",
    "can I borrow a phone charger",
    "Does the library lend graphing calculators?",
])
def test_prefilter_lets_equipment_questions_through(q):
    assert T.looks_like_equipment_question(q) is True, q


@pytest.mark.parametrize("q", [
    "what are your hours",
    "how long can i keep a laptop",
    "what's the late fee for a camera",
    "who is my subject librarian",
    "where is the makerspace",
])
def test_prefilter_skips_the_fetch_for_everything_else(q):
    assert T.looks_like_equipment_question(q) is False, q


def test_prefilter_agrees_with_the_real_decision_on_negatives():
    """If the pre-filter says no, the full path must also say no -- otherwise
    the orchestrator would skip a fetch that would have produced an answer."""
    for q in ("what are your hours", "how long can i keep a laptop",
              "who is my subject librarian", "what is the tech checkout policy"):
        assert not T.looks_like_equipment_question(q)
        assert T.tech_checkout_answer(q, PAGE) is None
