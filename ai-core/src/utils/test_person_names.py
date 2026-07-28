"""Tests for the one name-comparison rule.

Every case here is a REAL spelling that exists in the roster, the
LibGuides API, or a patron transcript -- the six multi-word/punctuated
active names as of 2026-07-28 plus the two live wrong-person incidents.
"""

import pytest

from src.utils.person_names import (
    display_name,
    first_last,
    names_match,
    normalize_words,
)


# --- normalization -------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("Roger A Justus", ("roger", "justus")),          # middle initial
    ("Cheyenne K Partridge", ("cheyenne", "partridge")),
    ("Patricia Kay Russell",                           # FULL middle name
     ("patricia", "kay", "russell")),
    ("Rob O'Brien Withers", ("rob", "obrien", "withers")),  # apostrophe
    ("Anthony Jones-Scott", ("anthony", "jonesscott")),     # hyphen: ONE word
    ("Dr. Ginny Boehme", ("ginny", "boehme")),              # title dropped
    ("  GINNY   BOEHME  ", ("ginny", "boehme")),
    ("", ()),
    (None, ()),
])
def test_normalize_words(raw, expected):
    assert normalize_words(raw) == expected


def test_hyphen_and_apostrophe_do_not_split_a_surname():
    # Splitting on punctuation would make "Jones-Scott" two words, and a
    # query for "Anthony Jones" would then match by accident.
    assert normalize_words("Anthony Jones-Scott") == ("anthony", "jonesscott")
    assert not names_match("Anthony Jones", "Anthony Jones-Scott")


def test_accents_fold():
    assert normalize_words("José Álvarez") == ("jose", "alvarez")


@pytest.mark.parametrize("raw,expected", [
    ("Roger A Justus", ("roger", "justus")),
    ("Patricia Kay Russell", ("patricia", "russell")),
    ("Rob O'Brien Withers", ("rob", "withers")),
    ("Boehme", ("", "")),          # one word -> no pair
])
def test_first_last_drops_everything_between(raw, expected):
    assert first_last(raw) == expected


# --- matching ------------------------------------------------------------

@pytest.mark.parametrize("query,stored", [
    # middle initial in the roster, patron types neither
    ("Roger Justus", "Roger A Justus"),
    ("roger justus", "Roger A Justus"),
    ("Roger A. Justus", "Roger A Justus"),      # both spell the initial
    ("Roger A Justus", "Roger Justus"),         # reversed: API is shorter
    # full middle name
    ("Alia Wegner", "Alia Levar Wegner"),
    ("Patricia Russell", "Patricia Kay Russell"),
    # the regex captures only two words, so a 3-word ask arrives truncated
    ("Patricia Kay", "Patricia Kay Russell"),
    ("Rob O'Brien", "Rob O'Brien Withers"),
    # punctuation differences on either side
    ("Rob OBrien Withers", "Rob O'Brien Withers"),
    ("Anthony Jones-Scott", "Anthony JonesScott"),
    ("cheyenne partridge", "Cheyenne K Partridge"),
])
def test_same_person_matches_across_spellings(query, stored):
    assert names_match(query, stored)


@pytest.mark.parametrize("query,stored", [
    # THE bug this rule exists for: the middle initial "A" used to match
    # the "a" inside "Krista", so a Krista McDonald ask returned Roger
    # Justus's email (live 2026-07-28).
    ("Krista McDonald", "Roger A Justus"),
    ("Jaclyn Spraetz", "Roger A Justus"),
    # a shared surname is not a match -- it must not declare the wrong
    # person departed, or hand over a relative's contact details
    ("Ginny Smith", "John Smith"),
    ("John Burke", "Krista McDonald"),
    # a first name in common is not enough
    ("John Williams", "John Burke"),
    ("", "Ginny Boehme"),
    ("Ginny Boehme", ""),
    ("Ginny Boehme", None),
])
def test_different_people_do_not_match(query, stored):
    assert not names_match(query, stored)


def test_bare_surname_matches_but_is_the_callers_problem_to_cap():
    # A one-word query legitimately matches everyone with that surname;
    # callers cap how many people they present rather than narrowing here.
    assert names_match("Boehme", "Ginny Boehme")
    assert names_match("Justus", "Roger A Justus")


# --- what we SAY ---------------------------------------------------------

@pytest.mark.parametrize("raw,said", [
    ("Roger A Justus", "Roger Justus"),
    ("Patricia Kay Russell", "Patricia Russell"),
    ("Rob O'Brien Withers", "Rob Withers"),
    ("Alia Levar Wegner", "Alia Wegner"),
    ("Cheyenne K Partridge", "Cheyenne Partridge"),
    # a hyphenated surname is the whole surname -- keep it
    ("Anthony Jones-Scott", "Anthony Jones-Scott"),
    # already short, or unusable: pass through rather than mangle
    ("Ginny Boehme", "Ginny Boehme"),
    ("Boehme", "Boehme"),
    ("", ""),
])
def test_display_name_drops_middles_and_keeps_capitalisation(raw, said):
    assert display_name(raw) == said


def test_display_name_never_drops_a_needed_word():
    # Whatever we say must still resolve back to the roster row, or the
    # bot would print a name its own lookup can't find.
    for stored in ["Roger A Justus", "Patricia Kay Russell",
                   "Rob O'Brien Withers", "Alia Levar Wegner",
                   "Anthony Jones-Scott", "Cheyenne K Partridge"]:
        assert names_match(display_name(stored), stored), stored


# --- nicknames are NOT middle names -------------------------------------

def test_nicknames_cannot_be_derived_and_need_the_data_column():
    """The reason Librarian.alternateName exists.

    A nickname shares no letters-rule with the formal name, so no amount
    of normalization gets from "Jacky" to "Jacqueline". These MUST NOT
    match on their own -- if they did, the rule would be matching loosely
    enough to confuse different people, which is the failure mode the
    whole module exists to prevent.
    """
    assert not names_match("Jacky Johnson", "Jacqueline Johnson")
    assert not names_match("Andy Revelle", "Andrew Revelle")
    assert not names_match("Jerry Yarnetsky", "Eric Yarnetsky")


def test_the_alternate_spelling_matches_when_supplied():
    """What the lookup actually does: try `name`, then `alternateName`.

    Both directions, because the operator has both -- Jacqueline goes by
    Jacky (formal stored, nickname alternate), while Jerry's formal first
    name is Eric but he is displayed as Jerry (nickname stored, formal
    alternate).
    """
    ROSTER = [
        # (name we display, alternate we accept)
        ("Jacqueline Johnson", "Jacky Johnson"),
        ("Andrew Revelle", "Andy Revelle"),
        ("Jerry Yarnetsky", "Eric Yarnetsky"),
    ]

    def lookup(asked):
        return [shown for shown, alt in ROSTER
                if names_match(asked, shown) or names_match(asked, alt)]

    assert lookup("Jacky Johnson") == ["Jacqueline Johnson"]
    assert lookup("Jacqueline Johnson") == ["Jacqueline Johnson"]
    assert lookup("Andy Revelle") == ["Andrew Revelle"]
    assert lookup("Andrew Revelle") == ["Andrew Revelle"]
    # the reverse direction: asking the formal name yields the name he
    # actually goes by, never "Eric"
    assert lookup("Eric Yarnetsky") == ["Jerry Yarnetsky"]
    assert lookup("Jerry Yarnetsky") == ["Jerry Yarnetsky"]
    # an alternate must not become a wildcard: a shared first OR last
    # name is still not a match
    assert lookup("Jacky Smith") == []
    assert lookup("Andy Johnson") == []
    assert lookup("Eric Adams") == []
