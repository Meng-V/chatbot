"""The alias table must not misroute ordinary English.

Every FAIL case here was live on 2026-07-29: `find_subject_by_alias` did a
bare substring test in dict order, so a 2-4 character course-code
abbreviation matched inside an ordinary word and the bot answered with that
subject's librarian, by name and email.

    "digital collections" -> 'ita' -> Italian     -> the Humanities Librarian
    "the reserve desk"    -> 'the' -> Theater
    "meeting rooms"       -> 'ee'  -> Electrical and Computer Engineering
"""

import pytest

from src.tools.subject_aliases import (
    SUBJECT_ALIASES,
    find_subject_by_alias,
    find_subject_by_course_code,
)


@pytest.mark.parametrize("query", [
    # the exact strings that misrouted
    "digital collections", "digital humanities", "the reserve desk",
    "meeting rooms", "quarterly reports", "start a paper",
    "relevant databases", "space science", "strength training",
    "capital markets", "hospital administration", "week long workshop",
    "three credit course", "partial credit", "lawn care", "other topics",
    "together", "need help", "see also",
])
def test_ordinary_english_resolves_to_no_subject(query):
    assert find_subject_by_alias(query) is None


@pytest.mark.parametrize("query,expected", [
    # a short code IS a subject when it is the WHOLE ask
    ("chem", "Chemistry and Biochemistry"),
    ("bio", "Biology"),
    ("psy", "Psychology"),
    ("the", "Theater"),
    ("cs", "Computer Science and Software Engineering"),
    # and a long alias still matches inside a sentence
    ("i need help with biology", "Biology"),
    ("sources for psychology", "Psychology"),
    ("organic chemistry", "Chemistry and Biochemistry"),
    ("marketing research", "Marketing"),
    # operator-confirmed additions from the same day
    ("botany", "Biology"),
    ("zoology", "Biology"),
    ("japanese", "Asian/Asian-American Studies"),
    ("data science", "Information Systems & Analytics"),
])
def test_real_aliases_still_resolve(query, expected):
    assert find_subject_by_alias(query) == expected


def test_longest_alias_wins_not_dict_order():
    """Which alias matched used to depend on insertion order, so the same
    query could resolve differently after an unrelated edit."""
    # "organic chemistry" contains "chem"; the longer, more specific alias
    # must decide
    assert find_subject_by_alias("organic chemistry lab") == \
        SUBJECT_ALIASES["organic chemistry"]


def test_no_short_alias_can_match_as_a_fragment():
    """Property: every alias shorter than the containment floor is
    unreachable except as a whole query. Guards the whole class rather than
    the handful of examples above."""
    short = [a for a in SUBJECT_ALIASES if len(a) < 5]
    assert short, "the table does contain short codes; that is the point"
    for alias in short:
        # embedded in a longer word, it must not fire
        assert find_subject_by_alias(f"xx{alias}yy") is None, alias
        # ...but alone it must
        assert find_subject_by_alias(alias) == SUBJECT_ALIASES[alias], alias


@pytest.mark.parametrize("code,expected", [
    ("BIO 203", "Biology"),
    ("bio203", "Biology"),
    ("CHM", "Chemistry and Biochemistry"),
    ("PSY 101", "Psychology"),
])
def test_course_codes_resolve(code, expected):
    assert find_subject_by_course_code(code) == expected


@pytest.mark.parametrize("not_a_code", [
    # matched the first 2-4 letters of ANY string before the fix, so
    # "the reserve desk" yielded prefix "THE" -> Theater
    "the reserve desk", "a very long question about art",
    "engineering help", "", "   ",
])
def test_a_phrase_is_not_a_course_code(not_a_code):
    assert find_subject_by_course_code(not_a_code) is None
