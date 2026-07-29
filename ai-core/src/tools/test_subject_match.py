"""Tests for the subject-match gate.

Every REJECT case below is a substitution that was live on 2026-07-28:
the fuzzy matcher picked that candidate and the bot answered with its
librarian's name and email. Every ACCEPT case is a real patron phrasing
that must keep resolving.
"""

import pytest

from src.tools.subject_match import (
    generic_words,
    is_plausible_subject_match,
    match_reason,
)

# The live liaison list, which is also the candidate pool the LibGuides
# API matches against. Used to derive which words are too generic to
# anchor a match.
POOL = [
    "Accountancy", "American Studies", "Anthropology",
    "Architecture & Interior Design", "Art", "Asian/Asian-American Studies",
    "Biology", "Black World Studies", "Business", "Business Legal Studies",
    "Chemical, Paper, and Biomedical Engineering",
    "Chemistry and Biochemistry", "Classics, Latin, and Greek",
    "Computer Science and Software Engineering", "Criminology", "Economics",
    "Education", "Electrical and Computer Engineering", "English",
    "Entrepreneurship", "Environmental Sciences",
    "Family Science and Social Work", "Finance", "French", "Geography",
    "Geology", "German", "Gerontology", "Government Information and Law",
    "History", "Information Systems & Analytics", "International Studies",
    "Italian", "Juvenile Literature", "Kinesiology, Nutrition, and Health",
    "Latin American Studies", "Law", "Makerspace", "Management",
    "Marketing", "Mathematics", "Mechanical and Manufacturing Engineering",
    "Media, Journalism, and Film", "Microbiology",
    "Middle Eastern and Islamic Studies", "Military Studies", "Music",
    "Neuroscience", "Nursing", "Philosophy", "Physics", "Political Science",
    "Psychology", "Religion", "Sociology", "Spanish and Portuguese",
    "Special Collections", "Speech Pathology and Audiology",
    "Sports Leadership and Management", "Statistics", "Student Affairs",
    "Teacher Education", "Theater",
    "Women's, Gender and Sexuality Studies",
]
GENERIC = generic_words(POOL)


def test_generic_words_are_derived_not_hand_listed():
    """The stopword set comes from the candidate list itself, so it tracks
    the live subject list instead of drifting."""
    # these appear in 3+ subject names, so they cannot prove a match
    for w in ["and", "science", "studies", "engineering"]:
        assert w in GENERIC, w
    # these appear once or twice and DO identify a subject
    for w in ["biology", "nursing", "journalism", "kinesiology",
              "paper", "marketing"]:
        assert w not in GENERIC, w


# --- the live wrong answers ----------------------------------------------

@pytest.mark.parametrize("query,candidate", [
    # Botany scored 0.455 against Accountancy and the bot answered with
    # the Business Librarian's email.
    ("Botany", "Accountancy"),
    ("Chinese", "Business"),
    # only overlap is the generic word "science"
    ("Data Science", "Political Science"),
    # 0.844 on the shared tail alone -- HIGHER than the tightest genuine
    # typo we accept, which is why no threshold can separate these
    ("Paper Science and Engineering",
     "Computer Science and Software Engineering"),
    ("Zoology", "Biology"),
    ("Religion", "Region"),
    ("Kinesiology", "Criminology"),
    ("Supply Chain", "Spanish and Portuguese"),
    ("Japanese", "Art"),
])
def test_rejects_a_different_subject(query, candidate):
    assert not is_plausible_subject_match(query, candidate, GENERIC)


# --- what must keep working ----------------------------------------------

@pytest.mark.parametrize("query,candidate", [
    ("Marketing", "Marketing"),
    ("nursing", "Nursing"),
    ("STATISTICS", "Statistics"),
])
def test_accepts_exact(query, candidate):
    assert match_reason(query, candidate, GENERIC) == "exact"


@pytest.mark.parametrize("query,candidate", [
    # the old 0.45 threshold REJECTED these: "Kinesiology" scores only
    # 0.32 against the full name, so raising the threshold would have
    # made coverage worse, not better
    ("Kinesiology", "Kinesiology, Nutrition, and Health"),
    ("Journalism", "Media, Journalism, and Film"),
    ("Analytics", "Information Systems & Analytics"),
    ("Architecture", "Architecture & Interior Design"),
    ("Women's Studies", "Women's, Gender and Sexuality Studies"),
    ("Paper Engineering", "Chemical, Paper, and Biomedical Engineering"),
])
def test_accepts_a_whole_word_subset(query, candidate):
    assert is_plausible_subject_match(query, candidate, GENERIC)


@pytest.mark.parametrize("query,candidate", [
    ("biolgy", "Biology"),
    ("psycology", "Psychology"),
    ("nursin", "Nursing"),
    ("marketting", "Marketing"),
    ("histroy", "History"),
    ("phsyics", "Physics"),
])
def test_accepts_a_typo(query, candidate):
    assert is_plausible_subject_match(query, candidate, GENERIC)


@pytest.mark.parametrize("query,candidate", [
    ("Accounting", "Accountancy"),
    ("chemisty", "Chemistry and Biochemistry"),
])
def test_accepts_a_shared_head_word_stem(query, candidate):
    assert is_plausible_subject_match(query, candidate, GENERIC)


# --- properties ----------------------------------------------------------

def test_punctuation_splits_here_unlike_person_names():
    """Opposite convention to person_names, on purpose. A surname must
    stay whole ("Jones-Scott"), but a subject list must break apart or
    "Women's, Gender and Sexuality Studies" offers no anchors."""
    assert is_plausible_subject_match("Gender", "Women's, Gender and "
                                      "Sexuality Studies", GENERIC)
    assert is_plausible_subject_match("Biomedical",
                                      "Chemical, Paper, and Biomedical "
                                      "Engineering", GENERIC)


def test_every_pool_subject_matches_itself():
    for name in POOL:
        assert is_plausible_subject_match(name, name, GENERIC), name


def test_admitted_pairs_are_related_not_lookalikes():
    """Whatever the gate lets through must be genuinely RELATED, never
    merely similar-looking. Two ways that is allowed: a shared distinctive
    word, or one name's words containing the other's -- which happens for
    real hierarchies like "American Studies" inside "Asian/Asian-American
    Studies". What must NEVER appear is a typo- or stem-based link between
    two DIFFERENT real subjects, because that is character soup."""
    for i, a in enumerate(POOL):
        for b in POOL[i + 1:]:
            reason = match_reason(a, b, GENERIC)
            if reason is None:
                continue
            assert ("distinctive word" in reason or "subset" in reason), \
                f"{a!r} ~ {b!r} admitted by lookalike rule: {reason}"


def test_a_real_subject_always_ranks_itself_first():
    """The safety net behind the subset rule. "American Studies" IS a
    word-subset of "Asian/Asian-American Studies", so both are admitted --
    correctness then depends on the caller ranking by similarity, where an
    exact match scores 1.0. This asserts that end to end, which is what
    actually protects the patron."""
    from src.tools.libguide_comprehensive_tools import _fuzzy_best_match

    for name in POOL:
        ranked = _fuzzy_best_match(name, POOL, {}, num_results=1)
        assert ranked, name
        assert ranked[0][1] == name, f"{name!r} ranked {ranked[0][1]!r} first"


def test_empty_and_none_never_match():
    for bad in ["", "   ", None, "of", "a"]:
        assert not is_plausible_subject_match(bad, "Biology", GENERIC)
        assert not is_plausible_subject_match("Biology", bad, GENERIC)
