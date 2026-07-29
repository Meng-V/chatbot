"""
Is this subject match real, or did fuzzy matching swap the subject?

WHY THIS EXISTS
    `libguide_comprehensive_tools` picked the closest subject name by
    Damerau-Levenshtein distance and accepted anything scoring >= 0.45 --
    45% of characters aligning. On the live liaison list that silently
    substituted a DIFFERENT subject and then answered with that subject's
    librarian, reporting success (found 2026-07-28):

        "Botany"                        -> Accountancy  -> Business Librarian
        "Chinese"                       -> Business     -> Business Librarians
        "Data Science"                  -> Political Science
        "Paper Science and Engineering" -> Computer Science and Software Eng.

    Handing a patron the wrong person is the worst error this bot makes,
    and character distance cannot tell these from real typos: "paper
    science and engineering" scores 0.84 against "computer science and
    software engineering" purely on the shared tail, while the genuine
    typo "biolgy" -> "Biology" scores 0.86. A threshold cannot separate
    them; only looking at WORDS can.

    Same discipline as src/utils/person_names.py: no character-soup
    matching across different words.

WHAT COUNTS AS A MATCH
    1. the same words (exact)
    2. one is a whole-word subset of the other
       "Kinesiology" c "Kinesiology, Nutrition, and Health"
    3. they share a DISTINCTIVE word
       "Journalism" in "Media, Journalism, and Film"
    4. a genuine typo of the whole string (>= 0.85 similarity)
    5. the head words share a >= 6-character stem
       "Accounting" ~ "Accountancy"

    Anything else is a rejection, which makes the caller say "no liaison
    listed for that" and point at the directory -- an honest miss instead
    of a confident wrong name.

WHAT MAKES A WORD "DISTINCTIVE"
    Not a hand-written stopword list, which would go stale with the
    subject list. A word is generic if it appears in `_GENERIC_DF` or more
    of the CANDIDATE NAMES THEMSELVES -- on the current liaison list that
    derives {and, american, business, engineering, science, studies},
    which is exactly why "data science"/"political science" and "paper
    science and engineering"/"computer science and software engineering"
    are rejected: their only overlap is generic.
"""

from __future__ import annotations

import re

# A word appearing in this many candidate names is too common to prove
# two subjects are the same thing.
_GENERIC_DF = 3

# Words shorter than this carry no signal ("of", "the", "in").
_MIN_WORD = 3

# Whole-string similarity that counts as a typo rather than a different
# subject. Calibrated against real cases: the tightest genuine typo we
# accept scores 0.857 ("biolgy"/"biology"), the loosest wrong match we
# must reject scores 0.844.
_TYPO_SIMILARITY = 0.85

# Shared leading characters on the HEAD word that imply the same root
# ("accounting"/"accountancy", "chemisty"/"chemistry").
_MIN_STEM = 6


def _words(text: object) -> list[str]:
    """Significant lowercase words, punctuation treated as a separator.

    Unlike person names, punctuation here SPLITS: "Women's, Gender and
    Sexuality Studies" must yield `women` and `gender` as separate
    anchors, and "Chemical, Paper, and Biomedical Engineering" must not
    collapse into one token.
    """
    cleaned = re.sub(r"[^\w\s]", " ", str(text or "").lower())
    return [w for w in cleaned.split() if len(w) >= _MIN_WORD]


def _similarity(a: str, b: str) -> float:
    """1.0 for identical strings, 0.0 for nothing in common."""
    from src.tools.libguide_comprehensive_tools import _levenshtein_distance

    a, b = a.lower().strip(), b.lower().strip()
    if not a or not b:
        return 0.0
    return max(1 - _levenshtein_distance(a, b) / max(len(a), len(b)), 0.0)


def generic_words(candidates: "list[str]") -> set[str]:
    """Words too common across `candidates` to anchor a match.

    Derived from the candidate list at call time, so it tracks the live
    subject list instead of drifting like a hand-kept stopword list.
    """
    counts: dict[str, int] = {}
    for name in candidates or []:
        for w in set(_words(name)):
            counts[w] = counts.get(w, 0) + 1
    return {w for w, n in counts.items() if n >= _GENERIC_DF}


def _stem_overlap(a: str, b: str) -> int:
    n = 0
    while n < min(len(a), len(b)) and a[n] == b[n]:
        n += 1
    return n


def match_reason(
    query: object, candidate: object, generic: "set[str] | None" = None
) -> "str | None":
    """Why `query` and `candidate` are the same subject, or None.

    Returning the REASON rather than a bool keeps the decision auditable:
    the tool logs it, so a wrong answer can be traced to the rule that
    allowed it instead of to an opaque score.
    """
    qw, cw = _words(query), _words(candidate)
    if not qw or not cw:
        return None

    if qw == cw:
        return "exact"
    qs, cs = set(qw), set(cw)
    if qs <= cs:
        return "query is a whole-word subset of the candidate"
    if cs <= qs:
        return "candidate is a whole-word subset of the query"

    gen = generic if generic is not None else set()
    distinctive = (qs & cs) - gen
    # Coverage is measured over the query's DISTINCTIVE words only. Counting
    # generic ones in the denominator made "film studies" fail against
    # "Media, Journalism, and Film": "studies" appears in several subject
    # names, so it carries no information and must not dilute the match.
    q_signal = qs - gen
    if distinctive and len(distinctive) * 2 > len(q_signal):
        # The shared word must carry MOST of the query, not just appear in
        # it. `generic` is derived from the subject list, so a word that is
        # common in English but rare among subjects still looks
        # distinctive: "paper" occurs in exactly one subject name, which
        # made "start a paper" match "Chemical, Paper, and Biomedical
        # Engineering" and answer with its liaison (found 2026-07-29 while
        # re-verifying the alias fix -- unreachable through the agent,
        # which never passes a phrase like that as a subject, but a latent
        # path all the same).
        #
        # Requiring a strict majority of the query's words to appear in the
        # candidate separates the two cleanly: "paper engineering" has both
        # its words in that subject (2 of 2), "start a paper" has one of
        # two. The subset rules above already cover the short, legitimate
        # asks ("Journalism", "Kinesiology"), so this only tightens the
        # single-shared-word case.
        return f"shares distinctive word(s): {', '.join(sorted(distinctive))}"

    score = _similarity(str(query), str(candidate))
    if score >= _TYPO_SIMILARITY:
        return f"typo of the whole name (similarity {score:.2f})"

    stem = _stem_overlap(qw[0], cw[0])
    if stem >= _MIN_STEM:
        return f"head words share the stem '{qw[0][:stem]}'"

    return None


def is_plausible_subject_match(
    query: object, candidate: object, generic: "set[str] | None" = None
) -> bool:
    """True when naming `candidate`'s librarian answers `query`."""
    return match_reason(query, candidate, generic) is not None


__all__ = [
    "generic_words",
    "is_plausible_subject_match",
    "match_reason",
]
