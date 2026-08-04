"""BM25 query widening: the observed failure, and the ways it could misfire.

The regression case is exact: on 2026-08-04 the live index answered
"charger" with zero BM25 hits while holding a chunk that reads
"Chargers (Mac, PC, assorted phones)". Weaviate 1.28.6 has no English
stemmer, so this has to be fixed on the query side.
"""
from __future__ import annotations

from src.retrieval.query_expansion import expand_for_bm25


def _terms(q: str) -> set[str]:
    return set(expand_for_bm25(q).lower().split())


# --- the regression -------------------------------------------------------


def test_the_charger_case():
    """The whole reason this module exists."""
    assert "chargers" in _terms("can I borrow a charger")
    assert "charger" in _terms("do you have phone chargers")


def test_the_original_query_is_always_preserved():
    """Widening must never drop what the student actually typed."""
    for q in ("can I borrow a charger", "silent study floor",
              "scan a document to email", "who is my librarian"):
        out = expand_for_bm25(q)
        assert out.startswith(q), out


# --- English morphology ---------------------------------------------------


def test_plural_to_singular():
    assert "room" in _terms("study rooms")
    assert "policy" in _terms("borrowing policies")
    assert "box" in _terms("boxes")


def test_singular_to_plural():
    assert "scanners" in _terms("scanner")
    assert "policies" in _terms("policy")


def test_irregulars_a_suffix_rule_could_not_reach():
    assert "shelf" in _terms("hold shelves")
    assert "theses" in _terms("thesis")


def test_double_s_is_not_stripped():
    """"access" must not become "acces" and outrank the real term."""
    assert "acces" not in _terms("off campus access")


# --- the ways this could make retrieval WORSE ----------------------------


def test_short_and_function_words_are_left_alone():
    """Expanding "the"/"is"/"can" would add noise to every single query."""
    out = _terms("can I use the wifi")
    for junk in ("cans", "thes", "uses", "is"):
        assert junk not in out, junk


def test_a_query_with_nothing_to_add_is_returned_unchanged():
    assert expand_for_bm25("") == ""
    assert expand_for_bm25("   ") == ""
    q = "is it the"
    assert expand_for_bm25(q) == q


def test_long_input_is_bounded():
    """A pasted paragraph must not become a hundred-term BM25 query -- that
    flattens the scoring this is meant to sharpen."""
    long_q = " ".join(f"widget{i}" for i in range(200))
    added = len(expand_for_bm25(long_q).split()) - len(long_q.split())
    assert added <= 24, added


def test_no_duplicate_terms():
    out = expand_for_bm25("printers printer printers")
    words = out.lower().split()
    added = words[3:]
    assert len(added) == len(set(added))


def test_punctuation_and_case_survive():
    out = expand_for_bm25("Where are the Chargers?")
    assert out.startswith("Where are the Chargers?")
    assert "charger" in out.lower().split()


def test_hyphenated_and_apostrophes_do_not_crash():
    for q in ("self-checkout machine", "librarian's office",
              "e-books and audio-books"):
        assert expand_for_bm25(q).startswith(q)
